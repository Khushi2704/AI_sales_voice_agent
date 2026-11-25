"""
llm.py - The ONLY file that talks to an LLM provider.

To swap provider/model you only edit this file:
  - change MODEL (or set the OPENAI_MODEL env variable), or
  - point base_url at any OpenAI-compatible API (Groq, Together, Ollama, Azure...), or
  - rewrite chat() and summarize() for another SDK, keeping the same return format.

If there is no API key, or the API call fails (no internet, quota, timeout),
we fall back to fallback.py, a simple rule-based "brain" that uses the same tools.
So the demo never crashes.
"""
import json
import logging
import os

import fallback
from openai import OpenAI, RateLimitError

log = logging.getLogger("llm")


def load_env_file(path=".env"):
    """Read KEY=value lines from .env (if it exists) so you don't have to set them in every terminal.
    Real environment variables win over the file."""
    if os.path.exists(path):
        for line in open(path, encoding="utf-8"):
            if "=" in line and not line.strip().startswith("#"):
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip().strip('"'))


load_env_file()

# One model, or a comma-separated list = fallback chain. If the first model hits its rate limit,
# we try the next one (each model has its own limit on Groq's free tier).
MODELS = [m.strip() for m in os.getenv("OPENAI_MODEL", "gpt-4o-mini").split(",") if m.strip()]
MODEL = MODELS[0]
KEEP_TURNS = 2            # send full tool details only for the last 2 caller turns (saves tokens)
API_KEY = os.getenv("OPENAI_API_KEY", "")
BASE_URL = os.getenv("OPENAI_BASE_URL") or None      # None = official OpenAI
TIMEOUT_SECONDS = 15      # give up quickly so the caller isn't left waiting

client = None
if API_KEY:
    client = OpenAI(api_key=API_KEY, base_url=BASE_URL, timeout=TIMEOUT_SECONDS, max_retries=0)

# Which brain answered the LAST turn (shown as the badge in the UI)
last_mode = f"openai:{MODEL}" if client else "offline-fallback"


def mode():
    return last_mode


def trim_history(messages):
    """Make the request smaller: for OLD turns keep only what was said (user/assistant text) and drop
    tool requests/results. The facts from those tools are already in the LEAD RECORD (system prompt)."""
    user_turns = [i for i, m in enumerate(messages) if m["role"] == "user"]
    if len(user_turns) <= KEEP_TURNS:
        return messages
    cut = user_turns[-KEEP_TURNS]
    old_talk = [m for m in messages[1:cut]
                if m["role"] in ("user", "assistant") and m.get("content") and not m.get("tool_calls")]
    return [messages[0]] + old_talk + messages[cut:]


def chat(messages, tools):
    """
    Send the conversation + tool descriptions to the LLM.
    Returns a plain dict (same shape for OpenAI and the fallback):
      {"content": "text reply or None",
       "tool_calls": [{"id": "...", "name": "...", "arguments": {...}}]}
    """
    global last_mode
    for model in (MODELS if client else []):
        try:
            resp = client.chat.completions.create(
                model=model, messages=trim_history(messages), tools=tools, temperature=0.3)
            msg = resp.choices[0].message
            calls = [{"id": tc.id, "name": tc.function.name,
                      "arguments": json.loads(tc.function.arguments or "{}")}
                     for tc in (msg.tool_calls or [])]
            last_mode = f"openai:{model}"
            return {"content": msg.content, "tool_calls": calls}
        except RateLimitError:
            log.warning("[LLM RATE LIMIT] %s is busy -> trying the next model", model)
        except Exception as e:
            log.error("[LLM ERROR] %s: %s -> using offline fallback for this turn", type(e).__name__, e)
            break
    last_mode = "offline-fallback"
    return fallback.chat(messages)          # the fallback gets the FULL history


SUMMARY_PROMPT = """You are a sales analyst. Read this sales call transcript and return ONLY JSON:
{"summary": "2-3 sentence summary in English",
 "sentiment": "positive|neutral|negative",
 "insights": ["3 short business insights: objections, interests, upsell chances, next action"]}"""


def summarize(transcript):
    """Post-call: summary + sentiment + insights as a dict."""
    for model in (MODELS if client else []):
        try:
            resp = client.chat.completions.create(
                model=model, temperature=0.2,
                response_format={"type": "json_object"},        # forces valid JSON
                messages=[{"role": "system", "content": SUMMARY_PROMPT},
                          {"role": "user", "content": transcript}])
            return json.loads(resp.choices[0].message.content)
        except Exception as e:
            log.error("[LLM ERROR] summarize with %s failed: %s", model, e)
    return fallback.summarize(transcript)
