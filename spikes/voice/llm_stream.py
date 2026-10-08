"""Streaming probes: time to first token, to the end of the first sentence, and to the end, for one prompt. The backend adapters do not
stream, so first-token latency can only be measured here. Local Ollama is free; Groq and Gemini calls go through the budget registry and telemetry."""
import json
import os
import re
import time
from dataclasses import dataclass

import httpx

SENTENCE_END = re.compile(r"[.!?](\s|$)")


@dataclass
class Streamed:
    provider: str
    model: str
    ttft_s: float | None       # request sent -> first non-empty text
    first_sentence_s: float | None
    total_s: float
    text: str
    tokens_out: int | None = None
    error: str = ""


class _Clock:
    """Feed it text pieces as they arrive; it notes when the first token and the first sentence were complete."""
    def __init__(self):
        self.t0, self.ttft, self.first_sentence, self.text = time.perf_counter(), None, None, ""

    def feed(self, piece: str):
        if not piece:
            return
        now = time.perf_counter() - self.t0
        if self.ttft is None:
            self.ttft = now
        self.text += piece
        if self.first_sentence is None and SENTENCE_END.search(self.text):
            self.first_sentence = now

    def done(self, provider, model, tokens=None, error=""):
        total = time.perf_counter() - self.t0
        return Streamed(provider, model, self.ttft, self.first_sentence if self.first_sentence is not None else (total if self.text else None),
                        total, self.text, tokens, error)


def ollama_stream(model, system, user, json_mode, max_tokens, host=None, timeout=120.0) -> Streamed:
    host = (host or os.environ.get("OLLAMA_HOST") or "http://localhost:11434").rstrip("/")
    body = {"model": model, "stream": True, "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "options": {"temperature": 0, "num_predict": max_tokens}}
    if json_mode:
        body["format"] = "json"
    clock, tokens = _Clock(), None
    with httpx.stream("POST", f"{host}/api/chat", json=body, timeout=timeout) as r:
        r.raise_for_status()
        for line in r.iter_lines():
            if not line:
                continue
            data = json.loads(line)
            clock.feed((data.get("message") or {}).get("content", ""))
            if data.get("done"):
                tokens = data.get("eval_count")
    return clock.done("ollama", model, tokens)


def openai_stream(provider, model, base_url, key, system, user, json_mode, max_tokens, headroom=1000, effort=None, auth="bearer", timeout=60.0) -> Streamed:
    """Any OpenAI-compatible endpoint (Groq, ...): SSE chunks with choices[0].delta.content."""
    body = {"model": model, "temperature": 0, "stream": True, "max_tokens": max_tokens + headroom,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
    if json_mode:
        body["response_format"] = {"type": "json_object"}
    if effort:
        body["reasoning_effort"] = effort
    headers = {"Authorization": f"Bearer {key}"} if auth == "bearer" else {"api-key": key}
    clock = _Clock()
    with httpx.stream("POST", f"{base_url.rstrip('/')}/chat/completions", json=body, headers=headers, timeout=timeout) as r:
        if r.status_code >= 400:
            r.read()
            r.raise_for_status()
        for line in r.iter_lines():
            if not line.startswith("data:"):
                continue
            payload = line[5:].strip()
            if payload == "[DONE]":
                break
            for choice in json.loads(payload).get("choices") or []:
                clock.feed((choice.get("delta") or {}).get("content") or "")
    return clock.done(provider, model)


def gemini_stream(model, key, system, user, json_mode, max_tokens, headroom=1500, timeout=60.0) -> Streamed:
    gen = {"temperature": 0, "maxOutputTokens": max_tokens + headroom}
    if json_mode:
        gen["responseMimeType"] = "application/json"
    body = {"systemInstruction": {"parts": [{"text": system}]}, "contents": [{"role": "user", "parts": [{"text": user}]}], "generationConfig": gen}
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:streamGenerateContent?alt=sse"
    clock = _Clock()
    with httpx.stream("POST", url, json=body, headers={"x-goog-api-key": key}, timeout=timeout) as r:
        if r.status_code >= 400:
            r.read()
            r.raise_for_status()
        for line in r.iter_lines():
            if not line.startswith("data:"):
                continue
            for cand in json.loads(line[5:]).get("candidates") or []:
                for part in (cand.get("content") or {}).get("parts") or []:
                    if not part.get("thought"):
                        clock.feed(part.get("text", ""))
    return clock.done("gemini", model)
