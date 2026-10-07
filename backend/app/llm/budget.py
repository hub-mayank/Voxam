"""Daily call cap for metered (paid or quota-limited) providers. One counter shared by every
clone and worktree: ~/.cache/ai-viva/llm_budget.json (override: LLM_BUDGET_FILE).
Cap: LLM_DAILY_CALL_CAP, default 30. Counted per attempt: a retry is a call. Mock, stub and
local providers never call count_call()."""
import fcntl
import json
import os
from datetime import date
from pathlib import Path

DEFAULT_CAP = 30


class CallCapExceeded(RuntimeError):
    pass


def budget_path() -> Path:
    return Path(os.environ.get("LLM_BUDGET_FILE") or Path.home() / ".cache" / "ai-viva" / "llm_budget.json")


def daily_cap() -> int:
    return int(os.environ.get("LLM_DAILY_CALL_CAP", DEFAULT_CAP))


def count_call() -> int:
    """Count one provider call for today. Raises CallCapExceeded once the cap is used up."""
    cap = daily_cap()
    today = date.today().isoformat()
    path = budget_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a+") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        f.seek(0)
        raw = f.read()
        try:
            data = json.loads(raw) if raw.strip() else {}
        except json.JSONDecodeError:
            raise RuntimeError(f"{path} is corrupt; fix or delete it (the cap fails closed)")
        used = data.get("count", 0) if data.get("date") == today else 0
        if used >= cap:
            raise CallCapExceeded(f"daily live call cap reached ({used}/{cap}); raise LLM_DAILY_CALL_CAP only with Mayank's ok")
        f.seek(0)
        f.truncate()
        json.dump({"date": today, "count": used + 1}, f)
        return used + 1
