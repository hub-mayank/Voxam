from typing import Protocol


class LLM(Protocol):
    name: str

    def complete_json(self, system: str, user: str) -> dict: ...
    def complete_text(self, system: str, user: str, max_tokens: int = 120) -> str: ...
