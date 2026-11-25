"""
main.py - The web server (FastAPI). Run with:  uvicorn main:app --reload

Pages:
  GET  /             -> static/index.html      (the voice-call screen)
  GET  /dashboard    -> static/dashboard.html  (business dashboard)
API (JSON):
  POST /api/call/start            {language}       -> new call, greeting
  POST /api/call/{id}/message     {text, language} -> agent reply + tools used + lead card
  POST /api/call/{id}/end                          -> summary + insights
  GET  /api/dashboard                              -> stats, leads, appointments, calls
"""
import logging

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import agent
import db
import llm

# Logs go to the terminal: this is where you look when something breaks.
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
                    datefmt="%H:%M:%S")
log = logging.getLogger("main")

app = FastAPI(title="SunNova AI Sales Voice Agent")
app.mount("/static", StaticFiles(directory="static"), name="static")

# Active calls live in memory: {call_id: Session}.
# Production: store this in Redis so any server can continue any call.
SESSIONS = {}


@app.on_event("startup")
def startup():
    db.init_db()
    db.seed_if_empty()
    log.info("Server ready. LLM mode = %s", llm.mode())


class StartReq(BaseModel):
    language: str = "en"


class MessageReq(BaseModel):
    text: str = ""
    language: str | None = None


def get_session(call_id):
    s = SESSIONS.get(call_id)
    if not s:
        raise HTTPException(404, "Call not found or already ended. Click 'Start call'.")
    return s


@app.get("/")
def home():
    return FileResponse("static/index.html")


@app.get("/dashboard")
def dashboard_page():
    return FileResponse("static/dashboard.html")


@app.post("/api/call/start")
def start_call(req: StartReq):
    lang = req.language if req.language in agent.LANG_NAMES else "en"
    s = agent.Session(lang)
    SESSIONS[s.call_id] = s
    log.info("[CALL %s] started, lead %s, lang=%s", s.call_id, s.lead_id, lang)
    return {"call_id": s.call_id, "lead_id": s.lead_id, "reply": agent.text_for(agent.GREETING, lang), "mode": llm.mode()}


@app.post("/api/call/{call_id}/message")
def message(call_id: int, req: MessageReq):
    s = get_session(call_id)
    log.info("[CALL %s] caller: %s", call_id, req.text)
    out = agent.handle_turn(s, req.text, req.language)
    log.info("[CALL %s] agent: %s", call_id, out["reply"])
    return out


@app.post("/api/call/{call_id}/end")
def end(call_id: int):
    s = get_session(call_id)
    out = agent.end_call(s)
    del SESSIONS[call_id]
    log.info("[CALL %s] ended. Summary: %s", call_id, out["summary"])
    return out


@app.get("/api/dashboard")
def dashboard():
    return db.dashboard_data()


@app.exception_handler(Exception)
async def any_error(request: Request, exc: Exception):
    """Last safety net: never show a crash page, always return friendly JSON."""
    log.exception("[SERVER ERROR] %s", request.url.path)
    return JSONResponse(status_code=500, content={"error": "Something went wrong on the server. Check the terminal logs."})
