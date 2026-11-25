"""
agent.py - The "brain loop" of the sales agent.

One Session = one phone call. It holds the MEMORY of the call:
  - messages: the full conversation in OpenAI format (system, user, assistant, tool)
  - lead_id:  the CRM row for this caller (their saved details are shown to the
              LLM on every turn inside the system prompt)

handle_turn() is the agent loop:
  1. add the caller's sentence to memory
  2. ask the LLM what to do
  3. if it wants tools -> run them, add results to memory, go back to step 2
  4. if it replies with text -> that is what we speak back
"""
import json
import logging

import db
import llm
from tools import TOOL_SCHEMAS, run_tool

log = logging.getLogger("agent")

MAX_TOOL_STEPS = 6          # safety limit so a confused LLM can't loop forever
LANG_NAMES = {"en": "English", "hi": "Hindi (Devanagari script)"}

SYSTEM_PROMPT = """You are Riya, a warm, professional sales voice agent for SunNova Solar, a rooftop-solar installer in India.
You are on a live PHONE CALL, so:
- Keep every reply short: 1-3 sentences, ONE question at a time. No lists, no markdown, no emojis.
- Reply ONLY in {language}. Numbers like "Rs 1,85,000" are fine.

Your goals, in order:
1. Answer questions. For ANY fact (price, subsidy, EMI, warranty, process...) FIRST call search_kb, then answer only
   from its results. If search_kb finds nothing, say you'll have an expert call back. Never invent numbers.
2. Qualify the lead by naturally collecting: name, city, need (monthly bill or system size), budget, timeline.
   Ask for whatever is still missing (see LEAD RECORD). Do not ask again for details you already have.
3. Whenever the caller shares ANY detail (name, city, need, budget, timeline), call update_lead IN THAT SAME TURN
   with every new detail plus their current sentiment. You may call several tools at once.
   Do NOT ask for phone number or email: we already have the caller's number.
4. Once qualified (or when the caller asks), call check_slots and offer 3 slots numbered 1, 2, 3 (e.g. "1) Thu 26 Nov,
   12 PM"). The caller may answer with a number ("the second one") OR a time ("3 PM", "teen baje"): map it to the
   matching slot and call book_appointment with that exact slot value. If the time they want is not in the list,
   say so and offer the available ones. If the slot is taken, offer the alternatives returned.
5. If the caller says they are not interested or asks not to be called, call update_lead with do_not_call=true,
   then call end_call and say a polite goodbye.
6. Ending the call: when the caller says they have no more questions ("no", "nothing else", "that's all", "nahi",
   "bas"), do NOT ask "anything else?" again. Ask ONCE: "Shall I end the call now?" (in their language).
   If they confirm ("yes", "haan", "kar do", "cut it"), call end_call and say one short goodbye line.
   If they say no, ask how else you can help.

LEAD RECORD (what is already saved in the CRM): {lead}
CALLER LANGUAGE: {lang}"""

GREETING = {
    "en": "Hello! This is Riya from SunNova Solar. I can help you cut your electricity bill with rooftop solar. May I know your name, please?",
    "hi": "नमस्ते! मैं सननोवा सोलर से रिया बोल रही हूँ। मैं रूफटॉप सोलर से आपका बिजली बिल कम करने में मदद कर सकती हूँ। क्या मैं आपका नाम जान सकती हूँ?",
}
DIDNT_HEAR = {"en": "Sorry, I didn't catch that. Could you please repeat?",
              "hi": "माफ़ कीजिए, मुझे सुनाई नहीं दिया। क्या आप दोबारा बोल सकते हैं?"}
TECH_ISSUE = {"en": "Sorry, I'm having a small technical issue. Could you say that again?",
              "hi": "माफ़ कीजिए, थोड़ी तकनीकी दिक्कत है। क्या आप दोबारा बोल सकते हैं?"}


def text_for(table, lang):
    """Pick the text for this language; fall back to English if a language has no entry."""
    return table.get(lang, table["en"])


