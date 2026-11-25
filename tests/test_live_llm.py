"""
tests/test_live_llm.py - Runs a full call against the REAL LLM configured in .env (Groq / OpenAI).
Run:  python -m tests.test_live_llm        (uses some of your API quota: ~15-25 requests)
Prints every turn so you can read how the agent behaves before the demo.
"""
import os
import sys
import time

PAUSE = float(os.getenv("LIVE_PAUSE", "8"))   # seconds between turns, like a real caller speaking

import db
db.DB_PATH = "test_live.db"
if os.path.exists(db.DB_PATH):
    os.remove(db.DB_PATH)
db.init_db()
db.seed_if_empty()

import agent
import llm

if not llm.client:
    sys.exit("No API key found in .env - nothing to test.")


def call(lang, lines):
    s = agent.Session(lang)
    print(f"\n=== {lang.upper()} call, model {llm.MODEL} ===\nAgent : {agent.text_for(agent.GREETING, lang)}")
    outs = []
    for line in lines:
        time.sleep(PAUSE)
        out = agent.handle_turn(s, line, lang)
        tools = ", ".join(f"{e['tool']}{e['args'] if e['tool'] == 'book_appointment' else ''}" for e in out["events"])
        print(f"Caller: {line}\n   [{out['mode']}] [tools: {tools or '-'}]{'  [END_CALL]' if out['end_call'] else ''}"
              f"\nAgent : {out['reply']}")
        outs.append(out)
        if out["end_call"]:
            break
    return s, outs


checks = []
s, outs = call("en", ["Hi, I'm Rahul from Delhi. How much subsidy do I get for a 3 kW system?",
                      "My budget is around 2 lakh and I want it within a month.",
                      "Can you book a site visit?",
                      "3 p.m. please",
                      "No, that's all, thanks.",
                      "Yes, please end it."])
lead = db.get_lead(s.lead_id)
llm_turns = sum(o["mode"].startswith("openai") for o in outs)
print(f"\nEN: {llm_turns}/{len(outs)} turns answered by the LLM")
checks += [("EN: every turn answered by the LLM", llm_turns == len(outs)),
           ("EN: booked", lead["status"] == "booked"),
           ("EN: call ended by agent", outs[-1]["end_call"] is True)]
appt = [a for a in db.dashboard_data()["appointments"] if a["lead_id"] == s.lead_id]
checks.append(("EN: booked the 3 PM slot", bool(appt) and appt[0]["slot"].endswith("15:00")))

s2, outs2 = call("hi", ["मेरा नाम प्रिया है, मैं जयपुर से हूँ। 5 किलोवाट का सिस्टम चाहिए।",
                        "बजट 3 लाख है और अगले महीने लगवाना है। साइट विज़िट बुक कर दीजिए।",
                        "दूसरा वाला",
                        "नहीं, बस इतना ही।",
                        "हाँ, कॉल काट दो।"])
checks += [("HI: booked", db.get_lead(s2.lead_id)["status"] == "booked"),
           ("HI: call ended by agent", outs2[-1]["end_call"] is True)]

print("\n=== CHECKS ===")
for n, ok in checks:
    print(("PASS " if ok else "FAIL ") + n)
os.remove(db.DB_PATH)
