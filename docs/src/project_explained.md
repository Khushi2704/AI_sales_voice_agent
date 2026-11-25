# Project Explained: a beginner's guide to your AI Sales Voice Agent

This guide assumes you are new to voice AI. Read it top to bottom once, then use it as a reference. Every idea is explained in plain words first, then shown in your own code.

**The one-sentence version:** a person talks into the browser; the browser turns speech into text; our Python server gives that text to an AI model (the LLM), which can use "tools" to look up facts, save lead details and book visits; the AI's reply goes back to the browser, which speaks it aloud; when the call ends we write a summary and show everything on a dashboard.

**Analogy for the whole system:** think of a call-centre employee named Riya.
- Her **ears** = speech-to-text (STT). Her **mouth** = text-to-speech (TTS).
- Her **brain** = the LLM (a large language model such as GPT).
- Her **notebook for this call** = memory (the list of messages).
- Her **company handbook** = the knowledge base (`kb.md`), and **flipping to the right page** = RAG retrieval.
- Her **hands** = tools: she can write in the CRM register, look at the appointment diary and book a slot.
- Her **manager's report after each call** = summary + insights on the dashboard.

## Part 1 - The concepts in simple words

### STT - Speech-to-Text
Turns audio (your voice) into text. We use the browser's free **Web Speech API** (`SpeechRecognition`). Chrome sends the audio to Google's speech service and returns the words. We set `lang = "en-IN"` or `"hi-IN"` so it expects Indian English or Hindi. "Interim results" are the guesses it shows while you are still speaking; the "final" result is sent to the server.

### TTS - Text-to-Speech
Turns text into spoken audio. We use the browser's `speechSynthesis`. We pick a voice that matches the language and set the speed (`rate`). In production you would use a neural TTS service (ElevenLabs, Azure, Google) for a more human voice.

### LLM - Large Language Model
A model trained on huge amounts of text that predicts the next words. Given a conversation, it writes a sensible next reply. It does NOT know your company prices and it cannot access your database by itself. That is why we add RAG and tools. We send it a list of messages:
- **system** message: the rules and personality ("You are Riya... keep replies short...").
- **user** messages: what the caller said.
- **assistant** messages: what the AI said before.
- **tool** messages: results of tools the AI asked us to run.

### Tool calling (function calling)
We describe some Python functions to the LLM in JSON (name, purpose, parameters). When the LLM decides it needs one, instead of replying with text it replies: "please call `book_appointment` with `{"slot": "2026-11-26 10:00"}`". **Our code** runs the real function and sends back the result. The LLM then continues. Analogy: the LLM is a manager who cannot touch the computer; it tells an assistant (our code) exactly what to do and reads the result.

### Agent
An **agent** is an LLM in a loop with tools and a goal. It decides by itself which steps to take: look something up, save data, check slots, book, then reply. Our loop is in `agent.handle_turn()`: ask the LLM; if it wants tools, run them and ask again; if it gives text, that is the reply. A limit (`MAX_TOOL_STEPS = 6`) prevents endless loops.

### Memory (contextual memory)
LLMs are **stateless**: they remember nothing between requests. So on every turn we send the **whole conversation** again (`session.messages`). We also put the **current CRM record** (name, city, budget...) into the system prompt each turn, so the agent never asks for something it already knows. This is short-term memory (one call). Long-term memory across calls is the CRM itself.

### RAG - Retrieval-Augmented Generation
"Look it up before you answer." Before answering a factual question, we **retrieve** the relevant part of our knowledge base and give it to the LLM, which then **generates** the answer from those facts. This keeps answers correct and up to date, and you can change prices by editing `kb.md`; no retraining is needed. It also reduces **hallucination** (the AI confidently making things up).

### Embeddings, vectors and TF-IDF
To find "relevant" text, computers turn text into lists of numbers (**vectors**). Similar meaning gives nearby vectors.
- **TF-IDF** (what we use): one number per word. A word scores high if it is frequent in this section but rare in others (so "subsidy" matters, "the" does not). Simple, fast, no API needed, but it only matches words, not meanings.
- **Embeddings** (production): a neural model turns text into ~1,500 numbers that capture meaning, so "how much will it cost" matches "pricing" even with no shared words. These are stored in a **vector database** (pgvector, Pinecone, Qdrant).
- **Cosine similarity**: measures the angle between two vectors. 1 = same direction (very similar), 0 = unrelated.

