"""
tests/test_flow.py - End-to-end test of the full workflow through the real HTTP API.
Run:  python -m tests.test_flow      (from the project folder)
Uses a fresh test database and the OFFLINE brain (no API calls, no quota used).
"""
import os
import sys

import db
db.DB_PATH = "test_crm.db"                       # separate DB for tests
if os.path.exists(db.DB_PATH):
    os.remove(db.DB_PATH)

import llm
llm.client = None                                # force the offline brain: fast, free, repeatable
llm.last_mode = "offline-fallback"

from fastapi.testclient import TestClient
import main


def run_call(client, lang, lines, end=True):
    r = client.post("/api/call/start", json={"language": lang}).json()
    cid = r["call_id"]
    print(f"\n=== CALL {cid} ({lang}) mode={r['mode']} ===\nAgent : {r['reply']}")
    outs = []
    for line in lines:
        out = client.post(f"/api/call/{cid}/message", json={"text": line, "language": lang}).json()
        tools = ", ".join(e["tool"] for e in out["events"]) or "-"
        print(f"Caller: {line}\n   [tools: {tools}]{'  [END_CALL]' if out['end_call'] else ''}\nAgent : {out['reply']}")
        outs.append(out)
    lead = outs[-1]["lead"]
    print(f"LEAD -> name={lead['name']} city={lead['city']} need={lead['need']} budget={lead['budget']} "
          f"timeline={lead['timeline']} score={lead['score']} sentiment={lead['sentiment']} status={lead['status']}")
    summary = None
    if end:
        summary = client.post(f"/api/call/{cid}/end").json()
        print("SUMMARY :", summary["summary"]); print("INSIGHTS:", summary["insights"])
    return outs, summary


def booked_hour(out):
    return next((e["result"]["slot"][-5:] for e in out["events"]
                 if e["tool"] == "book_appointment" and e["result"].get("booked")), None)


with TestClient(main.app) as client:
    checks = []
    # 1) English: RAG -> qualify -> slots -> book BY TIME ("3 p.m." as Chrome writes it) -> end-of-call flow
    outs, end = run_call(client, "en", [
        "Hi, my name is Rahul. How much subsidy do I get for a 3 kW system?",
        "I live in Delhi",
        "Budget is around 2 lakh",
        "I want it within 1 month",
        "3 p.m. please",
        "No, that's all",
        "Yes please",
    ])
    first = outs[0]
    checks += [("RAG: search_kb called", any(e["tool"] == "search_kb" for e in first["events"])),
               ("RAG: answer has KB fact", "78,000" in first["reply"]),
               ("lead scored hot", outs[-1]["lead"]["score"] == "hot"),
               ("booked by time '3 p.m.' -> 15:00", booked_hour(outs[4]) == "15:00"),
               ("'no' -> asks to end call (not 'anything else' again)", "end the call" in outs[5]["reply"]
                and "anything else" not in outs[5]["reply"].lower()),
               ("'yes' -> end_call flag", outs[6]["end_call"] is True and outs[5]["end_call"] is False),
               ("summary saved", bool(end["summary"]))]

    # 2) Hindi: unavailable time -> told + options; then ordinal "दूसरे वाला"; then end flow in Hindi
    outs2, _ = run_call(client, "hi", [
        "मेरा नाम प्रिया है",
        "सब्सिडी कितनी मिलेगी?",
        "जयपुर",
        "5 kW चाहिए",
        "बजट 3 लाख है",
        "अगले महीने",
        "दोपहर 2 बजे",
        "दूसरे वाला",
        "नहीं, बस",
        "हाँ कर दो",
    ])
    checks += [("hindi lead saved", outs2[-1]["lead"]["city"] == "Jaipur"),
               ("hindi: unavailable 2 PM explained", "खाली नहीं" in outs2[6]["reply"] and booked_hour(outs2[6]) is None),
               ("hindi: booked by ordinal", outs2[-1]["lead"]["status"] == "booked"),
               ("hindi: asks to end call", "कॉल समाप्त" in outs2[8]["reply"]),
               ("hindi: 'haan kar do' -> end_call", outs2[9]["end_call"] is True)]

    # 3) Saying "no" to "shall I end?" keeps the call going
    outs3, _ = run_call(client, "en", ["My name is Amit from Pune, 3 kW, budget 2 lakh, within 2 weeks",
                                       "first one", "nothing else", "no, wait", ], end=False)
    checks.append(("'no' to ending keeps call open", outs3[-1]["end_call"] is False and "what else" in outs3[-1]["reply"].lower()))

    # 3b) The same lead cannot book a second visit (guards against an LLM booking twice)
    import tools
    lead_amit = outs3[-1]["lead"]["id"]
    again = tools.book_appointment(type("S", (), {"lead_id": lead_amit})(), "tomorrow 5 pm")
    print("Second booking for same lead ->", again)
    checks.append(("one visit per lead", again["booked"] is False and "Already booked" in again["error"]))

    # 4) Double booking must fail at DB level
    taken = db.dashboard_data()["appointments"][0]["slot"]
    ok, msg = db.book_slot(1, taken)
    print("\nDouble booking attempt:", ok, msg)
    checks.append(("no double booking", ok is False))
    # 5) Empty speech
    r = client.post("/api/call/start", json={"language": "en"}).json()
    e = client.post(f"/api/call/{r['call_id']}/message", json={"text": "   "}).json()
    print("Empty speech ->", e["reply"]); checks.append(("empty speech handled", "repeat" in e["reply"]))
    # 6) Do-not-call -> flag saved AND call ends automatically
    e = client.post(f"/api/call/{r['call_id']}/message", json={"text": "I'm not interested, please don't call me again"}).json()
    print("DNC ->", e["reply"], "| do_not_call =", e["lead"]["do_not_call"], "| end_call =", e["end_call"])
    checks += [("DNC flag", e["lead"]["do_not_call"] == 1), ("DNC ends call", e["end_call"] is True)]
    # 7) Unknown call id
    checks.append(("bad call id -> 404", client.post("/api/call/9999/message", json={"text": "hi"}).status_code == 404))
    # 8) Dashboard + pages
    d = client.get("/api/dashboard").json()
    print("\nDASHBOARD STATS:", d["stats"])
    checks.append(("dashboard counts calls", d["stats"]["total_calls"] >= 8))
    checks.append(("index page", client.get("/").status_code == 200))
    checks.append(("dashboard page", client.get("/dashboard").status_code == 200))

print("\n=== CHECKS ===")
for name, ok in checks:
    print(("PASS " if ok else "FAIL ") + name)
if os.path.exists(db.DB_PATH):
    os.remove(db.DB_PATH)
sys.exit(0 if all(ok for _, ok in checks) else 1)
