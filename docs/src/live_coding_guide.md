# Live Coding Guide: how to change the project in the interview

**Golden rules while coding live**
1. Say what you will change and why **before** typing ("Scoring rules live in `tools.score_lead`, so I'll edit only that").
2. Make the smallest change, run it, and show it working (browser + terminal logs).
3. `uvicorn main:app --reload` restarts the server automatically when a `.py` file changes. After editing `kb.md` or the DB schema, restart manually (and delete `crm.db` after schema changes; it re-seeds).
4. Quick checks: `python -m tests.test_flow` (whole workflow) and `python rag.py` (retrieval).
5. Line numbers below are for the current code (rebuild this PDF with `python docs/build_docs.py` after big edits).

**Where things live (memorise this map)**

| I want to change... | File / place |
|---|---|
| Agent personality, rules, goals | `agent.py` SYSTEM_PROMPT ({{L:agent.py:SYSTEM_PROMPT = }}) |
| Greeting / languages | `agent.py` LANG_NAMES ({{L:agent.py:LANG_NAMES = }}), GREETING ({{L:agent.py:GREETING = {}}); `static/index.html` LANGS |
| Questions the agent must ask | `tools.py` QUALIFY_FIELDS ({{L:tools.py:QUALIFY_FIELDS = }}) |
| Lead scoring rules | `tools.py` score_lead ({{L:tools.py:def score_lead}}) |
| Tools (add/modify) | `tools.py` functions, TOOLS dict ({{L:tools.py:TOOLS = {}}), TOOL_SCHEMAS ({{L:tools.py:TOOL_SCHEMAS = [}}) |
| Slot times / days | `db.py` SLOT_TIMES ({{L:db.py:SLOT_TIMES = }}), DAYS_AHEAD ({{L:db.py:DAYS_AHEAD = }}) |
| Database columns | `db.py` CREATE TABLE ({{L:db.py:CREATE TABLE IF NOT EXISTS leads}}), LEAD_FIELDS ({{L:db.py:LEAD_FIELDS = }}) |
| Dashboard numbers | `db.py` dashboard_data ({{L:db.py:def dashboard_data}}); `static/dashboard.html` |
| Model / provider | `.env` file (OPENAI_MODEL, comma list = fallback chain); `llm.py` MODELS ({{L:llm.py:MODELS = }}), BASE_URL ({{L:llm.py:BASE_URL = }}) |
| How callers pick a slot ("3 PM", "2nd") | `tools.py` resolve_slot ({{L:tools.py:def resolve_slot}}), parse_time ({{L:tools.py:def parse_time}}) |
| Ending the call | SYSTEM_PROMPT rule 6; `tools.end_call` ({{L:tools.py:def end_call}}); `pendingEnd` in index.html |
| Summary format | `llm.py` SUMMARY_PROMPT ({{L:llm.py:SUMMARY_PROMPT = }}) |
| Knowledge | `kb.md` (one `##` section per topic) |
| Voice, speed, mic | `static/index.html` speak() ({{L:static/index.html:function speak}}), pickVoice ({{L:static/index.html:function pickVoice}}) |
| Offline brain | `fallback.py` QUALIFY ({{L:fallback.py:QUALIFY = }}), templates T ({{L:fallback.py:T = {}}) |

## 1. Add a new qualification question (example: roof type)

Goal: the agent should also ask "Is your roof concrete (RCC) or tin sheet?" and save it.

**a) Database**: `db.py`, add a column in CREATE TABLE ({{L:db.py:CREATE TABLE IF NOT EXISTS leads}}) and in LEAD_FIELDS ({{L:db.py:LEAD_FIELDS = }}):
```
            timeline    TEXT,      -- e.g. "within 1 month"
            roof_type   TEXT,      -- NEW: "RCC" / "tin sheet"
```
```
LEAD_FIELDS = ["name", "phone", "city", "need", "budget", "timeline", "roof_type",
               "language", "score", "sentiment", "do_not_call", "status"]
```
Then stop the server, **delete `crm.db`**, and start again (or run `ALTER TABLE leads ADD COLUMN roof_type TEXT` in SQLite).

**b) Tell the agent to ask it**: `tools.py` QUALIFY_FIELDS ({{L:tools.py:QUALIFY_FIELDS = }}):
```
QUALIFY_FIELDS = ["name", "city", "need", "budget", "timeline", "roof_type"]
```
and add a property to the `update_lead` schema inside TOOL_SCHEMAS ({{L:tools.py:"name": "update_lead",}}):
```
            "roof_type": {"type": "string", "description": "Roof type, e.g. 'RCC' or 'tin sheet'"},
```
**c) Prompt + memory**: `agent.py`, in SYSTEM_PROMPT goal 2 add "roof type" to the list, and in `refresh_system_prompt` ({{L:agent.py:visible = }}) add `"roof_type"` to the tuple of visible fields.

**d) Offline brain** (important, or the fallback raises KeyError): `fallback.py` add to QUALIFY ({{L:fallback.py:QUALIFY = }}) and a question in both templates:
```
QUALIFY = ["name", "city", "need", "budget", "timeline", "roof_type"]
        "roof_type": "Is your roof concrete (RCC) or tin sheet?",          # in T["en"]
        "roof_type": "Aapki chhat pakki (RCC) hai ya tin shed?",           # in T["hi"] (use Devanagari)
```
**e) Show it**: add a dashboard column (see recipe 7) and a row in `showLead()` in `static/index.html`: `row("Roof", esc(l.roof_type)) +`.