class Session:
    """Memory for one call."""

    def __init__(self, language="en"):
        self.language = language
        self.lead_id = db.create_lead(language)
        self.call_id = db.create_call(self.lead_id)
        self.messages = [{"role": "system", "content": ""}]
        self.messages.append({"role": "assistant", "content": text_for(GREETING, language)})
        self.events = []            # tool calls made, shown in the UI for transparency
        self.end_requested = False  # set by the end_call tool -> browser hangs up after the goodbye

    def refresh_system_prompt(self):
        """Put the latest CRM record + language into the system message every turn."""
        lead = db.get_lead(self.lead_id)
        visible = {k: lead[k] for k in ("name", "city", "need", "budget", "timeline", "score") if lead.get(k)}
        self.messages[0]["content"] = SYSTEM_PROMPT.format(
            language=LANG_NAMES.get(self.language, "English"), lang=self.language,
            lead=json.dumps(visible, ensure_ascii=False))


def handle_turn(session, user_text, language=None):
    """Process one thing the caller said. Returns {reply, events, lead}."""
    if language in LANG_NAMES:
        session.language = language
        db.update_lead(session.lead_id, {"language": language})
    user_text = (user_text or "").strip()
    if not user_text:                                   # empty speech / blank box
        return result(session, text_for(DIDNT_HEAR, session.language), [])

    session.messages.append({"role": "user", "content": user_text})
    turn_events = []
    try:
        for _ in range(MAX_TOOL_STEPS):
            session.refresh_system_prompt()
            out = llm.chat(session.messages, TOOL_SCHEMAS)

            if not out["tool_calls"]:                   # final answer -> speak it
                reply = out["content"] or text_for(TECH_ISSUE, session.language)
                session.messages.append({"role": "assistant", "content": reply})
                return result(session, reply, turn_events)

            # The LLM asked for tools: record the request in memory (OpenAI format)...
            session.messages.append({"role": "assistant", "content": out["content"], "tool_calls": [
                {"id": c["id"], "type": "function",
                 "function": {"name": c["name"], "arguments": json.dumps(c["arguments"], ensure_ascii=False)}}
                for c in out["tool_calls"]]})
            # ...run each tool and add its result to memory
            for c in out["tool_calls"]:
                res = run_tool(session, c["name"], c["arguments"])
                session.messages.append({"role": "tool", "tool_call_id": c["id"],
                                         "content": json.dumps(res, ensure_ascii=False)})
                turn_events.append({"tool": c["name"], "args": c["arguments"], "result": res})
        log.warning("Hit MAX_TOOL_STEPS without a final reply")
    except Exception:
        log.exception("[AGENT ERROR]")
    reply = text_for(TECH_ISSUE, session.language)
    session.messages.append({"role": "assistant", "content": reply})
    return result(session, reply, turn_events)


def result(session, reply, events):
    session.events += events
    return {"reply": reply, "events": events, "lead": db.get_lead(session.lead_id), "mode": llm.mode(),
            "end_call": session.end_requested}     # True -> browser speaks the goodbye, then hangs up


def transcript_text(session):
    """Readable transcript: only what was actually said (no tool messages)."""
    lead = db.get_lead(session.lead_id)
    header = "LEAD: " + ", ".join(f"{k}={lead[k]}" for k in ("name", "city", "need", "budget", "timeline", "score")
                                  if lead.get(k))
    lines = [header]
    for m in session.messages[1:]:
        if m["role"] in ("user", "assistant") and m.get("content"):
            lines.append(("Caller: " if m["role"] == "user" else "Agent: ") + m["content"])
    return "\n".join(lines)


def end_call(session):
    """Post-call job: summary + sentiment + insights -> CRM. (Production: run on a queue worker.)"""
    transcript = transcript_text(session)
    try:
        s = llm.summarize(transcript)
    except Exception:
        log.exception("[SUMMARY ERROR]")
        s = {"summary": "Summary unavailable.", "sentiment": "neutral", "insights": []}
    if s.get("sentiment") in ("positive", "neutral", "negative"):
        db.update_lead(session.lead_id, {"sentiment": s["sentiment"]})
    db.finish_call(session.call_id, transcript, s.get("summary", ""), s.get("insights", []))
    return {"summary": s.get("summary"), "insights": s.get("insights", []),
            "lead": db.get_lead(session.lead_id), "transcript": transcript}