### Sentiment analysis
Detecting the caller's mood: positive, neutral or negative. The LLM judges it during the call (it passes `sentiment` to `update_lead`), and again at the end in the summary. The offline fallback uses simple keyword lists ("expensive", "worried" means negative).

### Lead scoring (qualification)
Sales teams rank leads so humans call the best ones first. We use the classic **BANT** idea (Budget, Authority, Need, Timeline), simplified to budget + need + timeline. `tools.score_lead()` gives points: buying within 1 month = 2 points, within 3 months = 1; budget at least Rs 1.2 lakh = 2 (any budget = 1); a stated need = 1. 4+ points = **HOT**, 2-3 = **WARM**, else **COLD**. Rules are in code (not the LLM) so they are predictable, explainable and easy to change.

### CRM - Customer Relationship Management
The database where a company keeps its customers and leads (HubSpot and Salesforce are famous ones). Ours is SQLite with three tables: `leads`, `appointments`, `calls`.

### Call summarisation and insights
After the call, we send the transcript to the LLM with a prompt asking for JSON: a 2-3 sentence summary, the overall sentiment and 3 business insights (objections, interests, next action). `response_format={"type": "json_object"}` forces valid JSON.

<<<pagebreak>>>

## Part 2 - How each file works

### kb.md - the handbook
Markdown file with one `## Section` per topic (pricing, subsidy, EMI...). Each section ends with a `Keywords:` line containing synonyms and Hindi/Hinglish words, so Hindi questions still match with TF-IDF.

### rag.py - finding the right handbook page
```
def load_chunks(path=KB_FILE):
    text = open(path, encoding="utf-8").read()       # read the whole file
    chunks = []
    for part in text.split("\n## ")[1:]:             # cut at every "## " heading; [0] is the title
        title, _, body = part.partition("\n")        # first line = heading, rest = body
        chunks.append({"title": title.strip(), "text": body.strip()})
    return chunks
```
```
CHUNKS = load_chunks()                                # runs once at server start
VECTORIZER = TfidfVectorizer(lowercase=True, token_pattern=r"(?u)[\wऀ-ॿ]+", stop_words="english")
MATRIX = VECTORIZER.fit_transform([...])              # one TF-IDF vector per chunk (a matrix)

def search(query, k=2):
    scores = cosine_similarity(VECTORIZER.transform([query]), MATRIX)[0]   # similarity to every chunk
    best = scores.argsort()[::-1][:k]                                       # indexes of the top-k scores
    return [... for i in best if scores[i] >= MIN_SCORE]                    # ignore weak matches
```
- `token_pattern` keeps whole Hindi (Devanagari) words together, so "subsidy" written in Hindi matches the Keywords line.
- `stop_words="english"` ignores words like "the", "is".
- `MIN_SCORE = 0.05`: if nothing is similar enough we return nothing, and the agent says "I'll get an expert to call you" instead of guessing.

### db.py - the CRM
- `get_conn()` opens SQLite, commits if all went well and **always closes** the connection (a context manager).
- `init_db()` creates the tables. Note `slot TEXT UNIQUE` in `appointments`: the **database itself refuses** a second booking of the same slot. Even if two calls try at the same time, only one INSERT succeeds.
- `all_slots()` generates the next 3 working days x 4 times (`SLOT_TIMES`), skipping Sunday. `free_slots()` removes taken ones.
```
def book_slot(lead_id, slot):
    if slot not in all_slots():                       # reject made-up or past slots
        return False, f"'{slot}' is not a valid slot."
    try:
        with get_conn() as conn:
            conn.execute("INSERT INTO appointments ...", (lead_id, slot, now()))
            conn.execute("UPDATE leads SET status = 'booked' WHERE id = ?", (lead_id,))
        return True, f"Booked {slot}"
    except sqlite3.IntegrityError:                    # UNIQUE violated = already booked
        return False, f"Slot {slot} is already booked."
```
- `update_lead()` only accepts known column names (`LEAD_FIELDS`). This protects against bad keys and SQL injection through column names; values are always passed as `?` parameters.
- `dashboard_data()` returns everything the dashboard needs, including `conversion = bookings / finished calls`.
- `seed_if_empty()` inserts 6 sample leads, calls and bookings the first time, so the dashboard looks alive.

