"""Free-tier limits registry: config/free_tier_limits.json -> Limits per (provider, model)."""
import json
import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_FILE = Path(__file__).resolve().parents[3] / "config" / "free_tier_limits.json"


@dataclass(frozen=True)
class Limits:
    provider: str
    model: str
    rpm: int | None = None
    rpd: int | None = None
    tpm: int | None = None
    tpd: int | None = None
    audio_seconds_per_hour: int | None = None
    audio_seconds_per_day: int | None = None
    source: str = ""
    retrieved: str = ""


def load_limits(path=None) -> dict:
    """-> {(provider, model): Limits}. Raises ValueError for an entry without source and retrieved, or for a duplicate."""
    path = Path(path or os.environ.get("FREE_TIER_LIMITS_FILE") or DEFAULT_FILE)
    out = {}
    for e in json.loads(path.read_text())["limits"]:
        if not e.get("source") or not e.get("retrieved"):
            raise ValueError(f"{path.name}: {e.get('provider')}/{e.get('model')} needs `source` and `retrieved`")
        key = (e["provider"], e["model"])
        if key in out:
            raise ValueError(f"{path.name}: duplicate entry for {key}")
        fields = {k: e[k] for k in Limits.__dataclass_fields__ if k in e}
        out[key] = Limits(**fields)
    return out
