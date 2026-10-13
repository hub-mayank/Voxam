"""Call budgets for metered (free-tier or quota-limited) providers. Zero-spend policy D15/D18.

One usage file shared by every clone, worktree and process: ~/.cache/ai-viva/llm_budget.json (override: LLM_BUDGET_FILE). It holds, per
"provider|model", the timestamps of the calls made in the last 24 hours (a rolling window) (slots already reserved included).
Every ATTEMPT counts (a retry is a call). Mock, stub and local providers (Ollama) never call count_call().

count_call(provider, model) refuses, with CallCapExceeded, when
  * the model's own budget is used up: floor(FREE_TIER_MARGIN x rpd) calls in 24 h (default margin 0.9) for models listed in
    config/free_tier_limits.json; models not in the file get the global ceiling as their cap;
  * the global ceiling is reached: LLM_DAILY_CALL_CAP (default 30) calls in 24 h across ALL counted models;
  * the next call would have to wait longer than FREE_TIER_MAX_WAIT_S (default 5) to stay under the model's requests-per-minute limit;
  * tokens (models with tpm / tpd in the file): the call would push the last 24 h past floor(margin x tpd), or would need a wait longer
    than FREE_TIER_MAX_WAIT_S for the last 60 s to fit under floor(margin x tpm). The caller passes `est_tokens` (a reservation: prompt
    chars / 4 plus the largest reply it allows) and afterwards `record_tokens` swaps the reservation for what the call really used (the
    provider's usage numbers, else chars / 4 of prompt and reply). Both windows are rolling. A call that fails before any reply releases
    its reservation (the request still counts).
Otherwise it reserves the next slot (no more than floor(margin x rpm) calls in any 60 s, across processes: a burst of a few calls
is not delayed), sleeps until it, and returns
the model's call count. The fallback chain treats CallCapExceeded as "this provider is out for now" and moves to the next one."""
import fcntl
import json
import math
import os
import time
from pathlib import Path

from .limits import load_limits

DEFAULT_CAP = 30
WINDOW_S = 24 * 3600
MINUTE_S = 60


class CallCapExceeded(RuntimeError):
    pass


def budget_path() -> Path:
    return Path(os.environ.get("LLM_BUDGET_FILE") or Path.home() / ".cache" / "ai-viva" / "llm_budget.json")


def daily_cap() -> int:
    return int(os.environ.get("LLM_DAILY_CALL_CAP", DEFAULT_CAP))


def margin() -> float:
    return float(os.environ.get("FREE_TIER_MARGIN", "0.9"))


def max_wait() -> float:
    return float(os.environ.get("FREE_TIER_MAX_WAIT_S", "5"))


def model_cap(limits, provider: str, model: str) -> int:
    """Calls allowed per 24 h for this model."""
    lim = limits.get((provider, model))
    if lim is not None and lim.rpd is not None:
        return math.floor(margin() * lim.rpd)
    return daily_cap()


def estimate_tokens(*texts) -> int:
    """Rough token count when the provider reports none: characters / 4."""
    return math.ceil(sum(len(t or "") for t in texts) / 4)


def token_cap(limits, provider: str, model: str, field: str):
    """floor(margin x tpm) or floor(margin x tpd) for this model, or None when the file has no such limit."""
    lim = limits.get((provider, model))
    value = getattr(lim, field, None) if lim is not None else None
    return None if value is None else math.floor(margin() * value)


def _tokens_in(entries, since) -> int:
    return sum(n for t, n in entries if t > since)


def _token_wait(entries, now: float, need: int, cap: int) -> float:
    """Seconds until `need` more tokens fit under `cap` in a 60 s window (0 if they fit now). Entries are (time, tokens)."""
    live = sorted((t, n) for t, n in entries if t > now - MINUTE_S)
    total = sum(n for _, n in live)
    for t, n in live:
        if total + need <= cap:
            break
        total -= n
        wait_until = t + MINUTE_S
        if total + need <= cap:
            return max(0.0, wait_until - now)
    return 0.0 if total + need <= cap else float("inf")


def _read(f, path):
    f.seek(0)
    raw = f.read()
    if not raw.strip():
        return {"calls": {}, "last": {}, "tokens": {}}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        raise RuntimeError(f"{path} is corrupt; fix or delete it (the budget fails closed)")
    if not isinstance(data, dict) or "calls" not in data:  # the old one-counter format: start fresh
        return {"calls": {}, "last": {}, "tokens": {}}
    data.setdefault("last", {})
    data.setdefault("tokens", {})
    return data


