import os
from .mock import MockLLM
from .openai_compat import KNOWN_BASE_URLS, is_configured
from .resilient import ResilientLLM

BUILTIN = ("gemini", "ollama")


def split_spec(entry: str):
    """"groq:openai/gpt-oss-20b" -> ("groq", "openai/gpt-oss-20b"); "gemini" -> ("gemini", None);
    "ollama:llama3.2:3b" -> ("ollama", "llama3.2:3b") (only the first colon separates the provider)."""
    name, _, model = entry.strip().partition(":")
    return name.strip(), (model.strip() or None)


def is_provider_name(token: str) -> bool:
    """True if `token` names a provider we can build (used to tell `groq:model` from a bare model name that contains a colon)."""
    return token in ("mock", "modelled", *BUILTIN, *KNOWN_BASE_URLS) or is_configured(token)


def make_llm(spec=None, model=None, retries=2):
    """spec: "mock", or providers in fallback order, each `provider` or `provider:model`:
    "gemini", "gemini,ollama", "groq:openai/gpt-oss-120b,gemini:gemini-3.5-flash-lite,ollama:llama3.2:3b".
    Providers: gemini, ollama, and anything OpenAI-compatible (groq, cerebras, openrouter, or a name with NAME_BASE_URL set).
    Defaults to LLM_CHAIN, then mock. `model` overrides the model of the first provider."""
    spec = spec or os.environ.get("LLM_CHAIN") or "mock"
    entries = [e for e in spec.split(",") if e.strip()]
    if [e.strip() for e in entries] == ["mock"]:
        return MockLLM()
    providers = []
    for i, entry in enumerate(entries):
        name, spec_model = split_spec(entry)
        m = model if (i == 0 and model) else spec_model
        if name == "modelled":  # load tests only: app/loadmodel.py
            from ..loadmodel import shared
            providers.append(shared("llm"))
        elif name == "gemini":
            from .gemini import GeminiLLM
            providers.append(GeminiLLM(model=m))
        elif name == "ollama":
            from .ollama import OllamaLLM
            providers.append(OllamaLLM(model=m))
        elif is_configured(name):
            from .openai_compat import OpenAICompatLLM
            providers.append(OpenAICompatLLM(name, model=m))
        else:
            raise SystemExit(f"unknown llm {name!r}; use mock, gemini, ollama, groq, cerebras, openrouter, or set {name.upper()}_BASE_URL "
                             "for another OpenAI-compatible endpoint (comma list = fallback order, `provider:model` picks the model)")
    return ResilientLLM(providers, retries=retries)