## 2. Change the lead-scoring rules

All rules are in `tools.score_lead` ({{L:tools.py:def score_lead}}). Example: "leads outside our service cities are always COLD, and budget >= 3 lakh is an automatic HOT":
```
SERVICE_CITIES = {"delhi", "noida", "gurgaon", "jaipur", "chandigarh", "lucknow", "pune", "ahmedabad"}

def score_lead(lead):
    city = (lead.get("city") or "").lower()
    if city and city not in SERVICE_CITIES:
        return "cold"                                   # we cannot install there
    budget = parse_budget_rupees(lead.get("budget"))
    if budget and budget >= 300000:
        return "hot"
    points = timeline_points(lead.get("timeline"))
    ...  # keep the rest as it is
```
Explain: "Scoring is deterministic Python, not LLM, so it is predictable and auditable. The LLM only extracts the facts."
Test quickly: `python -c "import tools; print(tools.score_lead({'city':'Surat','budget':'5 lakh'}))"` gives `cold`.

## 3. Add a new language (Punjabi)

**a) Backend**: `agent.py` LANG_NAMES ({{L:agent.py:LANG_NAMES = }}) and GREETING ({{L:agent.py:GREETING = {}}):
```
LANG_NAMES = {"en": "English", "hi": "Hindi (Devanagari script)", "pa": "Punjabi (Gurmukhi script)"}
GREETING = {
    ...,
    "pa": "Sat Sri Akal! Main SunNova Solar ton Riya bol rahi haan. Ki main tuhada naam jaan sakdi haan?",
}
```
(Better: write the greeting in Gurmukhi script so the TTS voice pronounces it well. The LLM will reply in Gurmukhi because the prompt says so.)
**b) Frontend**: `static/index.html`, add to LANGS ({{L:static/index.html:const LANGS = {}}) and to the `<select>`:
```
  pa: { speech: "pa-IN", label: "Punjabi" },
          <option value="pa">Punjabi</option>
```
Missing texts (DIDNT_HEAR, TECH_ISSUE) fall back to English automatically via `text_for()`. The offline fallback answers in English for Punjabi. Say: "Chrome STT supports pa-IN; if no Punjabi TTS voice is installed, the browser uses a default voice. In production I'd use a neural TTS with Punjabi (Google/Azure)."

## 4. Change the TTS voice or speed

`static/index.html` speak() ({{L:static/index.html:function speak}}):
```
  u.rate = parseFloat($("rate").value);   // 1 = normal; slider default is value="1" on the <input id="rate">
  u.pitch = 1.1;                          // NEW: slightly higher pitch (0 to 2)
```
To pick a specific voice, first list voices in the browser console (F12):
`speechSynthesis.getVoices().map(v => v.name + " | " + v.lang)`, then change pickVoice ({{L:static/index.html:function pickVoice}}):
```
  return voices.find(v => v.name === "Microsoft Heera - English (India)") || voices.find(v => v.lang === langCode) ...
```
Default speed: change `value="1"` to `value="0.9"` on the slider input.

## 5. Add a new tool (send_whatsapp_confirmation)

Three places in `tools.py` + one line in the prompt.
**a) The function** (put it above `TOOLS = {`, {{L:tools.py:TOOLS = {}}):
```
def send_whatsapp_confirmation(session, phone, message):
    """MOCK: logs the WhatsApp message. Production: WhatsApp Cloud API or Twilio, with an approved template."""
    if not re.fullmatch(r"\+?\d{10,13}", phone.replace(" ", "")):
        return {"sent": False, "error": "Invalid phone number, ask the caller again."}
    db.update_lead(session.lead_id, {"phone": phone})
    log.info("[WHATSAPP] to %s: %s", phone, message)
    return {"sent": True, "to": phone}
```
**b) Register it** in TOOLS: `"send_whatsapp_confirmation": send_whatsapp_confirmation,`
**c) Describe it** to the LLM, append to TOOL_SCHEMAS:
```
    {"type": "function", "function": {
        "name": "send_whatsapp_confirmation",
        "description": "Send the booking confirmation on WhatsApp. Call right after a successful booking.",
        "parameters": {"type": "object", "properties": {
            "phone": {"type": "string", "description": "Caller's 10-digit mobile number"},
            "message": {"type": "string", "description": "Short confirmation with date and time"}},
            "required": ["phone", "message"]}}},
```
**d) Prompt**: in SYSTEM_PROMPT goal 4 add: "After booking, ask for their WhatsApp number and call send_whatsapp_confirmation."
Show it: make a booking, give a number, and point at the `[WHATSAPP]` log line and the tool log in the UI.

