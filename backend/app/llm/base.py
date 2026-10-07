from dataclasses import dataclass
from typing import Protocol


@dataclass
class Reply:
    text: str
    tokens_in: int | None = None
    tokens_out: int | None = None


class LLM(Protocol):
    """What the interviewer and scorer use. `kind` labels the call in telemetry."""
    name: str

    def complete_json(self, system: str, user: str, max_tokens: int = 200, kind: str = "classify") -> dict: ...
    def complete_text(self, system: str, user: str, max_tokens: int = 120, kind: str = "phrase") -> str: ...


class Provider(Protocol):
    """One raw attempt against one backend. Retry, fallback and telemetry live in ResilientLLM.
    Raises ProviderError on failure. `mode` is live (a real model) or stub (simulated)."""
    provider: str
    model: str
    mode: str
    name: str

    def generate(self, system: str, user: str, max_tokens: int, json_mode: bool) -> Reply: ...
