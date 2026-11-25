"""
fallback.py - A simple rule-based "brain" used when the LLM API is unavailable
(no API key, no internet, quota error, timeout).

It reads the SAME message history the LLM would read, and returns the SAME shape
as llm.chat(): {"content": ..., "tool_calls": [...]}. So the agent loop, tools,
CRM and dashboard all keep working. It is far less smart than an LLM (keyword
rules + regex), but it guarantees the demo never dies.
"""
import json
import re
import uuid

import tools          # shared slot reader (resolve_slot / parse_time)

# ---------- Text templates (English / Hindi) ----------
T = {
    "en": {
        "name": "May I know your name, please?",
        "city": "Which city is your home or business in?",
        "need": "What is your average monthly electricity bill, or what system size do you want?",
        "budget": "What budget do you have in mind for the solar system?",
        "timeline": "When are you planning to get it installed?",
        "thanks": "Thank you, {name}.",
        "ok": "Got it.",
        "slots": "I can book a free site visit for you. Available slots: {list}. Which one works for you? You can say the number or the time.",
        "booked": "Done! Your free site visit is booked for {label}. Our engineer will call you before coming. Anything else I can help with?",
        "taken": "Sorry, that slot is not available. Free slots: {list}. Which one should I book?",
        "noslot": "Sorry, all slots are full for the next few days. Our team will call you back to schedule.",
        "kb": "Here is what I can tell you: {facts}",
        "nokb": "I don't have that information right now. I'll ask an expert to call you back.",
        "dnc": "Understood. We will not call you again. Thank you for your time and have a nice day!",
        "done": "Is there anything else you would like to know?",
        "pick": "Which slot works for you? Just say first, second or third, or a time like 3 PM.",
        "notavail": "Sorry, {time} is not available. Available slots: {list}. Which one should I book?",
        "ask_end": "Glad I could help! Shall I end the call now?",
        "continue": "Sure! What else can I help you with?",
        "bye": "Thank you for your time. Have a great day, goodbye!",
    },
    "hi": {
        "name": "क्या मैं आपका नाम जान सकती हूँ?",
        "city": "आपका घर या बिज़नेस किस शहर में है?",
        "need": "आपका महीने का बिजली बिल लगभग कितना आता है, या आपको कितने किलोवाट का सिस्टम चाहिए?",
        "budget": "सोलर सिस्टम के लिए आपका बजट कितना है?",
        "timeline": "आप इसे कब तक लगवाना चाहते हैं?",
        "thanks": "धन्यवाद, {name}।",
        "ok": "ठीक है।",
        "slots": "मैं आपके लिए मुफ़्त साइट विज़िट बुक कर सकती हूँ। उपलब्ध समय: {list}. आपके लिए कौन सा ठीक रहेगा? आप नंबर या समय बोल सकते हैं।",
        "booked": "हो गया! आपकी मुफ़्त साइट विज़िट {label} के लिए बुक हो गई है। हमारे इंजीनियर आने से पहले आपको कॉल करेंगे। और कुछ मदद करूँ?",
        "taken": "माफ़ कीजिए, वह समय उपलब्ध नहीं है। खाली समय: {list}. कौन सा बुक करूँ?",
        "noslot": "माफ़ कीजिए, अगले कुछ दिनों के सभी स्लॉट भरे हैं। हमारी टीम आपको कॉल करेगी।",
        "kb": "हमारी जानकारी के अनुसार: {facts}",
        "nokb": "अभी मेरे पास यह जानकारी नहीं है। हमारे विशेषज्ञ आपको कॉल करेंगे।",
        "dnc": "ठीक है, हम आपको दोबारा कॉल नहीं करेंगे। आपके समय के लिए धन्यवाद!",
        "done": "क्या आप कुछ और जानना चाहेंगे?",
        "pick": "कौन सा समय ठीक रहेगा? पहला, दूसरा या तीसरा बोलिए, या कोई समय जैसे 3 बजे।",
        "notavail": "माफ़ कीजिए, {time} खाली नहीं है। खाली समय: {list}. कौन सा बुक करूँ?",
        "ask_end": "आपसे बात करके अच्छा लगा! क्या मैं कॉल समाप्त कर दूँ?",
        "continue": "ज़रूर! बताइए, मैं और क्या मदद कर सकती हूँ?",
        "bye": "आपके समय के लिए धन्यवाद। आपका दिन शुभ हो, नमस्ते!",
    },
}
QUALIFY = ["name", "city", "need", "budget", "timeline"]
CITIES = {"delhi": "Delhi", "दिल्ली": "Delhi", "noida": "Noida", "नोएडा": "Noida", "gurgaon": "Gurgaon",
          "gurugram": "Gurgaon", "गुड़गांव": "Gurgaon", "jaipur": "Jaipur", "जयपुर": "Jaipur",
          "chandigarh": "Chandigarh", "चंडीगढ़": "Chandigarh", "lucknow": "Lucknow", "लखनऊ": "Lucknow",
          "pune": "Pune", "पुणे": "Pune", "ahmedabad": "Ahmedabad", "अहमदाबाद": "Ahmedabad",
          "mumbai": "Mumbai", "मुंबई": "Mumbai", "ludhiana": "Ludhiana", "लुधियाना": "Ludhiana"}
