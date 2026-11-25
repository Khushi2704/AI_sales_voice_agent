# ☀️ SunNova AI Sales Voice Agent

An autonomous, bilingual (**English + Hindi**) AI voice agent for a rooftop-solar company. It **talks to leads by voice**, answers questions from a knowledge base (**RAG**), **qualifies and scores** each lead (hot / warm / cold + sentiment), **books a site visit** with no double booking, saves everything to a **CRM**, and generates a **call summary with business insights** on a live **dashboard**.

> SunNova Solar is a fictional company used for this MVP. See [REPORT.md](REPORT.md) for the one-page project report.

---

## ✨ Features

| | Feature | How |
|---|---|---|
| 🎙️ | Real-time voice | Browser Web Speech API: speech-to-text + text-to-speech (no paid keys) |
| 🧠 | AI agent with memory | LLM with tool calling; full conversation + CRM record sent every turn |
| 🌐 | Multilingual | English and Hindi (switch in the UI; agent replies in the caller's language) |
| 📚 | RAG | TF-IDF retrieval over `kb.md` (pricing, subsidy, EMI, warranty, FAQs) before answering |
| 🔥 | Lead qualification | Rule-based hot / warm / cold scoring + positive / neutral / negative sentiment |
| 📅 | Appointment booking | Free slots, booking by number ("the 2nd one") or time ("3 PM", "teen baje"), no double booking |
| 🗂️ | CRM | SQLite tables: `leads`, `appointments`, `calls` (HubSpot / Salesforce ready, see below) |
| 📊 | Summaries + dashboard | Post-call summary and insights; KPIs: calls, hot leads, bookings, conversion |
| 📴 | Natural call ending | "No, that's all" → "Shall I end the call?" → "Yes" → agent says goodbye and hangs up |
| 🛟 | Never crashes | Model fallback chain, offline rule-based brain, and a text-chat fallback if the mic fails |

---

## 🔄 How it works

```
Caller speaks ─► Browser STT ─► FastAPI ─► Agent loop (LLM + memory)
                                              │  tool calling
             ┌────────────┬───────────────┬───┴──────────┬──────────────────┬───────────┐
             ▼            ▼               ▼              ▼                  ▼           │
         search_kb    update_lead     check_slots   book_appointment     end_call       │
        (RAG on kb.md) (CRM + score)  (free times)  (no double booking)  (hang up)      │
             └────────────┴──── SQLite CRM: leads · appointments · calls ┘              │
                                                                                        ▼
Caller hears ◄─ Browser TTS ◄─────────────────── short reply in the caller's language ──┘
End call ─► LLM summary + sentiment + insights ─► CRM ─► Dashboard
```

1. The browser turns speech into text and sends it to the server.
2. The **agent loop** (`agent.py`) gives the LLM the conversation, the current lead record and 5 tool descriptions.
3. The LLM calls tools: look up facts, save lead details, check slots, book, or end the call. Our Python code runs them safely.
4. The LLM writes a short reply, and the browser speaks it.
5. When the call ends, the LLM writes a JSON summary with insights, which appears on the dashboard.

---

## 🛠️ Tech stack

- **Backend:** Python, FastAPI, Uvicorn
- **AI:** LLM via an OpenAI-compatible API (default: Groq free tier, model chain `gpt-oss-120b → qwen3.8-27b → gpt-oss-20b`; works with OpenAI too)
- **RAG:** scikit-learn TF-IDF + cosine similarity
- **Database:** SQLite
- **Frontend:** plain HTML, CSS, JavaScript (no framework)
- **Voice:** Web Speech API (`SpeechRecognition`, `speechSynthesis`)

---

## 🚀 Quick start

**Requirements:** Python 3.10+, Google Chrome or Microsoft Edge (best Web Speech support).

```bash
# 1. Clone and install
git clone https://github.com/Khushi2704/AI_sales_voice_agent.git
cd AI_sales_voice_agent
pip install -r requirements.txt

# 2. Add your API key (optional, but needed for the AI brain)
cp .env.example .env          # Windows PowerShell: copy .env.example .env
#    then open .env and paste your key (free key: https://console.groq.com)

# 3. Run
uvicorn main:app --reload
```

Open **http://localhost:8000** for the call screen and **http://localhost:8000/dashboard** for the dashboard.

`.env` settings:

```ini
OPENAI_API_KEY=gsk_your_groq_key
OPENAI_BASE_URL=https://api.groq.com/openai/v1
OPENAI_MODEL=openai/gpt-oss-120b,qwen/qwen3.8-27b,openai/gpt-oss-20b
```

- Comma-separated models form a **fallback chain**: if one hits its rate limit, the next one answers.
- For OpenAI, remove `OPENAI_BASE_URL` and set `OPENAI_MODEL=gpt-4o-mini`.
- **No key?** The app still runs: the badge shows *offline-fallback* and a rule-based brain drives the same tools.

---

## 🎬 Demo script

1. Pick **English**, click **📞 Start call**, and allow the microphone. Riya greets you.
2. Say: *"Hi, my name is Rahul. How much subsidy do I get for a 3 kW system?"* → she answers from the knowledge base (RAG).
3. *"I live in Delhi."* → *"My budget is around 2 lakh."* → *"Within one month."* → the lead turns **HOT**.
4. She offers 3 numbered slots → *"3 PM please"* or *"the first one"* → booked.
5. *"No, that's all."* → *"Shall I end the call now?"* → *"Yes."* → goodbye, and the call ends automatically.
6. Watch the **live lead card**, **tool log** and **summary**, then open the **dashboard**.

**Hindi example:** मेरा नाम प्रिया है → सब्सिडी कितनी मिलेगी? → जयपुर → 5 kW चाहिए → बजट 3 लाख है → अगले महीने → दूसरा वाला → नहीं, बस → हाँ, कॉल काट दो

The text box under the mic works exactly like speaking. To reset the demo data, stop the server, delete `crm.db`, and start again (6 sample leads are re-seeded).

---

## 📁 Project structure

```
├── main.py              FastAPI server: pages, JSON API, sessions, logging, error handler
├── agent.py             Agent loop, conversation memory, system prompt, post-call summary
├── llm.py               The ONLY file that calls the LLM: .env loading, model chain, history trimming
├── tools.py             The 5 tools + their JSON schemas, lead scoring, slot understanding
├── rag.py               TF-IDF retrieval over kb.md
├── db.py                SQLite CRM: leads, appointments (UNIQUE slot), calls, dashboard stats, seed data
├── fallback.py          Offline rule-based brain (same output format as the LLM)
├── kb.md                Knowledge base: packages, pricing, subsidy, EMI, warranty, process, FAQs
├── static/
│   ├── index.html       Call screen: voice, language switch, text fallback, lead card, tool log
│   ├── dashboard.html   KPIs, charts, leads, bookings, call summaries
│   └── style.css
├── tests/               Automated tests
├── .env.example         Settings template (copy to .env)
└── REPORT.md            One-page project report
```

### API

| Method | Endpoint | Purpose |
|---|---|---|
| `POST` | `/api/call/start` | Start a call `{language}` → greeting |
| `POST` | `/api/call/{id}/message` | Send what the caller said `{text, language}` → reply, tools used, lead card, `end_call` flag |
| `POST` | `/api/call/{id}/end` | End the call → summary + insights |
| `GET` | `/api/dashboard` | Stats, leads, appointments, call summaries |

---

## 🧪 Tests

```bash
python -m tests.test_flow          # full workflow over HTTP (offline brain): English + Hindi calls, RAG,
                                   # scoring, booking by time/number, end-of-call flow, double booking,
                                   # one visit per lead, empty speech, do-not-call, dashboard
python -m tests.test_openai_mock   # LLM code path with a fake client: tool calls, memory format,
                                   # API failure fallback, rate-limit model chain, history trimming
python -m tests.test_live_llm      # REAL LLM from .env (uses API quota): full English + Hindi call
python rag.py                      # quick retrieval check
```

---

## 🛟 Reliability and error handling

| Problem | What happens |
|---|---|
| Microphone blocked or unsupported | Message on screen; the text box works the same way |
| Model rate-limited (HTTP 429) | The next model in the chain answers |
| No key, no internet, or API error | The offline rule-based brain answers (badge turns orange) |
| Empty speech | "Sorry, I didn't catch that" (no LLM call) |
| Wrong tool arguments from the LLM | The error goes back to the LLM; no crash |
| Slot already taken | The database rejects it; alternatives are offered |
| Second booking for the same lead | Refused: one visit per lead |
| Caller says "don't call me" | Do-not-call flag saved, polite goodbye, call ends |

---

## 🔌 CRM integration (HubSpot / Salesforce)

All CRM writes go through `db.py`. To use a real CRM, keep SQLite as the local record and sync after each call (ideally in a background worker):

- **HubSpot:** upsert a Contact (`POST /crm/v3/objects/contacts`) with custom `lead_score` and `sentiment` properties, log the call (`/crm/v3/objects/calls`), and create a Meeting for the site visit. Authenticate with a Private App token.
- **Salesforce:** create a Lead (`POST /services/data/vXX.X/sobjects/Lead`, Rating = Hot/Warm/Cold), an Event for the visit, and a Task with the summary. Authenticate with OAuth 2.0.
- Store the CRM's record ID in `leads` so retries update instead of duplicating.

---

## 📈 From prototype to production

| Part | Prototype | Production |
|---|---|---|
| Voice | Browser mic and speaker | Phone calls via Exotel/Twilio, streamed over WebSockets |
| STT / TTS | Web Speech API | Streaming STT (Deepgram/Google), neural TTS (ElevenLabs/Azure) |
| Sessions | Server memory | Redis (stateless, autoscaled servers behind a load balancer) |
| Knowledge search | TF-IDF | Embeddings + vector database |
| CRM | SQLite | Postgres with read replicas + HubSpot/Salesforce sync |
| Post-call work | Inline | Queue + background workers |
| Security | Local demo | Consent notice, encryption, RBAC, PII masking, DPDP Act retention rules |

**Approximate production cost:** Rs 2-4.5 per call-minute, about Rs 35-70 per qualified lead (details in [REPORT.md](REPORT.md)).

---

## ⚠️ Limitations

- Browser speech quality depends on the browser and installed voices (Hindi TTS: "Google हिन्दी" in Chrome).
- Sessions live in memory, so restarting the server ends active calls.
- TF-IDF matches words, not meanings.
- The free-tier LLM has rate limits (handled by the model chain and offline fallback).
- The offline brain is intentionally simple.

---

## 🔒 Security note

Never commit your `.env` file. It is listed in `.gitignore`. Only `.env.example`, with a placeholder key, belongs in the repo.
