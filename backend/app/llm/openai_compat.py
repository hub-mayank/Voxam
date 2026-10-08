"""OpenAI-compatible chat adapter: Groq, Cerebras, OpenRouter, Azure AI Foundry-style endpoints, or any server that answers
POST {base_url}/chat/completions. One attempt per generate(); httpx only. Every attempt is counted against the (provider, model)
free-tier budget (budget.py).

Configuration comes from the environment, prefix = the provider name upper-cased (groq -> GROQ_*):
  {P}_API_KEY            required (never commit)
  {P}_BASE_URL           required unless the provider is one of KNOWN_BASE_URLS
  {P}_MODEL              default model when the spec has none
  {P}_AUTH               bearer (default) -> `Authorization: Bearer <key>`, or api-key -> `api-key: <key>` (Azure style)
  {P}_QUERY              extra query string, e.g. api-version=2024-10-21
  {P}_TOKEN_HEADROOM     extra output tokens on top of max_tokens (default 1000: reasoning models spend the budget thinking first)
  {P}_JSON_MODE          1 (default) sends response_format json_object when JSON is wanted; 0 for servers that reject it
  {P}_REASONING_EFFORT   optional (low|medium|high) for reasoning models such as gpt-oss
  {P}_MAX_TOKENS_FIELD   max_tokens (default) or max_completion_tokens"""
import os
import re
from urllib.parse import parse_qsl

import httpx

from .base import Reply
from .budget import count_call, estimate_tokens, record_tokens, tokens_used
from .errors import ProviderError, from_httpx

KNOWN_BASE_URLS = {
    "groq": "https://api.groq.com/openai/v1",
    "cerebras": "https://api.cerebras.ai/v1",
    "openrouter": "https://openrouter.ai/api/v1",
}


def env_prefix(provider: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", provider).upper()


def is_configured(provider: str, environ=None) -> bool:
    environ = os.environ if environ is None else environ
    return provider in KNOWN_BASE_URLS or bool(environ.get(f"{env_prefix(provider)}_BASE_URL"))


class OpenAICompatLLM:
    mode = "live"

    def __init__(self, provider, model=None, base_url=None, api_key=None, auth=None, query=None, timeout=60.0, environ=None):
        env = os.environ if environ is None else environ
        P = env_prefix(provider)
        self.provider = provider
        self.model = model or env.get(f"{P}_MODEL")
        self.base_url = (base_url or env.get(f"{P}_BASE_URL") or KNOWN_BASE_URLS.get(provider, "")).rstrip("/")
        self.key = api_key or env.get(f"{P}_API_KEY")
        if not self.model:
            raise RuntimeError(f"Set a model: `{provider}:<model>` or {P}_MODEL")
        if not self.base_url:
            raise RuntimeError(f"Set {P}_BASE_URL (OpenAI-compatible endpoint, e.g. https://host/v1)")
        if not self.key:
            raise RuntimeError(f"Set {P}_API_KEY (never commit keys)")
        self.auth = (auth or env.get(f"{P}_AUTH") or "bearer").lower()
        if self.auth not in ("bearer", "api-key"):
            raise RuntimeError(f"{P}_AUTH must be bearer or api-key, not {self.auth!r}")
        self.params = dict(query) if isinstance(query, dict) else dict(parse_qsl(query or env.get(f"{P}_QUERY", "")))
        self.headroom = int(env.get(f"{P}_TOKEN_HEADROOM", "1000"))
        self.json_mode = env.get(f"{P}_JSON_MODE", "1") not in ("0", "false", "no")
        self.effort = env.get(f"{P}_REASONING_EFFORT") or None
        self.tokens_field = env.get(f"{P}_MAX_TOKENS_FIELD", "max_tokens")
        self.name = f"{provider}:{self.model}"
        self.timeout = timeout

    def generate(self, system, user, max_tokens, json_mode):
        body = {"model": self.model, "temperature": 0, self.tokens_field: max_tokens + self.headroom,
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
        if json_mode and self.json_mode:
            body["response_format"] = {"type": "json_object"}
        if self.effort:
            body["reasoning_effort"] = self.effort
        headers = {"Authorization": f"Bearer {self.key}"} if self.auth == "bearer" else {"api-key": self.key}
        reserved = estimate_tokens(system, user) + max_tokens + self.headroom
        count_call(self.provider, self.model, est_tokens=reserved)
        try:
            r = httpx.post(f"{self.base_url}/chat/completions", json=body, headers=headers, params=self.params or None, timeout=self.timeout)
            r.raise_for_status()
            data = r.json()
        except httpx.HTTPError as e:
            record_tokens(self.provider, self.model, reserved, 0)  # no reply: nothing was used
            raise from_httpx(e) from e
        except ValueError as e:
            record_tokens(self.provider, self.model, reserved, 0)
            raise ProviderError("malformed response (not JSON)") from e
        use = data.get("usage") or {}
        choices = data.get("choices") or []
        if not choices:
            record_tokens(self.provider, self.model, reserved, tokens_used(Reply("", use.get("prompt_tokens"), use.get("completion_tokens")), system, user))
            raise ProviderError(f"no choices in response: {str(data.get('error'))[:200]}")
        content = (choices[0].get("message") or {}).get("content")
        if isinstance(content, list):  # some servers return content parts
            content = "".join(p.get("text", "") for p in content if isinstance(p, dict))
        reply = Reply(content or "", use.get("prompt_tokens"), use.get("completion_tokens"))
        record_tokens(self.provider, self.model, reserved, tokens_used(reply, system, user))
        if not reply.text.strip():
            raise ProviderError(f"empty response, finish_reason={choices[0].get('finish_reason')}")
        return reply
