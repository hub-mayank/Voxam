"""Ollama adapter for free local dev (no key, not counted against the call cap).
Needs a running server and OLLAMA_MODEL (e.g. llama3.2). OLLAMA_HOST defaults to http://localhost:11434."""
import json
import os
import httpx
from .base import Reply
from .errors import ProviderError, from_httpx


class OllamaLLM:
    provider = "ollama"
    mode = "live"  # a real model, just run locally

    def __init__(self, model=None, host=None, timeout=120.0):
        self.model = model or os.environ.get("OLLAMA_MODEL")
        if not self.model:
            raise RuntimeError("Set OLLAMA_MODEL (ollama list shows what is pulled)")
        self.host = (host or os.environ.get("OLLAMA_HOST") or "http://localhost:11434").rstrip("/")
        self.name = f"ollama:{self.model}"
        self.timeout = timeout

    def generate(self, system, user, max_tokens, json_mode):
        body = {"model": self.model, "stream": False,
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
                "options": {"temperature": 0, "num_predict": max_tokens}}
        if json_mode:
            body["format"] = "json"
        try:
            r = httpx.post(f"{self.host}/api/chat", json=body, timeout=self.timeout)
            r.raise_for_status()
            data = r.json()
        except httpx.HTTPError as e:
            raise from_httpx(e) from e
        except ValueError as e:
            raise ProviderError("malformed response (not JSON)") from e
        text = (data.get("message") or {}).get("content") or ""
        if not text.strip():
            raise ProviderError(f"empty response, done_reason={data.get('done_reason')}")
        return Reply(text, data.get("prompt_eval_count"), data.get("eval_count"))

    def generate_stream(self, system, user, max_tokens, on_delta):
        """Like generate() (text only) but calls on_delta(piece) as the model produces text. Returns the full Reply at the end."""
        body = {"model": self.model, "stream": True,
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
                "options": {"temperature": 0, "num_predict": max_tokens}}
        text, tokens_in, tokens_out = "", None, None
        try:
            with httpx.stream("POST", f"{self.host}/api/chat", json=body, timeout=self.timeout) as r:
                r.raise_for_status()
                for line in r.iter_lines():
                    if not line:
                        continue
                    data = json.loads(line)
                    piece = (data.get("message") or {}).get("content") or ""
                    if piece:
                        text += piece
                        on_delta(piece)
                    if data.get("done"):
                        tokens_in, tokens_out = data.get("prompt_eval_count"), data.get("eval_count")
        except httpx.HTTPError as e:
            raise from_httpx(e) from e
        except ValueError as e:
            raise ProviderError("malformed streaming response") from e
        if not text.strip():
            raise ProviderError("empty response (stream)")
        return Reply(text, tokens_in, tokens_out)

    def available(self) -> bool:
        try:
            r = httpx.get(f"{self.host}/api/tags", timeout=2.0)
            r.raise_for_status()
            names = [m.get("name", "") for m in r.json().get("models", [])]
        except (httpx.HTTPError, ValueError):
            return False
        return any(n == self.model or n.split(":")[0] == self.model for n in names)