### tools.py - the agent's hands
Five tools (`search_kb`, `update_lead`, `check_slots`, `book_appointment`, `end_call`) + `TOOL_SCHEMAS` (their JSON descriptions for the LLM) + `run_tool()`.
- `resolve_slot()` turns what the caller said ("the second one", "3 p.m.", "teen baje", "tomorrow 5 PM") into an exact slot. `book_appointment` uses it, so booking by number or by time always works, even if the LLM passes the caller's words.
- `end_call` sets `session.end_requested`; the server returns `end_call: true`, and the browser speaks the goodbye and then hangs up by itself. The agent only calls it after asking "Shall I end the call?" and hearing yes (prompt rule 6), or when the caller opts out.
```
def run_tool(session, name, args):
    log.info("[TOOL] %s args=%s", name, args)          # every tool call is logged
    try:
        if name not in TOOLS:
            raise ValueError(f"Unknown tool {name}")
        result = TOOLS[name](session, **args)          # TOOLS maps name -> python function
    except Exception as e:
        result = {"error": f"{type(e).__name__}: {e}"} # errors go BACK TO THE LLM, no crash
    return result
```
- `**args` turns the LLM's JSON `{"slot": "..."}` into the keyword argument `slot="..."`.
- If the LLM sends a wrong argument, the error text is returned to the LLM, which usually corrects itself on the next step.
- `update_lead` saves fields, **re-scores** the lead and returns `still_missing` so the LLM knows what to ask next.
- `book_appointment` returns `alternatives` when a slot is taken, so the agent can recover gracefully.

### llm.py - the only door to the AI provider
```
MODELS = [...os.getenv("OPENAI_MODEL")...split(",")]  # one model, or a list = fallback chain
client = OpenAI(api_key=API_KEY, base_url=BASE_URL, timeout=15, max_retries=0) if API_KEY else None

def chat(messages, tools):
    for model in MODELS:                               # try each model in the chain
        try:
            resp = client.chat.completions.create(model=model, messages=trim_history(messages),
                                                  tools=tools, temperature=0.3)
            msg = resp.choices[0].message
            calls = [{"id": tc.id, "name": tc.function.name,
                      "arguments": json.loads(tc.function.arguments or "{}")} for tc in (msg.tool_calls or [])]
            return {"content": msg.content, "tool_calls": calls}
        except RateLimitError:
            continue                                   # this model is busy -> try the next one
        except Exception as e:
            break                                      # network down, bad key... -> fallback
    return fallback.chat(messages)                     # never crash: use rule-based brain
```
- `temperature=0.3`: low randomness gives consistent, factual answers.
- We convert OpenAI's objects into a **plain dict**. The rest of the app depends only on this dict shape, so another provider just needs to return the same shape.
- `trim_history()`: for older turns it keeps what was SAID but drops tool requests/results; the facts are already in the LEAD RECORD. This keeps each request small (free tiers limit tokens per minute).
- The model list comes from `.env` (`load_env_file()`), e.g. `openai/gpt-oss-120b,qwen/qwen3.8-27b,openai/gpt-oss-20b` on Groq: if one hits its rate limit, the next one answers.
- `summarize()` uses `response_format={"type": "json_object"}` to force valid JSON.

### fallback.py - the backup brain
Reads the same message list and returns the same dict shape. It uses **regex** (text patterns) to pull out name, city, kW/bill, budget ("2 lakh") and timeline ("1 month"); keyword lists to detect questions, sentiment and "don't call me"; and templates (English/Hindi) to reply. `plan()` decides which tools to run; `chat()` runs them one at a time, then `compose_reply()` writes the answer. It is less smart than an LLM, but the demo survives without internet or an API key.