QUESTION_WORDS = ["?", "what", "how", "which", "does", "do you", "can i", "is there", "tell me", "kya", "kitna",
                  "kitni", "kaise", "क्या", "कितना", "कितनी", "कैसे", "बताइए", "price", "cost", "subsidy",
                  "emi", "loan", "warranty", "कीमत", "सब्सिडी", "लोन", "वारंटी", "ईएमआई"]
POSITIVE = ["great", "good", "interested", "thank", "nice", "perfect", "sure", "अच्छा", "बढ़िया", "धन्यवाद", "ठीक"]
NEGATIVE = ["expensive", "costly", "not interested", "bad", "worried", "angry", "waste", "महंगा", "बेकार", "परेशान"]
DNC = ["don't call", "do not call", "dont call", "stop calling", "not interested", "call mat", "कॉल मत", "फोन मत"]
# End-of-call understanding. MARKERS = phrases in OUR previous question; the rest = caller's answer.
ANYTHING_ELSE_MARKERS = ["anything else", "what else", "और कुछ", "कुछ और", "और क्या"]
ASK_END_MARKERS = ["end the call", "कॉल समाप्त"]
YES = r"\b(yes|yeah|yep|yup|sure|ok|okay|haan|han|haa|ji|please|go ahead|bilkul)\b|हाँ|हां|जी|ठीक है|बिल्कुल"
STRONG_YES = r"\b(cut|end|kar do|kardo|kar dijiye|hang up)\b|काट|कर दो|कर दीजिए|समाप्त"
NO_MORE = (r"\b(no|nope|nah|nothing|nahi|nahin|nai|that's all|thats all|that is all|bas|bye|goodbye|"
           r"thank you|thanks|shukriya|dhanyavad)\b|नहीं|नही|बस|अलविदा|धन्यवाद|शुक्रिया")
NOT_NAMES = {"from", "looking", "interested", "planning", "not", "in", "a", "the", "calling", "fine", "ok"}


# ---------- Reading the conversation ----------
def language(messages):
    m = re.search(r"CALLER LANGUAGE:\s*(\w+)", messages[0]["content"])
    return "hi" if m and m.group(1) == "hi" else "en"


def tool_results(messages, since=0):
    """List of (tool_name, result_dict) found in messages[since:]."""
    names, out = {}, []
    for m in messages[since:]:
        for tc in m.get("tool_calls") or []:
            names[tc["id"]] = tc["function"]["name"]
        if m["role"] == "tool":
            out.append((names.get(m["tool_call_id"], "?"), json.loads(m["content"])))
    return out


def state(messages):
    """What do we know so far? Latest lead record, offered slots, booking status."""
    s = {"lead": {}, "slots": None, "booked": False, "dnc": False}
    for name, res in tool_results(messages):
        if name == "update_lead" and res.get("lead"):
            s["lead"] = res["lead"]
            s["dnc"] = bool(res["lead"].get("do_not_call"))
        elif name == "check_slots":
            s["slots"] = res.get("slots") or []
        elif name == "book_appointment":
            if res.get("booked"):
                s["booked"] = True
            else:
                s["slots"] = res.get("alternatives") or []
    return s


