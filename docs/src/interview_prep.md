# Interview Prep: questions, model answers, pitch and demo script

Answer pattern that always works: **what I did -> why -> trade-off -> how I'd do it in production.** Keep answers to 30-60 seconds. If you don't know, say what you would check and how.

## A. 2-minute spoken pitch (read aloud 3 times tonight)

"Solar installers get hundreds of leads, but speed decides the sale: a lead called in five minutes converts far better than one called tomorrow. Human telecallers are slow, expensive, and offline at night, so many leads are never called.

I built an autonomous AI sales voice agent for a fictional installer, SunNova Solar. The lead talks to Riya, our agent, in English or Hindi. The browser converts speech to text; my FastAPI backend runs an agent loop where an LLM, with the whole conversation as memory, decides what to do using tools. It calls `search_kb`, a RAG lookup over the company knowledge base, so prices and subsidy answers are factual, not hallucinated. It saves every detail to the CRM with `update_lead`, which also scores the lead hot, warm or cold with transparent rules and tracks sentiment. Once qualified, it checks free slots and books a site visit; a database constraint makes double booking impossible. When the call ends, the LLM writes a summary and business insights, and everything appears on a live dashboard: calls, hot leads, bookings, conversion.

I designed it for reliability: all LLM code is in one file so the provider can be swapped in minutes, and if the API or internet fails, a rule-based fallback drives the same tools, and a text box covers microphone failures. On cost, a production call-minute is about two to four rupees, roughly thirty-five to seventy rupees per qualified lead, and the production design scales with stateless services, Redis, queues and managed databases. Let me show you a live call."

## B. 5-minute demo script

**Before (setup, 2 min before):** server running (`uvicorn main:app --reload`), Chrome tab 1 = call screen, tab 2 = dashboard, terminal visible beside the browser, volume up, mic tested, badge green (*brain: openai*). Backup video ready.

1. **(0:00) Dashboard first, 30 s.** "This is the sales manager's view: total calls, hot leads, bookings and conversion, with summaries and insights from previous calls. Six past leads are seeded. Now let's make a new call."
2. **(0:30) Start the English call, 2 min.** Click Start call. Riya greets. Say:
   - "Hi, my name is Rahul. How much subsidy do I get for a 3 kW system?" Point at the tool log: "It called `update_lead` to save my name and `search_kb` to retrieve the subsidy section. That's RAG: the answer of Rs 78,000 comes from `kb.md`, not from the model's memory."
   - "I'm in Delhi and my bill is about 3,500 a month." Point at the lead card filling in.
   - "Is EMI available?" (another RAG answer) then "My budget is around 2 lakh, and I want it within a month." The score turns **HOT**: "Scoring is rule-based in `tools.score_lead`: budget, need and timeline give points."
   - The agent offers slots, then "The first one, please." "`book_appointment` wrote to the CRM; the slot column is UNIQUE, so double booking is impossible."
3. **(2:30) Memory, 20 s (OpenAI mode only).** Ask "What was my budget again?" It answers 2 lakh: "the full conversation plus the CRM record is sent every turn."
4. **(2:50) End call, 40 s.** Click End call. Summary + insights appear. Switch to the dashboard: the new lead, booking, updated KPIs. "In production this summary job runs on a queue worker so the call never waits."
5. **(3:30) Hindi, 50 s.** Switch to Hindi, Start call: "Mera naam Priya hai, subsidy kitni milegi?" The agent answers in Hindi and speaks with a Hindi voice. "Language is passed to both STT and the prompt."
6. **(4:20) Robustness, 40 s.** Show the terminal logs with `[TOOL]` lines. Type in the text box ("mic fallback"). Mention: "If the OpenAI API fails, `llm.py` switches to the rule-based fallback; you can see the badge change." Close with the architecture PDF: prototype vs production.

## C. Architecture and design

**Q: Why this architecture?**
A: It's the simplest thing that shows every part of a real voice agent: STT, an agent with memory and tools, RAG, CRM, booking, post-call analytics and a dashboard. Each concern is a small file (`agent`, `tools`, `rag`, `db`, `llm`), so I can explain and change each in isolation. Browser STT/TTS costs nothing for a demo; FastAPI is light and async-friendly; SQLite needs no server. The production version keeps the same boundaries and swaps the implementations: telephony + streaming STT/TTS, Redis, Postgres, a vector DB, queues.

**Q: Why tool calling instead of asking the LLM to output everything as text?**
A: Tools give structured, validated actions. The LLM decides *what* to do; my code controls *how*, with validation (valid slot, known columns, UNIQUE constraint). It's safer (the LLM never writes SQL), testable (I can unit-test each tool), and auditable (every call is logged).

