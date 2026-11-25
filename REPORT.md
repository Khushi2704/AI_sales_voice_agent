# Project Report: Autonomous AI Sales Voice Agent for SunNova Solar

**Business problem.** Rooftop-solar installers buy or generate hundreds of leads a month (ads, subsidy-portal enquiries). Speed decides the sale: a lead called within 5 minutes converts far better than one called next day. Human telecallers are slow to respond, offline at night and on Sundays, cost about Rs 25-30k/month each, and qualify leads inconsistently. Many leads are never called at all.

**Solution.** An AI voice agent ("Riya") that calls or answers leads instantly, 24x7, in English or Hindi. It answers questions on pricing, subsidy, EMI and warranty from the company's own knowledge base; qualifies the lead (name, city, need, budget, timeline); scores it hot/warm/cold and tracks sentiment; books a free site visit in a free slot; and writes everything to the CRM. After each call it generates a summary and business insights (objections, interests, next action) for the sales dashboard. Humans only handle site visits and hot leads.

**Technical implementation (MVP).** Browser Web Speech API for speech-to-text and text-to-speech (free, no keys). FastAPI backend. An agent loop (`agent.py`) keeps the full conversation plus the CRM record as memory and uses an OpenAI LLM with **tool calling**: `search_kb` (RAG: TF-IDF retrieval over `kb.md`), `update_lead` (CRM write + rule-based scoring), `check_slots`, `book_appointment` (understands "the 2nd one" or "3 PM"; a UNIQUE constraint in SQLite prevents double booking), and `end_call` (hangs up after the caller confirms). A post-call LLM call returns JSON summary/sentiment/insights. All LLM code sits in one file, so swapping the provider is easy, and an offline rule-based fallback keeps the system working if the API fails. A text-chat fallback covers microphone failures.

**Commercial feasibility (approximate, India, production stack).**

| Cost per call-minute | Rs |
|---|---|
| Telephony (Exotel/Plivo) | 0.5 - 1.0 |
| Streaming STT | 0.4 - 0.7 |
| Neural TTS | 0.5 - 2.0 |
| LLM (small model, ~6 turns/min) | 0.2 - 0.5 |
| Cloud infra + monitoring | 0.2 - 0.3 |
| **Total** | **~2 - 4.5 per minute** |

A 4-minute call costs about Rs 8-18. If 1 in 4 calls yields a qualified lead, the cost is **~Rs 35-70 per qualified lead** (about Rs 80-150 per booked visit). A human telecaller costs about Rs 25+ per connected call and works 8 hours a day. A rooftop sale is worth Rs 1-3 lakh (Rs 15-40k margin), so ROI is strong. **Pricing model:** SaaS at Rs 10-15k/month platform fee plus Rs 5-6 per minute, or performance pricing of about Rs 150 per qualified lead.

**Scalability.** Stateless API/voice-gateway pods behind a load balancer with autoscaling; per-call memory in Redis; streaming STT/TTS over WebSockets for low latency; post-call work (summaries, CRM sync to HubSpot/Salesforce) on a queue with workers; Postgres with read replicas for the CRM and dashboard; a managed vector DB for RAG; multi-region deployment. This design targets 1,00,000+ users; concurrency is bounded mainly by provider rate limits, which are handled with quotas and multiple providers.

**Security and compliance.** AI-disclosure and recording-consent line at the start of every call; DND/do-not-call honoured (the `do_not_call` flag); TLS in transit and encryption at rest; API keys in a secrets manager; role-based dashboard access and audit logs; PII masking in logs and LLM prompts; data retention limits and deletion on request under India's **DPDP Act 2023**; prompts and tools restrict the agent to company-approved facts (RAG) to control hallucination.
