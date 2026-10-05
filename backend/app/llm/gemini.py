"""Gemini adapter (REST). UNTESTED: needs GEMINI_API_KEY and a verified model name."""
import json
import os
import httpx


class GeminiLLM:
    def __init__(self, model=None, api_key=None, timeout=10.0):
        self.model = model or os.environ.get("GEMINI_MODEL")
        self.key = api_key or os.environ.get("GEMINI_API_KEY")
        if not self.model or not self.key:
            raise RuntimeError("Set GEMINI_MODEL and GEMINI_API_KEY (never commit keys)")
        self.name = f"gemini:{self.model}"
        self.timeout = timeout

    def _call(self, system, user, max_tokens, json_mode):
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent"
        gen = {"temperature": 0, "maxOutputTokens": max_tokens}
        if json_mode:
            gen["responseMimeType"] = "application/json"
        body = {"systemInstruction": {"parts": [{"text": system}]},
                "contents": [{"role": "user", "parts": [{"text": user}]}],
                "generationConfig": gen}
        r = httpx.post(url, json=body, headers={"x-goog-api-key": self.key}, timeout=self.timeout)
        r.raise_for_status()
        return r.json()["candidates"][0]["content"]["parts"][0]["text"]

    def complete_json(self, system, user, max_tokens=200):
        return json.loads(self._call(system, user, max_tokens, True))

    def complete_text(self, system, user, max_tokens=120):
        return self._call(system, user, max_tokens, False).strip()