## 6. Add a new knowledge-base document

Append a section to `kb.md` (keep the `## ` heading and a Keywords line):
```
## Battery storage
Hybrid systems with a lithium battery keep lights and fans running during power cuts.
A 5 kWh battery costs about Rs 70,000 to 90,000 extra and has a 6 to 8 year warranty.
Keywords: battery, backup, power cut, inverter battery, lithium, bijli jaane par
```
Restart the server (the index is built at startup). Verify: `python rag.py`, or `python -c "import rag; print(rag.search('battery price'))"`.
Bigger documents: split into smaller sections; production would use a PDF loader + embeddings + vector DB in `rag.py` only.

## 7. Add a dashboard column or chart

**Column (phone)**: `static/dashboard.html`, add a header next to `<th>DNC</th>` ({{L:static/dashboard.html:<th>DNC</th>}}) and a cell in the row template:
```
        <th>Phone</th>
    <td>${esc(l.phone)}</td>
```
**Chart (leads per city)**: add `<div class="card"><h3>Leads by city</h3><div id="cityChart"></div></div>` in the HTML, and in `load()`:
```
  const byCity = {};
  d.leads.forEach(l => { if (l.city) byCity[l.city] = (byCity[l.city] || 0) + 1; });
  $("cityChart").innerHTML = bars(Object.entries(byCity).map(([c, n]) => ({ label: c, value: n, color: "var(--blue)" })));
```
**New KPI** (for example do-not-call count): in `db.dashboard_data` stats ({{L:db.py:def dashboard_data}}) add
`"dnc": sum(1 for l in leads if l["do_not_call"]),` and in dashboard.html kpis ({{L:static/dashboard.html:const kpis = [}}) add `["Do-not-call", s.dnc]`.

## 8. Change appointment slot times

`db.py` ({{L:db.py:SLOT_TIMES = }}):
```
SLOT_TIMES = ["09:00", "11:00", "14:00", "16:00", "18:00"]   # new visit times
DAYS_AHEAD = 5                                              # offer 5 working days
```
Also update the "Site visit booking" section of `kb.md` so the agent's facts match. To also skip Saturdays, in `all_slots()` change `if day.weekday() == 6:` to `if day.weekday() in (5, 6):`. Existing bookings keep their old times.

## 9. Swap the LLM provider or model

Only `llm.py` changes. Easiest: environment variables, with no code change:
```
$env:OPENAI_MODEL = "gpt-4.1-mini"                       # another OpenAI model
# Any OpenAI-compatible API (same code!):
$env:OPENAI_BASE_URL = "https://api.groq.com/openai/v1"; $env:OPENAI_MODEL = "openai/gpt-oss-120b"
$env:OPENAI_BASE_URL = "http://localhost:11434/v1";      $env:OPENAI_MODEL = "llama3.1"   # Ollama, local
$env:OPENAI_BASE_URL = "https://api.anthropic.com/v1/";  $env:OPENAI_MODEL = "claude-haiku-5-5"
$env:OPENAI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"; $env:OPENAI_MODEL = "gemini-2.5-flash"
```
(Put that provider's key in `OPENAI_API_KEY`; check the provider's docs for exact model names.) For a non-compatible SDK, rewrite only `chat()` and `summarize()` and return the same dict: `{"content": str|None, "tool_calls": [{"id", "name", "arguments": dict}]}`. Nothing else in the app changes.

## 10. The "do not call" flag

Already built: column `do_not_call` (db.py), parameter in the `update_lead` schema, rule 5 in SYSTEM_PROMPT, DNC column on the dashboard and lead card. Likely extension requests:
**Block booking for opted-out leads**: `tools.book_appointment` ({{L:tools.py:def book_appointment}}), first lines:
```
def book_appointment(session, slot):
    if db.get_lead(session.lead_id).get("do_not_call"):
        return {"booked": False, "error": "Caller opted out (do not call). Do not book."}
```
**Make opted-out leads COLD**: in `tools.update_lead`, after scoring: `if lead["do_not_call"]: lead = db.update_lead(lead_id, {"score": "cold"})`.
**Refuse to start calls to DNC numbers** (outbound): before dialing, `SELECT 1 FROM leads WHERE phone=? AND do_not_call=1`.

## 11. Debug a failing tool call

1. **Read the terminal.** Every tool call prints three kinds of lines:
```
INFO [tools] [TOOL] book_appointment args={'slot': 'tomorrow 3pm'}
INFO [tools] [TOOL RESULT] book_appointment -> {"booked": false, "error": "'tomorrow 3pm' is not a valid slot.", ...}
ERROR [tools] [TOOL ERROR] update_lead      <- followed by a Python traceback (read the LAST line first)
```
2. **Match the error to a cause:**

| Error text | Cause | Fix |
|---|---|---|
| `TypeError: ...unexpected keyword argument 'x'` | Schema property name differs from the Python parameter | Make names identical in TOOL_SCHEMAS and the function |
| `missing 1 required positional argument` | LLM omitted a field | Add it to `"required"` in the schema, improve the description |
| `not a valid slot` | LLM invented a date format | Description says "use exact slot value from check_slots"; agent recovers with alternatives |
| `Unknown tool` | Name in schema but not in TOOLS dict | Add to TOOLS |
| `sqlite3.OperationalError: no such column` | Schema changed, old `crm.db` | Delete `crm.db`, restart |
| `KeyError` in fallback.py | New qualify field has no template | Add to `T["en"]` and `T["hi"]` |

3. **Test the tool alone** (no LLM, no browser):
```
python -c "import db, tools; db.init_db(); S = type('S', (), {'lead_id': 1}); print(tools.run_tool(S, 'check_slots', {}))"
```
4. **Browser side**: F12 -> Console (JS errors) and Network (click the `/message` request -> Response shows `events` with every tool call and result).

## 12. Reading logs and fixing common problems

| Symptom | Fix |
|---|---|
| Badge says *offline-fallback* but you set a key | The env variable must be set in the SAME terminal that runs uvicorn; restart uvicorn |
| `[LLM ERROR] AuthenticationError` / 401 | Wrong key. `RateLimitError` / 429 = quota or billing. `NotFoundError` = wrong model name: set `OPENAI_MODEL` |
| `ModuleNotFoundError` | `pip install -r requirements.txt` (same Python as uvicorn: `python -m uvicorn main:app`) |
| `address already in use` | `uvicorn main:app --port 8001` |
| Mic does nothing / "not-allowed" | Use Chrome on `http://localhost:8000`, allow mic (icon in address bar), check Windows mic privacy settings |
| Hindi voice sounds English | No hi-IN voice installed; Chrome has "Google Hindi"; Windows: Settings > Time & language > Speech > add Hindi |
| KB edit not used | Restart server (index built at startup) |
| Dashboard not updating | It refreshes every 5 s; check `/api/dashboard` in the browser |
| Agent repeats a question | Check the lead card: was the field saved? If not, the LLM didn't call update_lead: strengthen rule 3 in the prompt |

<<<pagebreak>>>

## 13. Ten practice exercises (with solutions)

**Exercise 1: Rename the agent from Riya to Aisha and make her mention the free site visit in the greeting.**
Solution: `agent.py`, change "You are Riya" in SYSTEM_PROMPT and both GREETING strings, e.g. `"Hello! This is Aisha from SunNova Solar. We offer a free site visit and up to Rs 78,000 subsidy. May I know your name?"`. No other file mentions the name (fallback uses no name).

**Exercise 2: Add an evening 7 PM slot and offer 5 days.**
Solution: `db.py`: `SLOT_TIMES = ["10:00", "12:00", "15:00", "17:00", "19:00"]`, `DAYS_AHEAD = 5`. Update the kb.md "Site visit booking" times. Show `/api/dashboard` or ask the agent for slots.

**Exercise 3: Leads outside the service cities must be COLD.**
Solution: see recipe 2 (`SERVICE_CITIES` set + early `return "cold"` in `score_lead`). Test with `tools.score_lead({"city": "Surat", "budget": "3 lakh", "timeline": "1 month", "need": "3 kW"})` gives `cold`.

**Exercise 4: Ask whether the property is a home or a business (`property_type`).**
Solution: follow recipe 1 exactly with `property_type` (DB column + LEAD_FIELDS, QUALIFY_FIELDS, schema property, prompt list + visible fields, fallback QUALIFY + templates, delete crm.db). Bonus: in `score_lead`, add `if lead.get("property_type") == "business": points += 1`.

**Exercise 5: Add a `transfer_to_human` tool for angry callers.**
Solution (tools.py):
```
def transfer_to_human(session, reason):
    db.update_lead(session.lead_id, {"status": "handoff"})
    log.warning("[HANDOFF] lead %s: %s", session.lead_id, reason)
    return {"transferred": True, "message": "A senior advisor will call within 15 minutes."}
```
Add `"transfer_to_human": transfer_to_human` to TOOLS, a schema with one required string `reason`, and prompt rule 6: "If the caller is angry or asks for a human, call transfer_to_human."

**Exercise 6: Add a KB section on battery storage and prove RAG finds it.**
Solution: recipe 6. Show `python -c "import rag; print(rag.search('battery backup price'))"` returning `Battery storage` with the top score, then ask the agent in the UI.

**Exercise 7: Show a "Do-not-call" KPI card on the dashboard.**
Solution: `db.dashboard_data()` stats: `"dnc": sum(1 for l in leads if l["do_not_call"]),`; dashboard.html kpis: `["Do-not-call", s.dnc]`. Test: in a call say "please don't call me again", end, check the card.

**Exercise 8: Add `next_action` to the summary and show it after the call.**
Solution: llm.py SUMMARY_PROMPT JSON gets `"next_action": "one short sentence"`. In `agent.end_call` return `"next_action": s.get("next_action", "")`. In index.html `endCall()` add `<p><b>Next action:</b> ${esc(data.next_action)}</p>`. (Fallback: add `"next_action": insights[-1]` to the dict returned by `fallback.summarize`.) To store it, add a column to `calls` or append it to insights.

**Exercise 9: Make the agent more concise and slower-spoken.**
Solution: SYSTEM_PROMPT: change "1-3 sentences" to "at most 2 short sentences (under 30 words)". index.html: slider `value="0.9"`. Explain the latency benefit: fewer output tokens means a faster LLM response and shorter TTS.

**Exercise 10: Bug hunt.** A teammate renamed the parameter in `def book_appointment(session, slot)` to `def book_appointment(session, time)`. Bookings fail. Find and fix.
Solution: the terminal shows `[TOOL ERROR] book_appointment ... TypeError: book_appointment() got an unexpected keyword argument 'slot'`, because the LLM uses the schema name `slot`. Fix: rename back to `slot` (or rename it in both the function and TOOL_SCHEMAS). Note that the agent did not crash: `run_tool` returned the error to the LLM, which apologised. That is our error-handling design.

**Bonus: write a unit test for scoring.**
```
import tools
assert tools.score_lead({"budget": "2 lakh", "timeline": "within 1 month", "need": "3 kW"}) == "hot"   # 2+2+1
assert tools.score_lead({"budget": "1 lakh", "timeline": "6 months"}) == "cold"                          # 1+0
assert tools.score_lead({"budget": "2 lakh", "timeline": "next year"}) == "warm"                          # 2
```