### agent.py - the brain loop and memory
```
class Session:                                       # one object per call = the memory
    def __init__(self, language="en"):
        self.lead_id = db.create_lead(language)        # new CRM row for this caller
        self.call_id = db.create_call(self.lead_id)
        self.messages = [{"role": "system", "content": ""}]           # filled each turn
        self.messages.append({"role": "assistant", "content": text_for(GREETING, language)})
```
```
def handle_turn(session, user_text, language=None):
    if not user_text.strip(): return ... DIDNT_HEAR ...    # empty speech -> polite re-ask
    session.messages.append({"role": "user", "content": user_text})
    for _ in range(MAX_TOOL_STEPS):
        session.refresh_system_prompt()                # inject latest CRM record + language
        out = llm.chat(session.messages, TOOL_SCHEMAS)
        if not out["tool_calls"]:                      # plain text -> final reply
            session.messages.append({"role": "assistant", "content": out["content"]})
            return result(...)
        session.messages.append({"role": "assistant", "tool_calls": [...]})   # remember the request
        for c in out["tool_calls"]:
            res = run_tool(session, c["name"], c["arguments"])                 # do the work
            session.messages.append({"role": "tool", "tool_call_id": c["id"], "content": json.dumps(res)})
```
- The `tool_call_id` links each result to the request, so the LLM knows which answer belongs to which call (it can ask for several tools at once).
- `end_call()` builds a readable transcript (only spoken lines), calls `llm.summarize()`, saves the summary/insights in `calls` and updates the lead's sentiment.

### main.py - the web server
FastAPI maps URLs to Python functions. `SESSIONS` is a dict `{call_id: Session}` holding live calls in memory. Endpoints: `POST /api/call/start`, `POST /api/call/{id}/message`, `POST /api/call/{id}/end`, `GET /api/dashboard`. `@app.on_event("startup")` creates tables and seeds data. A global exception handler turns any crash into a friendly JSON error. `logging` prints every caller line, agent reply and tool call to the terminal.

### static/index.html - the call screen
- `startCall()` -> `/api/call/start`, shows and speaks the greeting.
- `startListening()` creates `SpeechRecognition` with the chosen language; `onresult` shows interim words; `onend` sends the final text via `sendText()`.
- `speak()` creates a `SpeechSynthesisUtterance`, sets `lang`, `rate` and voice; `onend` re-opens the mic if Hands-free is on. Clicking the mic while the agent talks cancels speech ("barge-in").
- `showLead()` updates the live CRM card; `showTool()` lists tool calls (great for explaining the agent live).
- The text box calls the same `sendText()`; that is the microphone fallback.

### static/dashboard.html - the business view
Fetches `/api/dashboard` every 5 seconds and draws KPI cards, simple CSS bar charts (no chart library), the leads table, bookings and call summaries with insights.

<<<pagebreak>>>

## Part 3 - One call from start to finish

1. You click **Start call**. Browser -> `POST /api/call/start {"language":"en"}`. Server creates a `Session` (new lead row + call row), stores it in `SESSIONS` and returns the greeting. The browser shows it and speaks it (TTS).
2. TTS ends -> mic opens (Hands-free). You say: "My name is Rahul, how much subsidy for 3 kW?" Chrome STT returns the text.
3. Browser -> `POST /api/call/7/message {"text": "...", "language": "en"}`.
4. `agent.handle_turn` adds your text to memory, refreshes the system prompt with the current lead record and calls `llm.chat(messages, TOOL_SCHEMAS)`.
5. The LLM answers with **two tool calls**: `update_lead({"name":"Rahul","need":"3 kW","sentiment":"positive"})` and `search_kb({"query":"subsidy for 3 kW"})`.
6. `run_tool` executes both. `update_lead` writes to SQLite and re-scores; `search_kb` runs TF-IDF and returns the subsidy section. Results are appended as `tool` messages.
7. Loop again: the LLM now sees the facts and writes: "Rahul, for 3 kW you get the maximum subsidy of Rs 78,000... Which city are you in?"
8. The server returns `{reply, events, lead}`. The browser shows the reply, updates the lead card and tool log, and speaks the reply.
9. Turns repeat. When name, city, need, budget and timeline are known, the score becomes HOT, the LLM calls `check_slots`, offers 2-3 slots, and when you choose, calls `book_appointment`. The UNIQUE constraint guarantees nobody else has that slot.
10. You click **End call** -> `POST /api/call/7/end`. `end_call` builds the transcript, `llm.summarize` returns JSON summary/sentiment/insights, which is saved to `calls`; the session is deleted.
11. The dashboard's next refresh (5 s) shows the new lead, booking, KPIs and summary.

