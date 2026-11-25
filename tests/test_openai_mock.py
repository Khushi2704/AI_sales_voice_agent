"""
tests/test_openai_mock.py - Tests the OpenAI code path WITHOUT a real key.
We replace llm.client with a fake object that returns OpenAI-shaped responses.
Run:  python -m tests.test_openai_mock
"""
import json
import os
from types import SimpleNamespace as NS

import db
db.DB_PATH = "test_mock.db"
if os.path.exists(db.DB_PATH):
    os.remove(db.DB_PATH)
db.init_db()
import agent
import llm


def tool_call(id_, name, args):
    return NS(id=id_, type="function", function=NS(name=name, arguments=json.dumps(args)))


def response(content=None, calls=None):
    return NS(choices=[NS(message=NS(content=content, tool_calls=calls))])


class FakeCompletions:
    """Turn 1: LLM asks for 2 tools at once. Turn 2: LLM writes the final answer."""
    def __init__(self):
        self.step, self.seen = 0, []

    def create(self, **kw):
        self.seen.append({**kw, "messages": list(kw["messages"])})   # copy: the list keeps growing
        if kw.get("response_format"):                       # summarize() call
            return response(json.dumps({"summary": "Rahul asked about subsidy.", "sentiment": "positive",
                                        "insights": ["Subsidy is key"]}))
        self.step += 1
        if self.step == 1:
            return response(None, [tool_call("c1", "update_lead", {"name": "Rahul", "sentiment": "positive"}),
                                   tool_call("c2", "search_kb", {"query": "subsidy 3 kW"})])
        return response("You can get up to Rs 78,000 subsidy, Rahul. Which city are you in?")


class Broken:
    def create(self, **kw):
        raise TimeoutError("simulated network failure")


checks = []
fake = FakeCompletions()
llm.client = NS(chat=NS(completions=fake))
s = agent.Session("en")
out = agent.handle_turn(s, "I'm Rahul, how much subsidy for 3 kW?")
print("OpenAI-path reply:", out["reply"]); print("tools:", [e["tool"] for e in out["events"]])
checks.append(("parallel tool calls executed", [e["tool"] for e in out["events"]] == ["update_lead", "search_kb"]))
checks.append(("lead saved from tool call", out["lead"]["name"] == "Rahul"))
roles = [m["role"] for m in fake.seen[-1]["messages"]]
print("roles sent on 2nd request:", roles)
checks.append(("memory format system/assistant/user/assistant/tool/tool", roles == ["system", "assistant", "user", "assistant", "tool", "tool"]))
checks.append(("tools were sent to the API", len(fake.seen[0]["tools"]) == 5))
checks.append(("lead record injected in system prompt", '"name": "Rahul"' in fake.seen[-1]["messages"][0]["content"]))
end = agent.end_call(s)
checks.append(("summarize parsed JSON", end["summary"] == "Rahul asked about subsidy." and end["lead"]["sentiment"] == "positive"))

# API failure -> fallback must answer, no crash
llm.client = NS(chat=NS(completions=Broken()))
s2 = agent.Session("en")
out2 = agent.handle_turn(s2, "My name is Neha")
print("After API failure, fallback reply:", out2["reply"])
checks.append(("API failure falls back", "Neha" in out2["reply"]))
checks.append(("badge shows offline after failure", out2["mode"] == "offline-fallback"))

# Rate limit on the first model -> the next model in the chain answers
import httpx
from openai import RateLimitError


class BusyFirstModel:
    def __init__(self):
        self.models = []

    def create(self, **kw):
        self.models.append(kw["model"])
        if len(self.models) == 1:
            raise RateLimitError("busy", response=httpx.Response(429, request=httpx.Request("POST", "http://x")),
                                 body=None)
        return response("Hi! Which city are you in?")


busy = BusyFirstModel()
llm.client = NS(chat=NS(completions=busy))
llm.MODELS = ["model-a", "model-b"]
out3 = agent.handle_turn(agent.Session("en"), "hello")
print("rate-limit chain tried:", busy.models, "->", out3["mode"])
checks.append(("rate limit -> next model in chain", busy.models == ["model-a", "model-b"]
               and out3["mode"] == "openai:model-b"))

# History trimming: old tool messages are dropped, everything that was SAID is kept
msgs = [{"role": "system", "content": "S"}]
for i in range(4):
    msgs += [{"role": "user", "content": f"u{i}"},
             {"role": "assistant", "content": None,
              "tool_calls": [{"id": f"t{i}", "type": "function", "function": {"name": "x", "arguments": "{}"}}]},
             {"role": "tool", "tool_call_id": f"t{i}", "content": "{}"},
             {"role": "assistant", "content": f"a{i}"}]
trimmed = llm.trim_history(msgs)
print("trimmed roles:", [m["role"] for m in trimmed])
checks.append(("trim keeps old talk, drops old tools", [m["role"] for m in trimmed].count("tool") == 2
               and [m["content"] for m in trimmed if m["role"] == "user"] == ["u0", "u1", "u2", "u3"]))

print("\n=== CHECKS ===")
for n, ok in checks:
    print(("PASS " if ok else "FAIL ") + n)
os.remove(db.DB_PATH)
