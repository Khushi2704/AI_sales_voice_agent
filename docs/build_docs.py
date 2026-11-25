"""
docs/build_docs.py - Builds the PDFs in docs/ from the markdown in docs/src/ (+ draws the architecture diagram).
Run from the project folder:   python docs/build_docs.py

Markdown supported: # ## ### headings, paragraphs, "- " bullets, "1. " lists, ``` code blocks,
| tables |, **bold**, `code`, and a line "<<<pagebreak>>>".
Placeholders like {{L:agent.py:SYSTEM_PROMPT}} become "agent.py line 23" using the CURRENT code,
so line numbers in the guides stay correct after you edit the code (just rebuild).
"""
import os
import re

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.platypus import (KeepTogether, ListFlowable, ListItem, PageBreak, Paragraph, Preformatted,
                                SimpleDocTemplate, Spacer, Table, TableStyle)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS = os.path.join(ROOT, "docs")

# ---------- Fonts (Arial/Consolas on Windows for Rs, quotes etc.; Helvetica fallback) ----------
FONT, BOLD, MONO = "Helvetica", "Helvetica-Bold", "Courier"
try:
    pdfmetrics.registerFont(TTFont("Arial", "C:/Windows/Fonts/arial.ttf"))
    pdfmetrics.registerFont(TTFont("Arial-Bold", "C:/Windows/Fonts/arialbd.ttf"))
    pdfmetrics.registerFont(TTFont("Consolas", "C:/Windows/Fonts/consola.ttf"))
    FONT, BOLD, MONO = "Arial", "Arial-Bold", "Consolas"
    from reportlab.lib.fonts import addMapping
    addMapping("Arial", 0, 0, "Arial"); addMapping("Arial", 1, 0, "Arial-Bold")
except Exception:
    pass

INK, ACCENT, SOFT = colors.HexColor("#1d2733"), colors.HexColor("#b45309"), colors.HexColor("#f4f6f8")
S = {
    "h1": ParagraphStyle("h1", fontName=BOLD, fontSize=19, leading=23, spaceAfter=8, textColor=INK),
    "h2": ParagraphStyle("h2", fontName=BOLD, fontSize=14, leading=18, spaceBefore=10, spaceAfter=5, textColor=ACCENT),
    "h3": ParagraphStyle("h3", fontName=BOLD, fontSize=11.5, leading=15, spaceBefore=7, spaceAfter=3, textColor=INK),
    "p": ParagraphStyle("p", fontName=FONT, fontSize=10, leading=14, spaceAfter=5, textColor=INK),
    "code": ParagraphStyle("code", fontName=MONO, fontSize=8.3, leading=10.4, backColor=SOFT, borderPadding=5,
                           spaceBefore=3, spaceAfter=8, textColor=INK),
    "cell": ParagraphStyle("cell", fontName=FONT, fontSize=8.8, leading=11.5, textColor=INK),
}


# ---------- Line-number placeholders ----------
def find_line(fname, anchor):
    path = os.path.join(ROOT, fname)
    for i, line in enumerate(open(path, encoding="utf-8"), 1):
        if anchor in line:
            return i
    raise SystemExit(f"Anchor not found: {fname}: {anchor!r}  (update the guide)")


def resolve(text):
    return re.sub(r"\{\{L:([^:}]+):([^}]+)\}\}",
                  lambda m: f"{m.group(1)} line {find_line(m.group(1), m.group(2))}", text)


# ---------- Tiny markdown -> reportlab ----------
def inline(text):
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("₹", "Rs ")
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"`([^`]+)`", rf'<font face="{MONO}" color="#7c2d12">\1</font>', text)
    return text