# ---------- Understanding the user's words (regex rules) ----------
def extract_fields(text, expected):
    t, low = text.strip(), text.lower()
    f = {}
    m = re.search(r"(?:my name is|i am|i'm|this is|mera naam|मेरा नाम)\s+([A-Za-zऀ-ॿ]+)", t, re.I)
    if m and m.group(1).lower() not in NOT_NAMES:
        f["name"] = m.group(1).strip().title()
    for key, city in CITIES.items():
        if key in low:
            f["city"] = city
    m = re.search(r"(\d+(?:\.\d+)?)\s*(?:kw|kilowatt|किलोवाट)", low)
    if m:
        f["need"] = f"{m.group(1)} kW"
    m = re.search(r"bill[^\d]{0,20}(\d[\d,]*)|(\d[\d,]*)\s*(?:rs|rupees|रुपये)?\s*(?:ka )?(?:bill|बिल)", low)
    if m and "need" not in f:
        f["need"] = f"bill Rs {m.group(1) or m.group(2)}/month"
    m = re.search(r"(\d+(?:\.\d+)?)\s*(lakh|lac|लाख|k\b|thousand|हज़ार|हजार)", low)
    if m:
        f["budget"] = f"{m.group(1)} {m.group(2)}"
    m = re.search(r"(\d+)\s*(days?|weeks?|months?|years?|दिन|हफ्ते|महीने|महीना|साल)", low)
    if m:
        f["timeline"] = f"within {m.group(1)} {m.group(2)}"
    for w in ["immediately", "asap", "next month", "this month", "next week", "jaldi", "turant",
              "तुरंत", "जल्दी", "अगले महीने"]:
        if w in low and "timeline" not in f:
            f["timeline"] = w
    # Short answer to the question we just asked -> store it in that field
    if not f and expected and len(t.split()) <= 6 and not is_question(t):
        f[expected] = t.title() if expected in ("name", "city") else t
    if any(w in low for w in NEGATIVE):
        f["sentiment"] = "negative"
    elif any(w in low for w in POSITIVE):
        f["sentiment"] = "positive"
    if any(w in low for w in DNC):
        f["do_not_call"] = True
    return f


def says(pattern, text):
    return re.search(pattern, text.lower()) is not None


def last_agent_line(messages, before):
    """The last thing the agent SAID before the caller's latest message."""
    for m in reversed(messages[:before]):
        if m["role"] == "assistant" and m.get("content"):
            return m["content"].lower()
    return ""


def is_question(text):
    low = text.lower()
    return any(w in low for w in QUESTION_WORDS)


# ---------- Main entry: decide the next action ----------
def plan(user_text, st, prev=""):
    """Which tools should run for this user message?
    Returns (list of (tool, args), note). note = a fixed reply to use, e.g. "ask_end"."""
    actions = []
    question = is_question(user_text)
    # --- We asked "Shall I end the call?" -> yes = hang up, no = keep helping ---
    if any(m in prev for m in ASK_END_MARKERS) and not question:
        if says(STRONG_YES, user_text) or (says(YES, user_text) and not says(NO_MORE, user_text)):
            return [("end_call", {})], None
        if says(NO_MORE, user_text):
            return [], "continue"
    # --- We asked "Anything else?" -> "no / that's all" = ask ONCE whether to end the call ---
    if any(m in prev for m in ANYTHING_ELSE_MARKERS) and not question:
        if says(NO_MORE, user_text):
            return [], "ask_end"
        if says(YES, user_text) and len(user_text.split()) <= 3:
            return [], "continue"
    missing = [f for f in QUALIFY if not st["lead"].get(f)]
    fields = extract_fields(user_text, missing[0] if missing else None)
    if fields:
        actions.append(("update_lead", fields))
    if fields.get("do_not_call"):
        return actions + [("end_call", {})], None          # opted out -> say goodbye and hang up
    if st["slots"] and not st["booked"]:
        offered = [s["slot"] for s in st["slots"]]
        slot = tools.resolve_slot(user_text, offered)     # "2nd" / "3 PM" / "teen baje" ...
        if not slot and says(YES, user_text) and not question:
            slot = offered[0]                             # plain "yes" = the first slot
        if slot:
            actions.append(("book_appointment", {"slot": slot}))
            return actions, None
        day, hour = tools.parse_time(user_text)
        if hour is not None:                              # asked for a time we don't have
            return actions, ("notavail", hour)
    if question:
        actions.append(("search_kb", {"query": user_text}))
    still_missing = [f for f in missing if f not in fields]
    wants_visit = any(w in user_text.lower() for w in ["visit", "appointment", "book", "विज़िट", "बुक"])
    if (not still_missing or wants_visit) and not st["booked"] and not st["slots"]:
        actions.append(("check_slots", {}))
    return actions, None


def chat(messages):
    lang = language(messages)
    last_user = max(i for i, m in enumerate(messages) if m["role"] == "user")
    user_text = messages[last_user]["content"]
    done = [name for name, _ in tool_results(messages, since=last_user)]
    st_before = state(messages[:last_user])
    actions, note = plan(user_text, st_before, last_agent_line(messages, last_user))
    # 1) Run the next planned tool that hasn't run yet
    for name, args in actions:
        if name not in done:
            return {"content": None, "tool_calls": [{"id": "fb_" + uuid.uuid4().hex[:8], "name": name, "arguments": args}]}
    # 2) All tools done -> write the reply from their results
    return {"content": compose_reply(messages, last_user, lang, note), "tool_calls": []}


