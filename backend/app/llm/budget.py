"""Call budgets for metered (free-tier or quota-limited) providers. Zero-spend policy D15/D18.

One usage file shared by every clone, worktree and process: ~/.cache/ai-viva/llm_budget.json (override: LLM_BUDGET_FILE). It holds, per
"provider|model", the timestamps of the calls made in the last 24 hours (a rolling window) and the time of the last reserved slot.
Every ATTEMPT counts (a retry is a call). Mock, stub and local providers (Ollama) never call count_call().

count_call(provider, model) refuses, with CallCapExceeded, when
  * the model's own budget is used up: floor(FREE_TIER_MARGIN x rpd) calls in 24 h (default margin 0.9) for models listed in
    config/free_tier_limits.json; models not in the file get the global ceiling as their cap;
  * the global ceiling is reached: LLM_DAILY_CALL_CAP (default 30) calls in 24 h across ALL counted models;
  * the next call would have to wait longer than FREE_TIER_MAX_WAIT_S (default 5) to stay under the model's requests-per-minute limit.
Otherwise it reserves the next slot (at least 60/rpm seconds after the previous call, across processes), sleeps until it, and returns
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


def _read(f, path):
    f.seek(0)
    raw = f.read()
    if not raw.strip():
        return {"calls": {}, "last": {}}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        raise RuntimeError(f"{path} is corrupt; fix or delete it (the budget fails closed)")
    if not isinstance(data, dict) or "calls" not in data:  # the old one-counter format: start fresh
        return {"calls": {}, "last": {}}
    data.setdefault("last", {})
    return data


def count_call(provider: str = "unknown", model: str = "unknown", *, clock=time.time, sleep=time.sleep, limits=None) -> int:
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
        total, used = sum(len(v) for v in calls.values()), len(calls.get(key, []))
        ceiling, cap = daily_cap(), model_cap(limits, provider, model)
        if total >= ceiling:
            raise CallCapExceeded(f"global call ceiling reached ({total}/{ceiling} in 24 h); raise LLM_DAILY_CALL_CAP only with Mayank's ok")
        if used >= cap:
            raise CallCapExceeded(f"{key}: free-tier budget used ({used}/{cap} in 24 h"
                                  + (f"; rpd {lim.rpd} x margin {margin()}" if lim and lim.rpd is not None else "") + ")")
        slot = now
        if lim is not None and lim.rpm:
            slot = max(now, data["last"].get(key, 0) + 60.0 / lim.rpm)
            if slot - now > max_wait():
                raise CallCapExceeded(f"{key}: staying under {lim.rpm} requests/min needs a {slot - now:.1f} s wait (limit {max_wait():.0f} s)")
            data["last"][key] = slot
        calls.setdefault(key, []).append(slot)
        data["calls"] = calls
        f.seek(0)
        f.truncate()
        json.dump(data, f)
    if slot > now:
        sleep(slot - now)
    return used + 1


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