def count_call(provider: str = "unknown", model: str = "unknown", *, est_tokens: int = 0, clock=time.time, sleep=time.sleep, limits=None) -> int:
    """Count one provider attempt, or raise CallCapExceeded. See the module docstring."""
    key = f"{provider}|{model}"
    limits = load_limits() if limits is None else limits
    lim = limits.get((provider, model))
    now = clock()
    path = budget_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a+") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        data = _read(f, path)
        calls = {k: [t for t in v if t > now - WINDOW_S] for k, v in data["calls"].items()}
        tokens = {k: [e for e in v if e[0] > now - WINDOW_S] for k, v in data["tokens"].items()}
        total, used = sum(len(v) for v in calls.values()), len(calls.get(key, []))
        ceiling, cap = daily_cap(), model_cap(limits, provider, model)
        if total >= ceiling:
            raise CallCapExceeded(f"global call ceiling reached ({total}/{ceiling} in 24 h); raise LLM_DAILY_CALL_CAP only with Mayank's ok")
        if used >= cap:
            raise CallCapExceeded(f"{key}: free-tier budget used ({used}/{cap} in 24 h"
                                  + (f"; rpd {lim.rpd} x margin {margin()}" if lim and lim.rpd is not None else "") + ")")
        mine = tokens.get(key, [])
        tpd, tpm = token_cap(limits, provider, model, "tpd"), token_cap(limits, provider, model, "tpm")
        if tpd is not None and _tokens_in(mine, now - WINDOW_S) + est_tokens > tpd:
            raise CallCapExceeded(f"{key}: free-tier token budget used ({_tokens_in(mine, now - WINDOW_S)} + {est_tokens} > {tpd} tokens in 24 h"
                                  f"; tpd {lim.tpd} x margin {margin()})")
        token_slot = now
        if tpm is not None:
            wait = _token_wait(mine, now, est_tokens, tpm)
            if wait == float("inf"):
                raise CallCapExceeded(f"{key}: a call of about {est_tokens} tokens can never fit under {tpm} tokens/min (tpm {lim.tpm} x margin {margin()})")
            token_slot = now + wait
        slot, why = max(now, token_slot), f"{tpm} tokens/min"
        if lim is not None and lim.rpm:
            # at most floor(margin x rpm) calls in any 60 s: a short burst (classify then phrase) goes straight through,
            # the next call waits until the oldest call in the minute has aged out
            per_minute = max(1, math.floor(margin() * lim.rpm))
            recent = sorted(t for t in calls.get(key, []) if t > slot - MINUTE_S)
            if len(recent) >= per_minute and recent[-per_minute] + MINUTE_S > slot:
                slot, why = recent[-per_minute] + MINUTE_S, f"{lim.rpm} requests/min"
        if slot - now > max_wait():
            raise CallCapExceeded(f"{key}: staying under {why} needs a {slot - now:.1f} s wait (limit {max_wait():.0f} s)")
        calls.setdefault(key, []).append(slot)
        if est_tokens and (tpd is not None or tpm is not None):
            tokens.setdefault(key, []).append([slot, est_tokens])
        data["calls"], data["tokens"] = calls, tokens
        f.seek(0)
        f.truncate()
        json.dump(data, f)
    if slot > now:
        sleep(slot - now)
    return used + 1


def record_tokens(provider: str, model: str, reserved: int, actual: int, *, clock=time.time, limits=None):
    """Swap a reservation for the real use: adds `actual - reserved` to the rolling token windows (pass actual=0 to release it).
    No-op for a model without token limits."""
    limits = load_limits() if limits is None else limits
    if reserved == actual or (token_cap(limits, provider, model, "tpd") is None and token_cap(limits, provider, model, "tpm") is None):
        return
    key, now = f"{provider}|{model}", clock()
    path = budget_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a+") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        data = _read(f, path)
        tokens = {k: [e for e in v if e[0] > now - WINDOW_S] for k, v in data["tokens"].items()}
        tokens.setdefault(key, []).append([now, actual - reserved])
        data["tokens"] = tokens
        f.seek(0)
        f.truncate()
        json.dump(data, f)


def tokens_used(reply, system: str, user: str) -> int:
    """What a finished call used: the provider's usage numbers when it sent both, else chars / 4 of prompt and reply."""
    if reply.tokens_in is not None and reply.tokens_out is not None:
        return reply.tokens_in + reply.tokens_out
    return estimate_tokens(system, user, reply.text)


def usage(clock=time.time) -> dict:
    """{"provider|model": calls in the last 24 h}, read-only. For reports."""
    path = budget_path()
    if not path.exists():
        return {}
    with open(path) as f:
        fcntl.flock(f, fcntl.LOCK_SH)
        data = _read(f, path)
    now = clock()
    return {k: len([t for t in v if t > now - WINDOW_S]) for k, v in data["calls"].items() if any(t > now - WINDOW_S for t in v)}


def token_usage(clock=time.time) -> dict:
    """{"provider|model": {"tpm": tokens in the last 60 s, "tpd": tokens in the last 24 h}}, read-only. For reports."""
    path = budget_path()
    if not path.exists():
        return {}
    with open(path) as f:
        fcntl.flock(f, fcntl.LOCK_SH)
        data = _read(f, path)
    now = clock()
    return {k: {"tpm": max(0, _tokens_in(v, now - MINUTE_S)), "tpd": max(0, _tokens_in(v, now - WINDOW_S))} for k, v in data["tokens"].items() if v}