def md_to_flowables(md, width):
    out, lines, i = [], resolve(md).splitlines(), 0
    while i < len(lines):
        ln = lines[i]
        if ln.strip() == "<<<pagebreak>>>":
            out.append(PageBreak()); i += 1
        elif ln.startswith("```"):
            j = i + 1
            while j < len(lines) and not lines[j].startswith("```"):
                j += 1
            out.append(Preformatted("\n".join(lines[i + 1:j]), S["code"], maxLineLength=104))
            i = j + 1
        elif ln.startswith("### "):
            out.append(Paragraph(inline(ln[4:]), S["h3"])); i += 1
        elif ln.startswith("## "):
            out.append(Paragraph(inline(ln[3:]), S["h2"])); i += 1
        elif ln.startswith("# "):
            out.append(Paragraph(inline(ln[2:]), S["h1"])); i += 1
        elif ln.startswith("|"):
            rows = []
            while i < len(lines) and lines[i].startswith("|"):
                cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
                if not all(re.fullmatch(r":?-+:?", c) for c in cells):
                    rows.append([Paragraph(inline(c), S["cell"]) for c in cells])
                i += 1
            t = Table(rows, colWidths=[width / len(rows[0])] * len(rows[0]), repeatRows=1)
            t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cbd2d9")),
                                   ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#fde68a")),
                                   ("VALIGN", (0, 0), (-1, -1), "TOP")]))
            out += [t, Spacer(1, 6)]
        elif re.match(r"^\s*(- |\d+\. )", ln):
            items, numbered = [], bool(re.match(r"^\s*\d+\. ", ln))
            while i < len(lines) and re.match(r"^\s*(- |\d+\. )", lines[i]):
                txt = re.sub(r"^\s*(- |\d+\. )", "", lines[i])
                items.append(ListItem(Paragraph(inline(txt), S["p"]), leftIndent=12))
                i += 1
            out.append(ListFlowable(items, bulletType="1" if numbered else "bullet", start="1" if numbered else None,
                                    leftIndent=14, bulletFontName=FONT, bulletFontSize=9))
        elif ln.strip() == "":
            i += 1
        else:
            para = [ln]; i += 1
            while i < len(lines) and lines[i].strip() and not re.match(r"^(#|```|\||\s*- |\s*\d+\. |<<<)", lines[i]):
                para.append(lines[i]); i += 1
            out.append(Paragraph(inline(" ".join(para)), S["p"]))
    return out


def footer(title):
    def draw(c, doc):
        c.setFont(FONT, 8); c.setFillColor(colors.grey)
        c.drawString(15 * mm, 10 * mm, f"SunNova AI Sales Voice Agent - {title}")
        c.drawRightString(A4[0] - 15 * mm, 10 * mm, f"Page {doc.page}")
    return draw


def build_pdf(src, dst, title):
    doc = SimpleDocTemplate(os.path.join(DOCS, dst), pagesize=A4, title=title, author="SunNova MVP",
                            leftMargin=16 * mm, rightMargin=16 * mm, topMargin=15 * mm, bottomMargin=17 * mm)
    md = open(os.path.join(DOCS, "src", src), encoding="utf-8").read()
    doc.build(md_to_flowables(md, doc.width), onFirstPage=footer(title), onLaterPages=footer(title))
    print("built", dst)


# ---------- Architecture diagram (drawn with shapes) ----------
COL = {"client": "#dbeafe", "api": "#e0e7ff", "ai": "#fef3c7", "data": "#dcfce7", "async": "#fce7f3", "ops": "#f1f5f9"}


def box(c, x, y, w, h, title, lines=(), kind="api"):
    c.setFillColor(colors.HexColor(COL[kind])); c.setStrokeColor(colors.HexColor("#475569")); c.setLineWidth(0.9)
    c.roundRect(x, y, w, h, 6, fill=1, stroke=1)
    c.setFillColor(INK); c.setFont(BOLD, 9.5)
    c.drawCentredString(x + w / 2, y + h - 13, title)
    c.setFont(FONT, 7.6)
    for k, line in enumerate(lines):
        c.drawCentredString(x + w / 2, y + h - 25 - k * 9.5, line)


