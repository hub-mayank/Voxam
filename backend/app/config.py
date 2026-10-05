import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Phase:
    name: str
    start: int
    end: int
    max_followups: int


@dataclass(frozen=True)
class VivaConfig:
    viva_id: str
    prompt_version: str
    hard_limit: int
    answer_cap: int
    phases: tuple
    rubric: dict


def load_config(path) -> VivaConfig:
    raw = json.loads(Path(path).read_text())
    phases = tuple(Phase(**p) for p in raw["phases"])
    if phases[0].start != 0:
        raise ValueError("first phase must start at 0")
    for a, b in zip(phases, phases[1:]):
        if a.end != b.start:
            raise ValueError(f"gap/overlap between {a.name} and {b.name}")
    if phases[-1].end != raw["hard_limit_seconds"]:
        raise ValueError("last phase must end at hard_limit_seconds")
    total = sum(d["weight"] for d in raw["rubric"]["dimensions"])
    if total != 100:
        raise ValueError(f"rubric weights sum to {total}, expected 100")
    return VivaConfig(raw["viva_id"], raw["prompt_version"], raw["hard_limit_seconds"],
                      raw["answer_cap_seconds"], phases, raw["rubric"])


def load_bank(path) -> list:
    bank = json.loads(Path(path).read_text())
    ids = [q["id"] for q in bank]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate question ids")
    n_c = sum(q["type"] == "concept" for q in bank)
    n_a = sum(q["type"] == "applied" for q in bank)
    if n_c < 7 or n_a < 3:
        import warnings
        warnings.warn(f"question bank small (concept={n_c}, applied={n_a}); aim for >=7 / >=3 or fallbacks kick in")
    return bank
