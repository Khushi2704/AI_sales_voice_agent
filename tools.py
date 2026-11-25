"""
tools.py - The "hands" of the agent.

The LLM cannot touch our database by itself. Instead we DESCRIBE some functions
to it (TOOL_SCHEMAS, a JSON description). When the LLM wants one, it replies with
"please call book_appointment with {slot: ...}". Our code (run_tool) runs the
real Python function and sends the result back. This is "tool calling".

Tools:
  search_kb        -> RAG lookup in kb.md
  update_lead      -> save what we learned about the caller into the CRM + rescore
  check_slots      -> list free site-visit slots
  book_appointment -> book one slot (no double booking)
  end_call         -> hang up after the caller confirms
"""
import json
import logging
import re
from datetime import datetime, timedelta

import db
import rag

log = logging.getLogger("tools")


# ---------- Lead scoring (rule based, easy to explain and change) ----------
def parse_budget_rupees(budget):
    """'2 lakh' -> 200000, '1.5L' -> 150000, '90k' -> 90000, '250000' -> 250000. None if unknown."""
    if not budget:
        return None
    text = budget.lower().replace(",", "")
    m = re.search(r"(\d+(?:\.\d+)?)\s*(lakh|lac|l\b|लाख|k\b|thousand|हज़ार|हजार)?", text)
    if not m:
        return None
    num, unit = float(m.group(1)), (m.group(2) or "")
    if unit in ("lakh", "lac", "l", "लाख"):
        return num * 100000
    if unit in ("k", "thousand", "हज़ार", "हजार"):
        return num * 1000
    return num if num > 1000 else None      # bare small numbers are ambiguous


def timeline_points(timeline):
    """2 points = buying within ~1 month, 1 point = within ~3 months, 0 = later/unknown."""
    if not timeline:
        return 0
    t = timeline.lower()
    if any(w in t for w in ["immediate", "asap", "urgent", "this week", "this month", "next week",
                            "jaldi", "turant", "abhi", "तुरंत", "जल्दी", "अभी"]):
        return 2
    m = re.search(r"(\d+)\s*(day|week|month|year|दिन|हफ्ते|हफ़्ते|महीने|महीना|साल)", t)
    if m:
        n, unit = int(m.group(1)), m.group(2)
        days = n * {"day": 1, "दिन": 1, "week": 7, "हफ्ते": 7, "हफ़्ते": 7,
                    "month": 30, "महीने": 30, "महीना": 30, "year": 365, "साल": 365}[unit]
        return 2 if days <= 31 else 1 if days <= 92 else 0
    if "next month" in t or "agle mahine" in t or "अगले महीने" in t:
        return 2
    return 0


def score_lead(lead):
    """HOT / WARM / COLD from budget + timeline + need.  >>> Change the rules here. <<<"""
    points = timeline_points(lead.get("timeline"))
    budget = parse_budget_rupees(lead.get("budget"))
    if budget and budget >= 120000:        # enough for at least a 2 kW system
        points += 2
    elif budget:
        points += 1
    if lead.get("need"):
        points += 1
    if points >= 4:
        return "hot"
    if points >= 2:
        return "warm"
    return "cold"


QUALIFY_FIELDS = ["name", "city", "need", "budget", "timeline"]   # questions the agent must ask


def missing_fields(lead):
    return [f for f in QUALIFY_FIELDS if not lead.get(f)]


# ---------- The tool functions ----------
def search_kb(session, query):
    results = rag.search(query, k=2)
    if not results:
        return {"found": False, "message": "No matching info in the knowledge base. Do not guess; offer a callback from an expert."}
    for r in results:                           # keywords line is only for matching; don't send it to the LLM
        r["text"] = re.sub(r"\nKeywords:.*", "", r["text"])
    return {"found": True, "results": results}


def update_lead(session, **fields):
    lead_id = session.lead_id
    if "do_not_call" in fields:
        fields["do_not_call"] = 1 if fields["do_not_call"] else 0
    lead = db.update_lead(lead_id, fields)
    # Re-score every time new info arrives
    status = "qualified" if not missing_fields(lead) and lead["status"] == "new" else lead["status"]
    lead = db.update_lead(lead_id, {"score": score_lead(lead), "status": status})
    short = {k: lead[k] for k in QUALIFY_FIELDS + ["score", "sentiment", "do_not_call", "status"]}  # fewer tokens
    return {"saved": True, "lead": short, "still_missing": missing_fields(lead)}


