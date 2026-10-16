"""One JSONL line per provider attempt (LLM now; STT/TTS use the same log_call).
File: ~/.cache/ai-viva/telemetry.jsonl (override: TELEMETRY_FILE). Fields (all required, null when n/a):
  ts          UTC ISO-8601, e.g. 2026-10-07T09:30:00.123Z
  provider    backend family, e.g. gemini
  model       model id
  mode        live (real model) | stub (simulated)
  kind        classify | phrase | score | generate | stt | tts
  latency_ms  one attempt, provider time only (excludes backoff sleeps)
  tokens_in, tokens_out   LLM tokens as reported by the provider; null if not reported
  audio_seconds           STT/TTS audio length; null for LLM calls
  status      ok | rate_limited | unavailable | timeout | error | bad_output | cap_exceeded
  retries     0 for the first try on a provider, 1 for the second, ..."""
import json
import os
import re
import warnings
from datetime import datetime, timezone
from pathlib import Path

KINDS = ("classify", "phrase", "score", "generate", "stt", "tts")
STATUSES = ("ok", "rate_limited", "unavailable", "timeout", "error", "bad_output", "cap_exceeded")
MODES = ("live", "stub")
TS_FORMAT = re.compile(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(\.\d+)?Z$")
FIELDS = ("ts", "provider", "model", "mode", "kind", "latency_ms", "tokens_in", "tokens_out",
          "audio_seconds", "status", "retries")


def telemetry_path() -> Path:
    return Path(os.environ.get("TELEMETRY_FILE") or Path.home() / ".cache" / "ai-viva" / "telemetry.jsonl")


def _is_int(v) -> bool:
    return type(v) is int and v >= 0


def _is_num(v) -> bool:
    return type(v) in (int, float) and v >= 0


def validate_record(rec: dict) -> list[str]:
    """Returns a list of problems; empty means valid. Unknown fields are a problem (closed schema)."""
    problems = [f"missing field {k}" for k in FIELDS if k not in rec]
    problems += [f"unknown field {k}" for k in rec if k not in FIELDS]
    if problems:
        return problems
    if not (isinstance(rec["ts"], str) and TS_FORMAT.match(rec["ts"])):
        problems.append("ts must be UTC ISO-8601 ending in Z")
    for k in ("provider", "model"):
        if not (isinstance(rec[k], str) and rec[k]):
            problems.append(f"{k} must be a non-empty string")
    for k, allowed in (("mode", MODES), ("kind", KINDS), ("status", STATUSES)):
        if rec[k] not in allowed:
            problems.append(f"{k} must be one of {allowed}")
    if not _is_num(rec["latency_ms"]):
        problems.append("latency_ms must be a number >= 0")
    if not _is_int(rec["retries"]):
        problems.append("retries must be an int >= 0")
    for k in ("tokens_in", "tokens_out"):
        if rec[k] is not None and not _is_int(rec[k]):
            problems.append(f"{k} must be null or an int >= 0")
    if rec["audio_seconds"] is not None and not _is_num(rec["audio_seconds"]):
        problems.append("audio_seconds must be null or a number >= 0")
    return problems


def log_call(provider: str, model: str, mode: str, kind: str, latency_ms: float, status: str,
             retries: int = 0, tokens_in: int | None = None, tokens_out: int | None = None,
             audio_seconds: float | None = None) -> dict:
    rec = {"ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
           "provider": provider, "model": model, "mode": mode, "kind": kind,
           "latency_ms": round(latency_ms, 1), "tokens_in": tokens_in, "tokens_out": tokens_out,
           "audio_seconds": audio_seconds, "status": status, "retries": retries}
    problems = validate_record(rec)
    if problems:
        raise ValueError(f"bad telemetry record: {problems}")
    try:
        path = telemetry_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a") as f:
            f.write(json.dumps(rec) + "\n")  # one write call per line
    except OSError as e:
        warnings.warn(f"telemetry not written: {e}")
    return rec
