# SunNova Solar - Autonomous AI Sales Voice Agent (MVP)

An AI agent that **talks to solar leads by voice** (English + Hindi), answers questions from a knowledge base (RAG),
**qualifies** them (hot / warm / cold + sentiment), **books a site visit** with no double booking, saves everything
to a **CRM** (SQLite), and at the end of the call writes a **summary + business insights** that show up on a **dashboard**.

```
Lead speaks -> browser STT -> FastAPI -> Agent (LLM + memory) -> tools: search_kb (RAG) / update_lead / check_slots /
book_appointment -> CRM (SQLite) -> reply -> browser TTS speaks.   End call -> summary + insights -> dashboard.
```

## Setup (4 steps)

1. Install Python 3.10+ and Google Chrome (Chrome/Edge have the best Web Speech support).
2. In this folder: `pip install -r requirements.txt`
3. Copy `.env.example` to `.env` and paste your key (Groq free tier or OpenAI). `.env` is git-ignored.
   With several models in `OPENAI_MODEL` (comma-separated), the agent switches to the next model when one hits its rate limit.
4. Run `uvicorn main:app --reload` and open **http://localhost:8000** (dashboard: http://localhost:8000/dashboard)

No key? It still works: the badge shows **brain: offline-fallback** and a rule-based brain (`fallback.py`) drives the same tools.

## How to run the demo

1. Open http://localhost:8000 and the dashboard in a second tab.
2. Choose **English** (or Hindi), click **Start call**, allow the microphone. Riya greets you and speaks.
3. With **Hands-free** on, the mic re-opens after the agent speaks. Otherwise click 🎤. You can also type in the text box.
4. Suggested script (English):
   - "Hi, my name is Rahul. How much subsidy do I get for a 3 kW system?"  -> RAG answer
   - "I live in Delhi." -> "My bill is about 3500 rupees." -> "Budget is around 2 lakh." -> "Within one month."
   - Agent offers numbered slots -> "The first one please" or "3 PM" -> booked
   - "No, that's all" -> agent asks "Shall I end the call now?" -> "Yes" -> agent says goodbye and hangs up by itself
5. Watch the right panel: the **live lead card** fills in, the score turns **HOT**, and **tool calls** are listed.
6. Click **End call** -> summary + insights appear. Refresh the dashboard: new lead, booking, summary, KPIs.
7. Hindi: switch to हिन्दी, start a call, e.g. "मेरा नाम प्रिया है", "सब्सिडी कितनी मिलेगी?", "जयपुर", "5 kW चाहिए", "बजट 3 लाख है", "अगले महीने", "पहला वाला".

Reset demo data: stop the server, delete `crm.db`, start again (6 sample leads are re-seeded).

## Run the tests

```
python -m tests.test_flow          # full workflow over HTTP: English + Hindi calls, RAG, scoring, booking,
                                   # double booking, empty speech, do-not-call, dashboard (uses a temp DB)
python -m tests.test_openai_mock   # OpenAI code path with a fake client, API-failure fallback, model chain
python -m tests.test_live_llm      # REAL LLM from .env (uses quota): full English + Hindi call
python rag.py                      # quick retrieval check
python docs/build_docs.py          # rebuild the PDFs (line numbers in guides are recomputed from the code)
```

## Project structure

| File | What it does |
|---|---|
| `main.py` | FastAPI web server: pages + JSON API, in-memory call sessions, logging, global error handler |
| `agent.py` | The agent loop + memory (Session), system prompt, greeting, end-of-call summary |
| `llm.py` | The ONLY file that calls the LLM (OpenAI). Swap provider/model here. Falls back if the API fails |
| `fallback.py` | Offline rule-based brain (regex + templates) with the same output format as the LLM |
| `tools.py` | Tools the LLM can call + their JSON schemas + lead scoring rules |
| `rag.py` | Retrieval: TF-IDF + cosine similarity over `kb.md` sections |
| `db.py` | SQLite CRM: leads, appointments (UNIQUE slot = no double booking), calls, seed data, dashboard stats |
| `kb.md` | Knowledge base: packages, pricing, subsidy, EMI, warranty, process, FAQs |
| `static/index.html` | Call screen: Web Speech STT + TTS, language switch, text fallback, live lead card, tool log |
| `static/dashboard.html` | KPIs, score + sentiment charts, leads table, bookings, call summaries (auto-refresh) |
| `tests/` | End-to-end tests |
| `docs/` | `architecture.pdf`, `project_explained.pdf`, `live_coding_guide.pdf`, `interview_prep.pdf` (+ markdown sources in `docs/src/`) |
| `REPORT.md` | One-page project report |

## CRM integration (HubSpot / Salesforce)

All CRM writes go through `db.py` (`update_lead`, `book_slot`, `finish_call`). To use a real CRM, keep SQLite as the
local record and add a sync step (best done in the post-call worker so calls never wait):
- **HubSpot**: create/update a Contact with `POST /crm/v3/objects/contacts` (properties: firstname, city, custom
  `lead_score`, `sentiment`), log the call with `POST /crm/v3/objects/calls`, create a Meeting for the site visit.
  Auth with a Private App token kept in an environment variable.
- **Salesforce**: create a Lead via REST `POST /services/data/vXX.X/sobjects/Lead` (Rating = Hot/Warm/Cold),
  an Event for the appointment and a Task with the call summary. Auth with OAuth 2.0 (connected app).
- Use the CRM's ID as an external key in our `leads` table so updates are idempotent (no duplicates on retry).

## Backup plan for demo failures (3 steps)

1. **Mic not working** (browser blocks it, noisy room, wrong browser): use the **text box**. Every feature (RAG, scoring,
   booking, CRM, summary, dashboard) works the same, because only the input method changes. Check the mic permission
   icon in Chrome's address bar, and use `http://localhost` (Chrome only allows the mic on localhost or https).
2. **Internet down / OpenAI API error**: nothing to do. `llm.py` catches the error and `fallback.py` answers (badge turns
   orange: *offline-fallback*). Use the suggested script above, which the rule-based brain handles well. Browser STT needs
   internet in Chrome; if it fails, type. TTS usually still works offline (Windows voices).
3. **Everything fails** (laptop, projector): play the **backup video**. Record it tonight:
   - Windows: press **Win + Alt + R** (Xbox Game Bar) to record the Chrome window, or use OBS Studio (free).
   - Record: start the server, a full English call with voice, a short Hindi call, end the call, show the dashboard,
     and show the terminal logs with `[TOOL]` lines. Keep it 3-4 minutes. Save it on the laptop AND on your phone/Drive.
   - Also keep screenshots of the call screen and dashboard plus the PDFs in `docs/` ready.

## Notes / limitations
- Browser STT/TTS quality depends on the browser and the installed voices (Hindi TTS voice: "Google हिन्दी" in Chrome).
- Sessions are kept in memory, so restarting the server ends active calls (production: Redis).
- The offline fallback is deliberately simple. It answers KB facts in English even on Hindi calls; the LLM path answers in Hindi.