def arrow(c, x1, y1, x2, y2, label="", dashed=False, both=False, lx=0, ly=0):
    import math
    c.setStrokeColor(colors.HexColor("#334155")); c.setLineWidth(1.1)
    c.setDash(4, 3) if dashed else c.setDash()
    c.line(x1, y1, x2, y2); c.setDash()

    def head(xa, ya, xb, yb):
        ang, L = math.atan2(yb - ya, xb - xa), 7
        p = c.beginPath(); p.moveTo(xb, yb)
        p.lineTo(xb - L * math.cos(ang - 0.4), yb - L * math.sin(ang - 0.4))
        p.lineTo(xb - L * math.cos(ang + 0.4), yb - L * math.sin(ang + 0.4)); p.close()
        c.setFillColor(colors.HexColor("#334155")); c.drawPath(p, fill=1, stroke=0)
    head(x1, y1, x2, y2)
    if both:
        head(x2, y2, x1, y1)
    if label:
        c.setFont(FONT, 7); c.setFillColor(colors.HexColor("#7c2d12"))
        c.drawCentredString((x1 + x2) / 2 + lx, (y1 + y2) / 2 + 3 + ly, label)


def legend(c, x, y, items):
    c.setFont(BOLD, 9); c.setFillColor(INK); c.drawString(x, y, "Legend")
    for k, (kind, text) in enumerate(items):
        yy = y - 14 - k * 13
        c.setFillColor(colors.HexColor(COL[kind])); c.setStrokeColor(colors.HexColor("#475569"))
        c.rect(x, yy - 2, 14, 9, fill=1, stroke=1)
        c.setFillColor(INK); c.setFont(FONT, 7.8); c.drawString(x + 19, yy, text)
    yy = y - 14 - len(items) * 13
    arrow(c, x, yy + 2, x + 14, yy + 2); c.setFont(FONT, 7.8); c.setFillColor(INK); c.drawString(x + 19, yy, "Request / data flow")
    arrow(c, x, yy - 11, x + 14, yy - 11, dashed=True); c.drawString(x + 19, yy - 13, "Fallback / async / optional")


def page_title(c, title, sub):
    W, H = landscape(A4)
    c.setFont(BOLD, 16); c.setFillColor(INK); c.drawString(28, H - 34, title)
    c.setFont(FONT, 9); c.setFillColor(colors.HexColor("#475569")); c.drawString(28, H - 48, sub)