def friendly(slot):
    """'2026-11-26 15:00' -> 'Thu 26 Nov, 3 PM' (short and easy to speak)."""
    dt = datetime.strptime(slot, "%Y-%m-%d %H:%M")
    return dt.strftime("%a %d %b, ") + dt.strftime("%I:%M %p").lstrip("0").replace(":00", "")


# ---------- Understanding how a caller picks a slot ----------
# "first" / "2nd" / "teesra" / "3 PM" / "3 p.m." / "teen baje" / "tomorrow 5 pm" / "दोपहर 3 बजे"
ORDINALS = [["first", "1st", "pehla", "pehle", "pehli", "पहला", "पहले", "पहली", "option 1", "number 1", "slot 1"],
            ["second", "2nd", "dusra", "doosra", "dusre", "दूसरा", "दूसरे", "दूसरी", "option 2", "number 2", "slot 2"],
            ["third", "3rd", "teesra", "tisra", "teesre", "तीसरा", "तीसरे", "तीसरी", "option 3", "number 3", "slot 3"]]
NUMBER_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
                "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "ek": 1, "teen": 3, "char": 4, "chaar": 4,
                "paanch": 5, "panch": 5, "saat": 7, "aath": 8, "nau": 9, "das": 10, "gyarah": 11, "barah": 12,
                "एक": 1, "दो": 2, "तीन": 3, "चार": 4, "पांच": 5, "पाँच": 5, "सात": 7, "आठ": 8, "नौ": 9,
                "दस": 10, "ग्यारह": 11, "बारह": 12}
MORNING = ["am", "morning", "subah", "सुबह"]
AFTERNOON = ["pm", "afternoon", "evening", "dopahar", "dopehar", "shaam", "sham", "दोपहर", "शाम"]
WEEKDAYS = [["monday", "somvar", "सोमवार"], ["tuesday", "mangalvar", "मंगलवार"], ["wednesday", "budhvar", "बुधवार"],
            ["thursday", "guruvar", "गुरुवार"], ["friday", "shukravar", "शुक्रवार"], ["saturday", "shanivar", "शनिवार"]]


def parse_time(text):
    """Find a day and/or an hour in the caller's words. Returns (date or None, hour 0-23 or None)."""
    low = " " + text.lower().replace(".", "") + " "          # "3 p.m." -> "3 pm"
    for word, num in NUMBER_WORDS.items():                    # "teen baje" -> "3 baje"
        low = re.sub(rf"(?<![\wऀ-ॿ]){word}(?=\s*(baje|बजे|o'clock|oclock|am|pm))", str(num), low)
    hour = None
    m = re.search(r"(\d{1,2})(?::(\d\d))?\s*(am|pm|baje|बजे|o'clock|oclock)", low) or \
        re.search(r"(\d{1,2}):(\d\d)", low)                    # needs a marker or ":00", so "2nd" is not 2 o'clock
    if m:
        hour = int(m.group(1))
        is_pm = any(w in low for w in AFTERNOON)
        is_am = any(re.search(rf"(?<![a-z]){w}(?![a-z])", low) for w in MORNING)
        if is_pm and hour < 12:
            hour += 12
        elif not is_am and hour < 8:                          # "3 baje" in office hours means 3 PM
            hour += 12
    today, day = datetime.now().date(), None
    if any(w in low for w in ["day after tomorrow", "parso", "परसों"]):
        day = today + timedelta(days=2)
    elif any(w in low for w in ["tomorrow", " kal ", "कल"]):
        day = today + timedelta(days=1)
    else:
        for i, words in enumerate(WEEKDAYS):
            if any(w in low for w in words):
                day = today + timedelta(days=(i - today.weekday()) % 7 or 7)
    return day, hour


def resolve_slot(text, slots):
    """Turn the caller's words into one slot from `slots` (list of 'YYYY-MM-DD HH:MM'). None if unclear."""
    text = (text or "").strip()
    if text in slots:                                         # already an exact slot value
        return text
    low = text.lower().replace(".", "")                      # "3 p.m." -> "3 pm"
    for i, words in enumerate(ORDINALS):                      # "first", "2nd", "teesra", "पहला"...
        if any(w in low for w in words) and i < len(slots):
            return slots[i]
    if re.fullmatch(r"\D*\b([1-3])\b\D*", low) and not re.search(r"am|pm|baje|बजे|:", low):
        return slots[int(re.search(r"[1-3]", low).group()) - 1]   # a bare "2" = option 2
    day, hour = parse_time(text)
    if hour is None:
        return None
    for s in slots:                                           # first free slot matching the hour (and day)
        when = datetime.strptime(s, "%Y-%m-%d %H:%M")
        if when.hour == hour and (day is None or when.date() == day):
            return s
    return None