**Q: Why is scoring rule-based and not done by the LLM?**
A: Sales managers need consistent, explainable scores. The LLM is great at extracting "2 lakh, next month" from messy speech; deterministic rules then score it. It's cheap, reproducible and easy to change live. In future, a model trained on historical conversions could replace the rules.

**Q: Why REST instead of WebSockets?**
A: For a turn-based browser demo, REST is simpler and easier to debug. For real-time phone audio I'd use WebSockets (or the telephony provider's media streams) to stream audio both ways, enabling barge-in and sub-second latency.

**Q: What is "agentic" about this?**
A: The model isn't following a fixed script; in a loop it chooses which tools to call, in what order, how many (even several in parallel), and when it has enough information to reply, toward a goal (qualify and book). Guardrails: limited tool set, validated inputs, max 6 steps per turn, and a prompt that restricts facts to the KB.

## D. Latency

**Q: Where does latency come from, and how do you reduce it?**
A: Voice-to-voice latency = end-of-speech detection + STT + LLM (each tool round trip adds a call) + TTS start + network. In my demo it's roughly 1.5-3 s. Production target: under ~1 s:
- **Streaming everywhere**: streaming STT with partial transcripts; stream LLM tokens straight into a streaming TTS so the agent starts speaking after the first sentence.
- **Fast endpointing**: voice-activity detection (VAD) tuned to about 300-500 ms of silence.
- **Small fast model** for turns (e.g. a mini/flash/haiku-class model); bigger model only for the summary.
- **Fewer round trips**: parallel tool calls, keep the prompt short, prompt caching for the fixed system prompt and tool schemas.
- **Fillers**: "Let me check that for you" while a tool runs.
- **Co-location**: servers in an Indian region (Mumbai) near STT/LLM/TTS endpoints; keep connections warm.
- **Cache** frequent answers (subsidy, pricing) and pre-generated TTS for the greeting.

## E. RAG, hallucination and memory

**Q: RAG vs fine-tuning?**
A: RAG = look up facts at question time; fine-tuning = change the model's weights with training examples. For prices, subsidy rules and FAQs that change, RAG wins: update `kb.md` and the next call uses it; answers are traceable to a source; no training cost. Fine-tuning is for style/behaviour (tone, format, domain phrasing) or a small model for a narrow task. They can be combined.

