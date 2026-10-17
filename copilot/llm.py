"""OpenRouter client for the Gemma 4 models (OpenAI-compatible chat completions
with tool calling). Falls back across models on rate limits / errors, and
caches responses so re-running the evaluation costs no quota."""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import time

from openai import OpenAI

from . import config


class LLM:
    def __init__(self, model: str | None = None, fallbacks: list[str] | None = None, cache_path: str | None = None):
        if not config.OPENROUTER_API_KEY:
            raise RuntimeError("OPENROUTER_API_KEY is not set (put it in .env)")
        self.client = OpenAI(base_url=config.OPENROUTER_BASE_URL, api_key=config.OPENROUTER_API_KEY,
                             default_headers={"HTTP-Referer": "https://github.com/adwaiyk/FlytBase-Asset-Intelligence-Copilot",
                                              "X-Title": "FlytBase Asset Intelligence Copilot"})
        self.models = [model or config.MODEL] + (fallbacks if fallbacks is not None else config.FALLBACK_MODELS)
        self.cache = sqlite3.connect(cache_path or config.DB_PATH.replace(".db", "") + "-llmcache.db",
                                     check_same_thread=False)
        self.cache.execute("CREATE TABLE IF NOT EXISTS c (k TEXT PRIMARY KEY, v TEXT)")
        self.last_model = None
        self.calls = 0

    def chat(self, messages: list[dict], tools: list[dict] | None = None, temperature: float = 0.1) -> dict:
        """Returns {"content": str, "tool_calls": [{"id","name","arguments"(dict)}], "model": str}."""
        key = hashlib.sha256(json.dumps([messages, tools, temperature], sort_keys=True, default=str).encode()).hexdigest()
        hit = self.cache.execute("SELECT v FROM c WHERE k=?", (key,)).fetchone()
        if hit:
            return json.loads(hit[0])
        err = None
        for model in self.models:
            for attempt in range(3):
                try:
                    kw = {"model": model, "messages": messages, "temperature": temperature}
                    if tools:
                        kw["tools"] = tools
                        kw["tool_choice"] = "auto"
                    resp = self.client.chat.completions.create(**kw)
                    self.calls += 1
                    if not resp.choices:
                        raise RuntimeError(f"empty response: {getattr(resp, 'error', None)}")
                    msg = resp.choices[0].message
                    calls = []
                    for tc in msg.tool_calls or []:
                        try:
                            args = json.loads(tc.function.arguments or "{}")
                        except json.JSONDecodeError:
                            args = {}
                        calls.append({"id": tc.id, "name": tc.function.name, "arguments": args})
                    content = msg.content or ""
                    if not calls and tools:
                        calls = _parse_text_tool_calls(content, {t["function"]["name"] for t in tools})
                        if calls:
                            content = ""
                    out = {"content": content, "tool_calls": calls, "model": model}
                    self.last_model = model
                    self.cache.execute("INSERT OR REPLACE INTO c VALUES (?,?)", (key, json.dumps(out)))
                    self.cache.commit()
                    return out
                except Exception as e:  # rate limit / provider error → retry, then next model
                    err = e
                    msg = str(e)
                    if "429" in msg or "rate" in msg.lower():
                        time.sleep(2 * (attempt + 1))
                        continue
                    if attempt == 0:
                        time.sleep(1)
                        continue
                    break
        raise RuntimeError(f"All models failed: {err}")


def _parse_text_tool_calls(content: str, names: set[str]) -> list[dict]:
    """Some providers return tool calls as JSON text; accept {"name":..,"arguments":{..}} blocks."""
    calls = []
    for m in re.finditer(r"\{[^{}]*\"name\"\s*:\s*\"(\w+)\"[^{}]*\"(?:arguments|parameters)\"\s*:\s*(\{.*?\})\s*\}", content, re.S):
        if m.group(1) in names:
            try:
                calls.append({"id": f"txt{len(calls)}", "name": m.group(1), "arguments": json.loads(m.group(2))})
            except json.JSONDecodeError:
                pass
    return calls