## Part 4 - Error handling (why the demo does not crash)

| Problem | What happens |
|---|---|
| No API key / internet down / API error | `llm.py` catches it and uses `fallback.py`; the badge turns orange |
| Empty speech or blank text | Agent says "Sorry, I didn't catch that" without calling the LLM |
| Mic blocked or unsupported browser | Toast message; the text box works the same |
| LLM sends bad tool arguments | `run_tool` returns `{"error": ...}` to the LLM, which retries or apologises |
| Slot already taken (double booking) | DB `UNIQUE` rejects it; tool returns alternatives |
| LLM keeps calling tools | Stops after `MAX_TOOL_STEPS`, polite fallback line |
| Unknown call id | 404 with a friendly message |
| Any other server exception | Global handler returns JSON; details in the terminal log |

## Part 5 - Glossary

| Term | Meaning |
|---|---|
| Agent / agentic AI | LLM + tools + a loop: it decides and performs steps toward a goal by itself |
| API | A way for programs to talk to each other (here: HTTP + JSON) |
| API key | Secret password for a paid API; kept in an environment variable, never in code |
| ASR | Automatic Speech Recognition, another name for STT |
| Barge-in | Caller interrupts while the agent is speaking; we stop TTS |
| BANT | Budget, Authority, Need, Timeline: classic sales qualification |
| Chunk | A piece of the knowledge base (here one `##` section) |
| Context window | Maximum text an LLM can read at once (tokens) |
| Cosine similarity | How similar two vectors are (0 to 1) |
| CRM | Customer Relationship Management system/database |
| DPDP Act | India's Digital Personal Data Protection Act, 2023 |
| Embedding | Neural vector representing meaning of text |
| Endpoint | A URL the server answers, e.g. `/api/dashboard` |
| Environment variable | Setting given to a program from outside (e.g. `OPENAI_API_KEY`) |
| FastAPI | Python web framework we use for the server |
| Fine-tuning | Re-training a model on your data (we use RAG instead) |
| Hallucination | The LLM inventing facts confidently |
| JSON | Text format for data: `{"name": "Rahul"}` |
| Latency | Delay between the caller stopping and the agent starting to speak |
| LLM | Large Language Model (GPT, Claude, Gemini, Llama) |
| Load balancer | Spreads incoming requests over many servers |
| Prompt / system prompt | Instructions given to the LLM; system = permanent rules |
| Queue / worker | Jobs put in a list and processed in the background by workers |
| RAG | Retrieval-Augmented Generation: look up facts, then answer |
| Redis | Very fast in-memory database, used for shared session state |
| Regex | Pattern for matching text, e.g. numbers followed by "lakh" |
| REST | Style of API using URLs + HTTP methods (GET, POST) |
| Sentiment | Mood of the caller: positive/neutral/negative |
| Session | All data for one ongoing call |
| SQLite | Small database stored in a single file |
| Stateless | A server that keeps no memory between requests |
| STT / TTS | Speech-to-Text / Text-to-Speech |
| Temperature | LLM randomness setting (low = consistent) |
| TF-IDF | Term Frequency x Inverse Document Frequency: word-importance weights |
| Token | A piece of a word; LLMs read and are billed in tokens |
| Tool calling | LLM asks our code to run a named function with JSON arguments |
| Uvicorn | The program that runs the FastAPI app |
| Vector DB | Database optimised for finding similar vectors |
| WebSocket | Two-way connection for streaming (used for real-time audio in production) |
| Web Speech API | Browser's built-in STT (SpeechRecognition) and TTS (speechSynthesis) |
