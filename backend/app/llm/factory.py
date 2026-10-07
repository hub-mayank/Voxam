import os
from .mock import MockLLM
from .resilient import ResilientLLM


def make_llm(spec=None, model=None, retries=2):
    """spec: "mock", or providers in fallback order, e.g. "gemini" or "gemini,ollama".
    Defaults to LLM_CHAIN, then mock. `model` overrides the model of the first provider."""
    spec = spec or os.environ.get("LLM_CHAIN") or "mock"
    names = [n.strip() for n in spec.split(",") if n.strip()]
    if names == ["mock"]:
        return MockLLM()
    providers = []
    for i, n in enumerate(names):
        m = model if i == 0 else None
        if n == "gemini":
            from .gemini import GeminiLLM
            providers.append(GeminiLLM(model=m))
        elif n == "ollama":
            from .ollama import OllamaLLM
            providers.append(OllamaLLM(model=m))
        else:
            raise SystemExit(f"unknown llm {n!r}; use mock, gemini or ollama (comma list = fallback order)")
    return ResilientLLM(providers, retries=retries)
