"""Every paid-quota-relevant call in T3b goes through here: it is counted against the free-tier budget (T1c registry: per provider and model,
rolling 24 h, paced per minute) and logged to telemetry, so the report's call counts come from files. Requires the T1c code (git merge main)."""
import os
import time

from common import DATA

os.environ.setdefault("TELEMETRY_FILE", str(DATA / "telemetry_t3b.jsonl"))
os.environ.setdefault("FREE_TIER_MAX_WAIT_S", "60")  # a benchmark may wait for its per-minute slot

from app import telemetry  # noqa: E402
from app.envfile import load_env  # noqa: E402
from app.llm.budget import CallCapExceeded, count_call  # noqa: E402

load_env()  # keys from the shell or the repo .env; never printed


def key(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise SystemExit(f"{name} is not set (shell or .env)")
    return value


def counted(provider: str, model: str, kind: str, fn, *, tokens=False):
    """Count one attempt, run fn() and log the outcome. -> (result, seconds). Re-raises the provider's error after logging it."""
    count_call(provider, model)  # may sleep for pacing, or raise CallCapExceeded
    t = time.perf_counter()
    try:
        result = fn()
    except Exception as e:
        telemetry.log_call(provider, model, "live", kind, (time.perf_counter() - t) * 1000, "error", 0, None, None)
        raise
    seconds = time.perf_counter() - t
    telemetry.log_call(provider, model, "live", kind, seconds * 1000, "ok", 0, None, None)
    return result, seconds