def check_slots(session, limit=3):          # offer only 3: easy to say and remember on a call
    free = db.free_slots()[:limit]
    if not free:
        return {"slots": [], "message": "No free slots in the next few days. Offer a callback."}
    return {"slots": [{"slot": s, "label": friendly(s)} for s in free]}


def book_appointment(session, slot):
    # Business rule: one site visit per lead (also protects against an LLM booking twice by mistake)
    existing = db.lead_booking(session.lead_id)
    if existing:
        return {"booked": False, "error": f"Already booked for {friendly(existing)}. Do not book again.",
                "existing_booking": friendly(existing)}
    # The LLM should send an exact slot, but if it sends the caller's words ("3 PM", "the second one")
    # we translate them here, so booking by time or by number always works.
    if slot not in db.all_slots():
        slot = resolve_slot(slot, db.free_slots()) or slot
    ok, msg = db.book_slot(session.lead_id, slot)
    if ok:
        return {"booked": True, "slot": slot, "label": friendly(slot)}
    # Double booking / invalid slot -> return alternatives so the agent can recover
    return {"booked": False, "error": msg, "alternatives": check_slots(session, 3)["slots"]}


def end_call(session):
    """The caller confirmed they want to hang up. The browser ends the call after the goodbye is spoken."""
    session.end_requested = True
    return {"ending": True}


TOOLS = {
    "search_kb": search_kb,
    "update_lead": update_lead,
    "check_slots": check_slots,
    "book_appointment": book_appointment,
    "end_call": end_call,
}


def run_tool(session, name, args):
    """Run a tool safely. Any error becomes a message for the LLM instead of a crash."""
    log.info("[TOOL] %s args=%s", name, args)
    try:
        if name not in TOOLS:
            raise ValueError(f"Unknown tool {name}")
        result = TOOLS[name](session, **args)
    except Exception as e:                      # bad args, DB error, etc.
        log.exception("[TOOL ERROR] %s", name)
        result = {"error": f"{type(e).__name__}: {e}"}
    log.info("[TOOL RESULT] %s -> %s", name, json.dumps(result, ensure_ascii=False)[:300])
    return result


# ---------- JSON descriptions the LLM sees (OpenAI "tools" format) ----------
TOOL_SCHEMAS = [
    {"type": "function", "function": {
        "name": "search_kb",
        "description": "Search the SunNova knowledge base (prices, subsidy, EMI, warranty, installation, FAQs). "
                       "ALWAYS call this before answering any factual question. Write the query in English.",
        "parameters": {"type": "object", "properties": {
            "query": {"type": "string", "description": "Short English search query, e.g. 'subsidy for 3 kW'"}},
            "required": ["query"]}}},
    {"type": "function", "function": {
        "name": "update_lead",
        "description": "Save details the caller shared into the CRM. Call it as soon as you learn ANY detail. "
                       "Store values in English (e.g. timeline 'within 1 month', budget '2 lakh').",
        "parameters": {"type": "object", "properties": {
            "name": {"type": "string"},
            "phone": {"type": "string"},
            "city": {"type": "string"},
            "need": {"type": "string", "description": "System size or monthly bill, e.g. '3 kW' or 'bill Rs 3000/month'"},
            "budget": {"type": "string", "description": "e.g. '2 lakh'"},
            "timeline": {"type": "string", "description": "When they want to install, e.g. 'within 1 month'"},
            "sentiment": {"type": "string", "enum": ["positive", "neutral", "negative"],
                          "description": "Caller's current mood"},
            "do_not_call": {"type": "boolean", "description": "True if the caller asks not to be called again"}},
            "required": []}}},
    {"type": "function", "function": {
        "name": "check_slots",
        "description": "Get free site-visit slots. Call before offering times to the caller.",
        "parameters": {"type": "object", "properties": {}, "required": []}}},
    {"type": "function", "function": {
        "name": "book_appointment",
        "description": "Book a site visit. Pass the exact 'slot' value from check_slots (format 'YYYY-MM-DD HH:MM') "
                       "that matches the caller's choice, whether they said a number ('the second one') or a time ('3 PM').",
        "parameters": {"type": "object", "properties": {
            "slot": {"type": "string"}}, "required": ["slot"]}}},
    {"type": "function", "function": {
        "name": "end_call",
        "description": "Hang up the call. ONLY call this after the caller confirmed they want to end the call "
                       "(or asked not to be called). Then say one short goodbye line.",
        "parameters": {"type": "object", "properties": {}, "required": []}}},
]
