"""
db.py - The CRM (Customer Relationship Management) database.

We use SQLite: a whole database stored in ONE file (crm.db). No server needed.
Three tables:
  leads         - one row per person we talk to (name, city, budget, score...)
  appointments  - booked site visits. slot is UNIQUE -> the database itself
                  refuses double bookings.
  calls         - one row per call (transcript, summary, insights)

In production you would swap this for Postgres, or push the same data into
HubSpot / Salesforce through their APIs (see README "CRM integration").
"""
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta

DB_PATH = "crm.db"


@contextmanager
def get_conn():
    """Open a connection, commit if all went well, ALWAYS close it.
    row_factory lets us read rows like dicts: row["name"]."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()          # (uncommitted changes are rolled back on error)


def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M")


# ---------- Create tables ----------
def init_db():
    with get_conn() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS leads (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT,
            phone       TEXT,
            city        TEXT,
            need        TEXT,      -- e.g. "3 kW for home" or "bill Rs 3000/month"
            budget      TEXT,      -- e.g. "2 lakh"
            timeline    TEXT,      -- e.g. "within 1 month"
            language    TEXT DEFAULT 'en',
            score       TEXT DEFAULT 'cold',     -- hot / warm / cold
            sentiment   TEXT DEFAULT 'neutral',  -- positive / neutral / negative
            do_not_call INTEGER DEFAULT 0,
            status      TEXT DEFAULT 'new',      -- new / qualified / booked
            created_at  TEXT
        );
        CREATE TABLE IF NOT EXISTS appointments (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            lead_id    INTEGER,
            slot       TEXT UNIQUE,              -- UNIQUE = no double booking
            created_at TEXT
        );
        CREATE TABLE IF NOT EXISTS calls (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            lead_id    INTEGER,
            started_at TEXT,
            ended_at   TEXT,
            transcript TEXT,
            summary    TEXT,
            insights   TEXT
        );
        """)


# ---------- Leads ----------
LEAD_FIELDS = ["name", "phone", "city", "need", "budget", "timeline",
               "language", "score", "sentiment", "do_not_call", "status"]


def create_lead(language="en"):
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO leads (language, created_at) VALUES (?, ?)", (language, now()))
        return cur.lastrowid


def update_lead(lead_id, fields):
    """Update only the columns we know about (protects against bad keys)."""
    fields = {k: v for k, v in fields.items() if k in LEAD_FIELDS and v not in (None, "")}
    if not fields:
        return get_lead(lead_id)
    sets = ", ".join(f"{k} = ?" for k in fields)
    with get_conn() as conn:
        conn.execute(f"UPDATE leads SET {sets} WHERE id = ?", (*fields.values(), lead_id))
    return get_lead(lead_id)


def get_lead(lead_id):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM leads WHERE id = ?", (lead_id,)).fetchone()
        return dict(row) if row else None


# ---------- Appointments ----------
SLOT_TIMES = ["10:00", "12:00", "15:00", "17:00"]   # change visit times here
DAYS_AHEAD = 3                                     # how many days to offer


def all_slots():
    """Every possible slot for the next DAYS_AHEAD working days (Sundays skipped)."""
    slots, day = [], datetime.now().date()
    while len(slots) < DAYS_AHEAD * len(SLOT_TIMES):
        day += timedelta(days=1)
        if day.weekday() == 6:          # 6 = Sunday, closed
            continue
        slots += [f"{day} {t}" for t in SLOT_TIMES]
    return slots


def free_slots():
    with get_conn() as conn:
        taken = {r["slot"] for r in conn.execute("SELECT slot FROM appointments")}
    return [s for s in all_slots() if s not in taken]


def lead_booking(lead_id):
    """The slot this lead already booked, or None."""
    with get_conn() as conn:
        row = conn.execute("SELECT slot FROM appointments WHERE lead_id = ?", (lead_id,)).fetchone()
        return row["slot"] if row else None


def book_slot(lead_id, slot):
    """Returns (True, msg) on success, (False, reason) if invalid or already taken."""
    if slot not in all_slots():
        return False, f"'{slot}' is not a valid slot."
    try:
        with get_conn() as conn:
            conn.execute("INSERT INTO appointments (lead_id, slot, created_at) VALUES (?, ?, ?)",
                         (lead_id, slot, now()))
            conn.execute("UPDATE leads SET status = 'booked' WHERE id = ?", (lead_id,))
        return True, f"Booked {slot}"
    except sqlite3.IntegrityError:      # UNIQUE(slot) violated -> someone has it
        return False, f"Slot {slot} is already booked."


# ---------- Calls ----------
def create_call(lead_id):
    with get_conn() as conn:
        cur = conn.execute("INSERT INTO calls (lead_id, started_at) VALUES (?, ?)", (lead_id, now()))
        return cur.lastrowid


