"""Gemini adapter (REST). Needs GEMINI_API_KEY + GEMINI_MODEL (pick from `python -m app.list_models`).
Thinking-capable models can spend the output budget on reasoning and return truncated/empty text,
so we add headroom (GEMINI_TOKEN_HEADROOM, default 1500) and fail loudly on empty output."""
import json
import os
import httpx


class GeminiLLM:
    def __init__(self, model=None, api_key=None, timeout=60.0):
        self.model = model or os.environ.get("GEMINI_MODEL")
        self.key = api_key or os.environ.get("GEMINI_API_KEY")
        if not self.model or not self.key:
            raise RuntimeError("Set GEMINI_MODEL and GEMINI_API_KEY (never commit keys)")
        self.name = f"gemini:{self.model}"
        self.timeout = timeout
        self.headroom = int(os.environ.get("GEMINI_TOKEN_HEADROOM", "1500"))

    def _call(self, system, user, max_tokens, json_mode):
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent"
        gen = {"temperature": 0, "maxOutputTokens": max_tokens + self.headroom}
        if json_mode:
            gen["responseMimeType"] = "application/json"
        body = {"systemInstruction": {"parts": [{"text": system}]},
                "contents": [{"role": "user", "parts": [{"text": user}]}],
                "generationConfig": gen}
        r = httpx.post(url, json=body, headers={"x-goog-api-key": self.key}, timeout=self.timeout)
        r.raise_for_status()
        cand = r.json()["candidates"][0]
        parts = cand.get("content", {}).get("parts") or []
        text = "".join(p.get("text", "") for p in parts if not p.get("thought"))
        if not text.strip():
            raise RuntimeError(f"empty response, finishReason={cand.get('finishReason')}")
        return text

    def complete_json(self, system, user, max_tokens=200):
        return json.loads(self._call(system, user, max_tokens, True))

    def complete_text(self, system, user, max_tokens=120):
        return self._call(system, user, max_tokens, False).strip()