**Q: How do you control hallucination?**
A: (1) The prompt says to always call `search_kb` before any fact and never invent numbers. (2) Retrieval has a minimum similarity threshold; if nothing matches, the tool says "not found" and the agent offers an expert callback. (3) Low temperature (0.3). (4) Actions go through validated tools, not free text. (5) Production: citation checks (does the answer's number appear in the retrieved text?), evaluation sets of real questions, monitoring flagged calls, human review of low-confidence answers.

**Q: Why TF-IDF and not embeddings?**
A: A small, curated KB with clear keywords works well with TF-IDF: it's instant, free and offline. I added Hindi keywords to each section for cross-language matching. Its weakness is synonyms ("how much will it cost" vs "pricing"). Production: multilingual embeddings in a vector DB, possibly hybrid search (keyword + vector) with re-ranking. Only `rag.py` changes.

**Q: How does memory work, and what are its limits?**
A: LLMs are stateless, so each turn I send the full message history (short-term memory) plus the current CRM record in the system prompt (structured memory). Long-term memory across calls is the CRM: on a repeat call you'd load the previous summary. Limit: very long calls grow the token count (cost and latency). Fix: summarise older turns, keep the structured lead record, and keep only the last N messages.

## F. Scalability to 1,00,000 users

**Q: How would you scale this to 1,00,000 users?**
A: Distinguish total users from concurrent calls: 1 lakh users might mean a few thousand simultaneous calls at peak.
- **Stateless gateways behind a load balancer**: any pod can serve any request; autoscale on CPU or active calls (Kubernetes HPA / ECS).
- **Session state in Redis** (today it's an in-memory dict; that's the one thing blocking horizontal scaling).
- **Queue for post-call jobs** (SQS/Kafka/Redis Streams): summaries, CRM sync and WhatsApp run in autoscaled workers with retries and a dead-letter queue.
- **Managed vector DB** for RAG; **Postgres** with connection pooling and **read replicas** for the dashboard; analytics in a warehouse.
- **Multi-region** (e.g. Mumbai + Hyderabad) with DNS failover; CDN for static files.
- **Provider limits**: LLM/STT/TTS rate limits are the real bottleneck, so I'd use quotas, multiple providers or keys, fallbacks, and backpressure (queue outbound calls).
- **Observability**: latency per stage, error rates, cost per call, alerts.

## G. Security, privacy and compliance

**Q: How do you handle data security?**
A: **Consent**: the call opens with AI disclosure and recording consent; honour DND/TRAI rules and our `do_not_call` flag. **Encryption**: TLS in transit, encryption at rest (DB, recordings). **Secrets**: API keys in env vars or a secrets manager (KMS/Vault), never in code. **Access**: role-based access to the dashboard (agent vs manager vs admin), SSO, audit logs. **PII handling**: mask phone numbers in logs; send the LLM only what's needed; choose providers with no-training data agreements and Indian data residency where possible. **Retention**: keep transcripts only as long as needed (e.g. 90 days), then delete or anonymise. **DPDP Act 2023**: lawful purpose with consent, purpose limitation, data-principal rights (access, correction, erasure), breach notification, and a grievance contact. **Prompt injection**: tools validate inputs; the LLM can't run arbitrary actions.

## H. Infrastructure and deployment

**Q: How would you deploy it?**
A: Containerise with Docker (Python slim image, `uvicorn main:app --host 0.0.0.0`, workers via gunicorn). CI/CD with GitHub Actions: tests, build image, push to a registry, deploy to AWS ECS/EKS or GCP Cloud Run in the Mumbai region. Managed Postgres (RDS/Cloud SQL), ElastiCache Redis, SQS, secrets in Secrets Manager. Telephony via Exotel/Twilio media streams to the voice gateway. Monitoring with CloudWatch/Grafana and Sentry; blue-green or canary deploys and prompt versioning so a bad prompt can be rolled back.
```
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

## I. Cost, commercial model and ROI

**Q: What does a call cost?** (approximate production numbers; say "approximately" and "depends on vendor")
A: Per minute: telephony Rs 0.5-1, streaming STT Rs 0.4-0.7, neural TTS Rs 0.5-2, LLM (small model) Rs 0.2-0.5, infra Rs 0.2-0.3, so **about Rs 2-4.5 per minute**. A 4-minute call is about Rs 8-18. With 1 in 4 calls qualified, that is **Rs 35-70 per qualified lead**. The demo itself costs only LLM tokens (fractions of a rupee per call) because browser voice is free.

**Q: Commercial model and ROI?**
A: SaaS for installers: a platform fee (about Rs 10-15k/month) plus usage (about Rs 5-6/minute), or performance pricing (about Rs 150 per qualified lead / Rs 500 per booked visit). ROI example: a telecaller costs about Rs 25-30k/month for ~1,200 connected calls in office hours. The agent handles unlimited parallel calls 24x7, calls every lead within a minute, and costs about Rs 10 per call. One extra solar sale (Rs 15-40k margin) pays for a month. Plus consistent data: every call is summarised and scored.

## J. Limitations and next steps

**Q: What are the limitations?**
A: Browser STT/TTS quality varies and is not a phone line; turn-based, not full-duplex streaming; in-memory sessions; TF-IDF misses synonyms; SQLite is single-node; offline fallback is simplistic; slots aren't tied to engineer calendars or locations; no auth on the dashboard.
**Next steps:** telephony integration (Exotel/Twilio) with streaming STT/TTS and barge-in; Redis sessions; embeddings + vector DB; HubSpot/Salesforce sync worker; WhatsApp confirmations and reminders; engineer calendar and route-aware slots; outbound campaign scheduler respecting DND hours; an evaluation suite (test conversations scored automatically); A/B tests of prompts; analytics on objections to improve sales scripts.

## K. Rapid-fire questions (one-liners)

| Question | Answer |
|---|---|
| What is temperature? | Randomness of the LLM; 0.3 = consistent, factual |
| What is a token? | A piece of a word; LLMs read and bill by tokens (~4 English characters) |
| Why `tool_call_id`? | Links each tool result to the request it answers |
| What if the LLM loops? | `MAX_TOOL_STEPS = 6`, then a polite fallback line |
| How is double booking prevented? | `UNIQUE` on `appointments.slot`; insert fails with IntegrityError, tool returns alternatives |
| How do you detect sentiment? | LLM labels it per turn via `update_lead` and in the post-call summary; fallback uses keywords |
| What does `response_format=json_object` do? | Forces the model to return valid JSON |
| Why one llm.py? | Single place to swap provider/model; the app depends on a plain dict format |
| Why `?` placeholders in SQL? | Prevent SQL injection; values are escaped by the driver |
| What is VAD? | Voice Activity Detection: detects when the caller starts/stops speaking |
| What is barge-in? | Caller interrupts; we stop TTS and listen (clicking the mic does this) |
| How to test without a key? | Offline fallback + `tests/test_openai_mock.py` with a fake client |
| What's cosine similarity? | Angle-based similarity of two vectors, 0 to 1 |
| How do you add a language? | LANG_NAMES + GREETING in agent.py, LANGS + option in index.html |