def draw_architecture():
    W, H = landscape(A4)
    c = canvas.Canvas(os.path.join(DOCS, "architecture.pdf"), pagesize=(W, H))
    c.setTitle("SunNova AI Sales Voice Agent - Architecture")

    # ===== Page 1: PROTOTYPE =====
    page_title(c, "1. Prototype architecture (what runs on the laptop today)",
               "One Python process (FastAPI) + browser. Free browser voice. OpenAI for the brain, offline rule-based fallback.")
    box(c, 28, 300, 150, 175, "Browser - index.html", ["", "Mic -> Web Speech API (STT)", "speechSynthesis (TTS) -> Speaker",
        "Language switch EN / HI", "Text-chat fallback box", "Live lead card + tool log"], "client")
    box(c, 28, 40, 150, 80, "Browser - dashboard.html", ["KPIs: calls, hot leads,", "bookings, conversion,",
        "charts, summaries", "(auto-refresh 5 s)"], "client")
    box(c, 225, 330, 135, 115, "FastAPI server", ["main.py", "REST API (JSON over HTTP)", "/api/call/start", "/api/call/{id}/message",
        "/api/call/{id}/end", "/api/dashboard"], "api")
    box(c, 405, 330, 150, 115, "Agent loop", ["agent.py", "Session = memory of call", "(messages + lead record)",
        "LLM -> tools -> LLM ... -> reply", "max 6 tool steps"], "ai")
    box(c, 405, 470, 150, 62, "llm.py (only LLM file)", ["OpenAI chat.completions", "tool calling, gpt-4o-mini"], "ai")
    box(c, 600, 470, 140, 62, "fallback.py", ["Offline rule-based brain", "(no key / API error)"], "ai")
    box(c, 405, 170, 150, 115, "tools.py", ["search_kb", "update_lead (+ lead scoring)", "check_slots", "book_appointment",
        "errors -> message, not crash"], "ai")
    box(c, 600, 250, 140, 70, "rag.py  (RAG)", ["TF-IDF vectors +", "cosine similarity", "top-2 chunks"], "ai")
    box(c, 770, 250, 55, 70, "kb.md", ["products", "pricing", "subsidy", "FAQs"], "data")
    box(c, 600, 90, 225, 115, "db.py -> SQLite crm.db (CRM)", ["leads: name, city, need, budget, timeline,",
        "score, sentiment, do_not_call, status", "appointments: slot UNIQUE (no double booking)",
        "calls: transcript, summary, insights", "Seeded with 6 demo leads"], "data")
    box(c, 225, 170, 135, 95, "Post-call summary", ["agent.end_call()", "llm.summarize() -> JSON", "summary, sentiment,",
        "insights -> calls table", "(inline in prototype)"], "async")

    arrow(c, 178, 400, 225, 400, "text", both=True, ly=2)
    arrow(c, 360, 388, 405, 388, "", both=True)
    arrow(c, 480, 445, 480, 470, "", both=True)
    arrow(c, 555, 501, 600, 501, "if error", dashed=True)
    arrow(c, 480, 330, 480, 285, "tool calls", both=True, lx=22)
    arrow(c, 555, 260, 600, 280, "search_kb")
    arrow(c, 740, 285, 770, 285, "")
    arrow(c, 555, 200, 600, 170, "update / book", lx=-30, ly=-12)
    arrow(c, 292, 330, 292, 265, "End call", lx=-24)
    arrow(c, 360, 200, 600, 120, "save", dashed=False, lx=-40, ly=-14)
    arrow(c, 600, 100, 178, 80, "GET /api/dashboard", lx=-20, ly=-14)
    legend(c, 28, 285, [("client", "Browser / user side"), ("api", "Web server / gateway"), ("ai", "AI agent, LLM, tools, RAG"),
                       ("data", "Data / CRM / knowledge"), ("async", "Post-call processing")])
    c.setFont(FONT, 8); c.setFillColor(colors.HexColor("#475569"))
    c.drawString(230, 32, "Flow of one turn: caller speaks -> browser STT -> text to /message -> agent asks LLM -> LLM calls tools (RAG, CRM, slots)")
    c.drawString(230, 21, "-> LLM writes reply -> JSON back -> browser TTS speaks it. End call -> summary + insights -> CRM -> dashboard.")
    c.showPage()

    # ===== Page 2: PRODUCTION =====
    page_title(c, "2. Production architecture (target for 1,00,000+ users)",
               "Stateless services behind a load balancer, streaming voice, shared session state in Redis, async workers, managed data stores.")
    box(c, 22, 420, 120, 75, "Caller (phone)", ["PSTN / SIP via", "Exotel / Twilio", "media stream"], "client")
    box(c, 22, 320, 120, 70, "Web / app widget", ["WebRTC mic + speaker", "same API"], "client")
    box(c, 22, 95, 120, 85, "Sales dashboard", ["React / BI tool", "role-based login", "(read replicas)"], "client")
    box(c, 172, 345, 125, 130, "Load balancer +", ["API / WebSocket gateway", "", "TLS, auth, rate limits", "routes media streams",
        "multi-region (DNS)"], "api")
    box(c, 327, 380, 140, 95, "Voice gateway pods", ["stateless, autoscaled", "(Kubernetes / ECS)", "VAD + barge-in",
        "streams audio both ways"], "api")
    box(c, 500, 445, 120, 50, "Streaming STT", ["Deepgram / Google /", "Whisper (Hindi+EN)"], "ai")
    box(c, 500, 380, 120, 50, "Streaming TTS", ["ElevenLabs / Azure /", "Google Neural voices"], "ai")
    box(c, 327, 225, 140, 120, "Agent service pods", ["LLM + tool calling", "(OpenAI / Claude / Gemini", "via provider-agnostic", "llm layer)",
        "guardrails, prompt", "versioning"], "ai")
    box(c, 500, 270, 120, 75, "Tools service", ["search_kb, update_lead,", "check_slots, book,", "WhatsApp / SMS confirm"], "ai")
    box(c, 650, 400, 170, 60, "Redis", ["session memory per call_id", "(any pod can continue a call)"], "data")
    box(c, 650, 310, 170, 65, "Vector DB (RAG)", ["pgvector / Pinecone / Qdrant", "neural embeddings", "KB ingestion pipeline"], "data")
    box(c, 650, 200, 170, 85, "CRM data", ["Postgres (primary + read replicas)", "sync to HubSpot / Salesforce", "via their REST APIs + webhooks",
        "encrypted at rest"], "data")
    box(c, 327, 95, 140, 95, "Queue", ["SQS / Kafka / Redis Streams", "event: call_ended", "retries + dead-letter queue"], "async")
    box(c, 500, 95, 140, 95, "Worker pool", ["summary + insights", "sentiment, QA scoring", "CRM sync, follow-ups",
        "autoscale on queue depth"], "async")
    box(c, 172, 95, 125, 85, "Analytics store", ["warehouse / ClickHouse", "KPIs, conversion,", "cost per lead"], "data")
    box(c, 650, 95, 170, 80, "Ops & security", ["Logs, traces, metrics, alerts", "Secrets in KMS / Vault", "RBAC, audit log, PII masking",
        "consent + DPDP retention"], "ops")

    arrow(c, 142, 457, 172, 430, "audio")
    arrow(c, 142, 355, 172, 380, "")
    arrow(c, 297, 420, 327, 420, "", both=True)
    arrow(c, 467, 460, 500, 470, "audio")
    arrow(c, 500, 405, 467, 405, "speech")
    arrow(c, 397, 380, 397, 345, "text", both=True, lx=14)
    arrow(c, 467, 300, 500, 300, "", both=True)
    # elbow connector agent -> Redis (goes around the TTS box)
    c.setStrokeColor(colors.HexColor("#334155")); c.setLineWidth(1.1)
    c.line(467, 355, 635, 355); c.line(635, 355, 635, 430)
    arrow(c, 635, 430, 650, 430)
    c.setFont(FONT, 7); c.setFillColor(colors.HexColor("#7c2d12")); c.drawString(520, 359, "session state (read/write)")
    arrow(c, 620, 330, 650, 340, "")
    arrow(c, 620, 290, 650, 255, "")
    arrow(c, 397, 225, 397, 190, "call_ended", lx=-26)
    arrow(c, 467, 142, 500, 142, "")
    arrow(c, 640, 160, 690, 200, "write", lx=-10)
    arrow(c, 500, 120, 297, 120, "events", dashed=True, ly=-14)
    arrow(c, 172, 138, 142, 138, "")
    legend(c, 28, 300, [("client", "Callers / users"), ("api", "Edge & gateways"), ("ai", "AI services"), ("data", "Data stores"),
                       ("async", "Async post-call"), ("ops", "Ops / security")])
    c.setFont(FONT, 8); c.setFillColor(colors.HexColor("#475569"))
    c.drawString(172, 62, "Why it scales: every pod is stateless (memory lives in Redis), so the load balancer can send any request to any pod;")
    c.drawString(172, 51, "pods autoscale on CPU / active calls; slow work (summaries, CRM sync) goes through the queue so calls never wait;")
    c.drawString(172, 40, "Postgres read replicas serve the dashboard; managed vector DB scales retrieval; deploy in 2 regions for failover.")
    c.showPage()
    c.save()
    print("built architecture.pdf")


if __name__ == "__main__":
    draw_architecture()
    build_pdf("project_explained.md", "project_explained.pdf", "Project Explained (Beginner Guide)")
    build_pdf("live_coding_guide.md", "live_coding_guide.pdf", "Live Coding Guide")
    build_pdf("interview_prep.md", "interview_prep.pdf", "Interview Prep")
