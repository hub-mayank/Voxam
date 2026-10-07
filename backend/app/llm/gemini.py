"""Gemini adapter (REST), one attempt per generate(). Needs GEMINI_API_KEY + GEMINI_MODEL (pick from `python -m app.list_models`).
Thinking-capable models can spend the output budget on reasoning and return truncated/empty text,
so we add headroom (GEMINI_TOKEN_HEADROOM, default 1500) and fail loudly on empty output."""
import os
import httpx
from .base import Reply
from .budget import count_call
from .errors import ProviderError, from_httpx


class GeminiLLM:
    provider = "gemini"
    mode = "live"

    def __init__(self, model=None, api_key=None, timeout=60.0):
        self.model = model or os.environ.get("GEMINI_MODEL")
        self.key = api_key or os.environ.get("GEMINI_API_KEY")
        if not self.model or not self.key:
            raise RuntimeError("Set GEMINI_MODEL and GEMINI_API_KEY (never commit keys)")
        self.name = f"gemini:{self.model}"
        self.timeout = timeout
        self.headroom = int(os.environ.get("GEMINI_TOKEN_HEADROOM", "1500"))

    def generate(self, system, user, max_tokens, json_mode):
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent"
        gen = {"temperature": 0, "maxOutputTokens": max_tokens + self.headroom}
        if json_mode:
            gen["responseMimeType"] = "application/json"
        body = {"systemInstruction": {"parts": [{"text": system}]},
                "contents": [{"role": "user", "parts": [{"text": user}]}],
                "generationConfig": gen}
        count_call()
        try:
            r = httpx.post(url, json=body, headers={"x-goog-api-key": self.key}, timeout=self.timeout)
            r.raise_for_status()
            data = r.json()
        except httpx.HTTPError as e:
            raise from_httpx(e) from e
        except ValueError as e:
            raise ProviderError("malformed response (not JSON)") from e
        cands = data.get("candidates") or []
        if not cands:
            raise ProviderError(f"no candidates, promptFeedback={data.get('promptFeedback')}")
        parts = cands[0].get("content", {}).get("parts") or []
        text = "".join(p.get("text", "") for p in parts if not p.get("thought"))
        if not text.strip():
            raise ProviderError(f"empty response, finishReason={cands[0].get('finishReason')}")
        use = data.get("usageMetadata") or {}
        out = [use.get("candidatesTokenCount"), use.get("thoughtsTokenCount")]  # thinking tokens are billed as output
        tokens_out = sum(t for t in out if t is not None) if any(t is not None for t in out) else None
        return Reply(text, use.get("promptTokenCount"), tokens_out)