def finish_call(call_id, transcript, summary, insights):
    with get_conn() as conn:
        conn.execute("UPDATE calls SET ended_at=?, transcript=?, summary=?, insights=? WHERE id=?",
                     (now(), transcript, summary, json.dumps(insights), call_id))


# ---------- Dashboard ----------
def dashboard_data():
    with get_conn() as conn:
        leads = [dict(r) for r in conn.execute("SELECT * FROM leads ORDER BY id DESC")]
        appts = [dict(r) for r in conn.execute(
            "SELECT a.slot, a.lead_id, l.name, l.city FROM appointments a "
            "LEFT JOIN leads l ON l.id = a.lead_id ORDER BY a.slot")]
        calls = [dict(r) for r in conn.execute(
            "SELECT c.*, l.name, l.score, l.sentiment FROM calls c "
            "LEFT JOIN leads l ON l.id = c.lead_id WHERE c.summary IS NOT NULL ORDER BY c.id DESC")]
    for c in calls:
        c["insights"] = json.loads(c["insights"] or "[]")
    total_calls = len(calls)
    stats = {
        "total_calls": total_calls,
        "hot_leads": sum(1 for l in leads if l["score"] == "hot"),
        "warm_leads": sum(1 for l in leads if l["score"] == "warm"),
        "cold_leads": sum(1 for l in leads if l["score"] == "cold"),
        "bookings": len(appts),
        # conversion = calls that ended in a booking / all finished calls
        "conversion": round(100 * len(appts) / total_calls) if total_calls else 0,
        "positive": sum(1 for l in leads if l["sentiment"] == "positive"),
        "negative": sum(1 for l in leads if l["sentiment"] == "negative"),
    }
    return {"stats": stats, "leads": leads, "appointments": appts, "calls": calls}


# ---------- Demo seed data ----------
SEED = [
    # name, phone, city, need, budget, timeline, lang, score, sentiment, status, summary, insights, book?
    ("Rahul Sharma", "98100xxxxx", "Delhi", "3 kW, bill Rs 3,500/month", "2 lakh", "within 1 month", "en",
     "hot", "positive", "booked", "Rahul wants a 3 kW system for his home in Delhi. Asked about subsidy and EMI. Booked a site visit.",
     ["Price-sensitive: asked about EMI twice", "Subsidy is the main buying reason"], True),
    ("Priya Verma", "98765xxxxx", "Jaipur", "5 kW for a bungalow", "3 lakh", "2-3 months", "hi",
     "warm", "positive", "qualified", "Priya (spoke Hindi) is planning 5 kW in 2-3 months. Interested in battery backup.",
     ["Hindi-speaking lead", "Battery backup is an upsell opportunity"], False),
    ("Amit Patel", "99250xxxxx", "Ahmedabad", "10 kW for a shop", "5 lakh", "immediately", "en",
     "hot", "neutral", "booked", "Amit owns a shop and needs 10 kW urgently. Not eligible for residential subsidy. Booked visit.",
     ["Commercial lead: no subsidy, higher ticket size", "Urgent timeline"], True),
    ("Sneha Iyer", "97300xxxxx", "Pune", "2 kW, just exploring", "not sure", "next year", "en",
     "cold", "neutral", "new", "Sneha is only exploring and has no budget yet. Asked about payback period.",
     ["Early-stage lead: nurture with email content"], False),
    ("Vikram Singh", "98140xxxxx", "Chandigarh", "3 kW", "1.5 lakh", "6 months", "hi",
     "warm", "negative", "qualified", "Vikram is worried about power-cut performance and price. Needs follow-up.",
     ["Objection: on-grid does not work in power cuts", "Competitor quote was cheaper"], False),
    ("Neha Gupta", "98390xxxxx", "Lucknow", "3 kW, bill Rs 3,000/month", "2 lakh", "within 1 month", "en",
     "hot", "positive", "booked", "Neha wants to install quickly before summer. Booked a site visit.",
     ["Seasonal demand: summer bills drive urgency"], True),
]


def seed_if_empty():
    """Fill the CRM with 6 sample past leads so the dashboard is not empty in the demo."""
    with get_conn() as conn:
        if conn.execute("SELECT COUNT(*) FROM leads").fetchone()[0] > 0:
            return
    free = free_slots()
    for i, (name, phone, city, need, budget, timeline, lang, score, senti, status,
            summary, insights, book) in enumerate(SEED):
        lead_id = create_lead(lang)
        update_lead(lead_id, dict(name=name, phone=phone, city=city, need=need, budget=budget,
                                  timeline=timeline, score=score, sentiment=senti, status=status))
        call_id = create_call(lead_id)
        finish_call(call_id, "(seeded demo call)", summary, insights)
        if book:
            book_slot(lead_id, free[i * 2])   # spread seeded bookings out