def compose_reply(messages, last_user, lang, note=None):
    t, st = T[lang], state(messages)
    if note in ("ask_end", "continue"):
        return t[note]
    parts = []
    for name, res in tool_results(messages, since=last_user):
        if name == "search_kb":
            parts.append(t["kb"].format(facts=facts(res)) if res.get("found") else t["nokb"])
        elif name == "update_lead":
            if st["dnc"]:
                return t["dnc"]
            # Say the name only in the turn we learned it; otherwise a short acknowledgement
            if learned_name(messages, last_user):
                parts.append(t["thanks"].format(name=res["lead"]["name"]))
            else:
                parts.append(t["ok"])
        elif name == "check_slots" or (name == "book_appointment" and not res.get("booked")):
            slots = res.get("slots") or res.get("alternatives") or []
            listing = ", ".join(f"{i + 1}) {s['label']}" for i, s in enumerate(slots[:3]))
            key = "taken" if name == "book_appointment" else "slots"
            parts.append(t[key].format(list=listing) if slots else t["noslot"])
            return " ".join(parts)
        elif name == "book_appointment":
            parts.append(t["booked"].format(label=res["label"]))
            return " ".join(parts)
        elif name == "end_call":
            return t["bye"]
    if isinstance(note, tuple) and note[0] == "notavail":       # e.g. caller asked for 2 PM
        h = note[1]
        time_txt = f"{h % 12 or 12} {'AM' if h < 12 else 'PM'}"
        listing = ", ".join(f"{i + 1}) {s['label']}" for i, s in enumerate(st["slots"][:3]))
        return " ".join(parts + [t["notavail"].format(time=time_txt, list=listing)])
    # Ask the next qualification question (or offer help)
    missing = [f for f in QUALIFY if not st["lead"].get(f)]
    if missing:
        parts.append(t[missing[0]])
    elif st["slots"] and not st["booked"]:
        parts.append(t["pick"])
    else:
        parts.append(t["done"])
    return " ".join(parts).strip()


def learned_name(messages, since):
    """Did an update_lead call in this turn save the caller's name?"""
    for m in messages[since:]:
        for tc in m.get("tool_calls") or []:
            if json.loads(tc["function"]["arguments"]).get("name"):
                return True
    return False


def facts(res):
    """First ~280 characters of the best KB chunk, cut at a sentence end."""
    text = re.sub(r"\nKeywords:.*", "", res["results"][0]["text"]).replace("\n", " ")
    out = ""
    for sent in re.split(r"(?<=[.!?])\s+", text):
        if len(out) + len(sent) > 280 and out:
            break
        out += sent + " "
    return out.strip()


# ---------- Post-call summary without an LLM ----------
TOPICS = {"price": "pricing", "cost": "pricing", "कीमत": "pricing", "subsidy": "subsidy", "सब्सिडी": "subsidy",
          "emi": "EMI/financing", "loan": "EMI/financing", "warranty": "warranty", "वारंटी": "warranty",
          "battery": "battery backup", "power cut": "power cuts", "payback": "savings/payback"}


def summarize(transcript):
    low = transcript.lower()
    caller = " ".join(l for l in low.splitlines() if l.startswith("caller:"))
    topics = sorted({v for k, v in TOPICS.items() if k in caller})
    booked = "site visit is booked" in low or "बुक हो गई" in low
    neg = sum(w in caller for w in NEGATIVE)
    pos = sum(w in caller for w in POSITIVE)
    sentiment = "negative" if neg > pos else "positive" if pos or booked else "neutral"
    lead_line = next((l for l in transcript.splitlines() if l.startswith("LEAD:")), "LEAD: unknown")
    summary = (f"{lead_line[5:].strip()}. Caller asked about {', '.join(topics) or 'general information'}. "
               f"Outcome: {'site visit booked' if booked else 'no booking yet'}.")
    insights = [f"Interest areas: {', '.join(topics)}" if topics else "No specific product questions asked",
                "Objection raised (price/concern) - follow up with EMI + subsidy" if neg else "No strong objections",
                "Next action: engineer site visit" if booked else "Next action: sales follow-up call in 2 days"]
    return {"summary": summary, "sentiment": sentiment, "insights": insights}
