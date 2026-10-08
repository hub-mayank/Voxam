"""Per-(provider, model) free-tier budgets (D18). All with a fake clock and sleep: no real waiting."""
import json
import subprocess
import sys
from pathlib import Path

import pytest

from app.llm.budget import CallCapExceeded, budget_path, count_call, model_cap, usage
from app.llm.limits import Limits, load_limits

ROOT = Path(__file__).resolve().parents[2]
LIMITS = {("p", "m"): Limits("p", "m", rpm=5, rpd=10, source="test", retrieved="2026-10-08"),
          ("p", "bulk"): Limits("p", "bulk", rpm=None, rpd=100, source="test", retrieved="2026-10-08")}


class Clock:
    def __init__(self):
        self.t, self.slept = 1_000_000.0, []

    def __call__(self):
        return self.t

    def sleep(self, s):
        self.slept.append(round(s, 3))
        self.t += s


@pytest.fixture()
def clock(monkeypatch):
    monkeypatch.setenv("LLM_DAILY_CALL_CAP", "1000")  # high global ceiling unless a test lowers it
    monkeypatch.setenv("FREE_TIER_MAX_WAIT_S", "1000")
    return Clock()


def call(clock, provider="p", model="m"):
    return count_call(provider, model, clock=clock, sleep=clock.sleep, limits=LIMITS)


def test_the_daily_cap_is_90_percent_of_rpd_by_default_and_follows_the_margin(clock, monkeypatch):
    assert model_cap(LIMITS, "p", "m") == 9 and model_cap(LIMITS, "p", "bulk") == 90
    monkeypatch.setenv("FREE_TIER_MARGIN", "0.5")
    assert model_cap(LIMITS, "p", "m") == 5
    monkeypatch.setenv("FREE_TIER_MARGIN", "1.0")
    assert model_cap(LIMITS, "p", "m") == 10


def test_a_model_is_refused_at_its_own_cap_and_others_are_not(clock):
    assert [call(clock, model="bulk") for _ in range(12)][-1] == 12
    for n in range(1, 10):
        assert call(clock) == n
    with pytest.raises(CallCapExceeded, match=r"p\|m: free-tier budget used \(9/9"):
        call(clock)
    assert call(clock, model="bulk") == 13, "another model of the same provider still has budget"


def test_models_missing_from_the_file_get_the_global_ceiling_as_their_cap(clock, monkeypatch):
    monkeypatch.setenv("LLM_DAILY_CALL_CAP", "3")
    assert model_cap(LIMITS, "other", "unlisted") == 3
    for _ in range(3):
        call(clock, "other", "unlisted")
    with pytest.raises(CallCapExceeded):
        call(clock, "other", "unlisted")


def test_the_global_ceiling_spans_every_counted_model(clock, monkeypatch):
    monkeypatch.setenv("LLM_DAILY_CALL_CAP", "4")
    call(clock, model="bulk"), call(clock, model="bulk"), call(clock, "other", "x"), call(clock, "other", "y")
    with pytest.raises(CallCapExceeded, match="global call ceiling"):
        call(clock, model="bulk")


def test_the_window_rolls_so_old_calls_stop_counting_after_24_hours(clock):
    for _ in range(9):
        call(clock)
    clock.t += 24 * 3600 - 200
    with pytest.raises(CallCapExceeded):
        call(clock)
    clock.t += 1000  # the nine early calls (spaced 12 s apart) are now older than 24 h
    assert call(clock) == 1


def test_calls_are_spaced_to_stay_under_the_per_minute_limit(clock):
    start = clock.t
    call(clock)
    assert clock.slept == [], "the first call goes straight through"
    call(clock), call(clock), call(clock)
    assert clock.slept == [12.0, 12.0, 12.0], "5 requests/min = one slot every 12 s"
    assert clock.t - start == pytest.approx(36)
    clock.t += 100
    call(clock)
    assert clock.slept == [12.0, 12.0, 12.0], "after a quiet period no wait is needed"


def test_a_wait_longer_than_the_limit_refuses_instead_of_blocking_the_caller(clock, monkeypatch):
    monkeypatch.setenv("FREE_TIER_MAX_WAIT_S", "5")
    call(clock)
    with pytest.raises(CallCapExceeded, match="requests/min needs a"):
        call(clock)
    assert clock.slept == [] and usage(clock)["p|m"] == 1, "a refused call is not counted and reserves nothing"
    clock.t += 12
    assert call(clock) == 2


def test_usage_is_read_only_and_counts_the_last_24_hours(clock):
    assert usage(clock) == {}
    call(clock), call(clock, model="bulk")
    assert usage(clock) == {"p|m": 1, "p|bulk": 1}
    clock.t += 25 * 3600
    assert usage(clock) == {}


def test_an_old_format_counter_file_is_ignored_not_trusted(clock):
    budget_path().parent.mkdir(parents=True, exist_ok=True)
    budget_path().write_text('{"date": "2026-10-01", "count": 99}')
    assert call(clock) == 1


def test_four_processes_racing_never_exceed_the_ceiling(tmp_path, monkeypatch):
    """Real OS processes sharing the file: exactly the ceiling's worth of calls succeed, none more."""
    monkeypatch.setenv("LLM_DAILY_CALL_CAP", "25")
    code = ("from app.llm.budget import count_call, CallCapExceeded\n"
            "ok = 0\n"
            "for _ in range(15):\n"
            "    try:\n        count_call('race', 'model'); ok += 1\n    except CallCapExceeded:\n        pass\n"
            "print(ok)")
    procs = [subprocess.Popen([sys.executable, "-c", code], cwd=ROOT / "backend", stdout=subprocess.PIPE, text=True) for _ in range(4)]
    done = sum(int(p.communicate()[0].strip()) for p in procs)
    assert done == 25
    assert usage()["race|model"] == 25


# ---------- the registry file ----------

def test_the_committed_limits_file_has_the_values_from_the_consoles():
    lim = load_limits()
    g = lambda m: lim[("gemini", m)]  # noqa: E731
    for m in ("gemini-3.5-flash", "gemini-3.8-flash", "gemini-3.6-flash", "gemini-3.7-flash", "gemini-3-flash"):
        assert (g(m).rpm, g(m).rpd, g(m).tpm) == (5, 20, 250_000), m
    for m in ("gemini-3.5-flash-lite", "gemini-3.1-flash-lite"):
        assert (g(m).rpm, g(m).rpd, g(m).tpm) == (15, 500, 250_000), m
    assert (g("gemini-2.5-flash").rpm, g("gemini-2.5-flash").rpd) == (5, 20)
    assert (g("gemini-2.5-flash-lite").rpm, g("gemini-2.5-flash-lite").rpd) == (10, 20)
    tts = [v for (p, m), v in lim.items() if p == "gemini" and "tts" in m]
    assert len(tts) == 4 and all((v.rpm, v.rpd) == (3, 10) for v in tts)
    assert (g("gemini-3.5-transcribe").rpm, g("gemini-3.5-transcribe").rpd) == (3, 25)
    for m in ("openai/gpt-oss-120b", "openai/gpt-oss-20b", "qwen/qwen3.8-27b"):
        v = lim[("groq", m)]
        assert (v.rpm, v.rpd, v.tpm, v.tpd) == (30, 1000, 8000, 200_000), m
    for m in ("whisper-large-v3", "whisper-large-v3-turbo"):
        v = lim[("groq", m)]
        assert (v.rpm, v.rpd, v.audio_seconds_per_hour, v.audio_seconds_per_day) == (20, 2000, 7200, 28800), m
    assert all(v.source and v.retrieved == "2026-10-08" for v in lim.values())


def test_limits_entries_need_a_source_and_a_date_and_no_duplicates(tmp_path):
    f = tmp_path / "l.json"
    f.write_text(json.dumps({"limits": [{"provider": "p", "model": "m", "rpd": 1}]}))
    with pytest.raises(ValueError, match="source"):
        load_limits(f)
    ok = {"provider": "p", "model": "m", "rpd": 1, "source": "s", "retrieved": "2026-10-08"}
    f.write_text(json.dumps({"limits": [ok, ok]}))
    with pytest.raises(ValueError, match="duplicate"):
        load_limits(f)


def test_every_counted_adapter_passes_its_provider_and_model():
    for name in ("gemini.py", "openai_compat.py"):
        assert "count_call(self.provider, self.model)" in (ROOT / "backend" / "app" / "llm" / name).read_text()
    assert "count_call" not in (ROOT / "backend" / "app" / "llm" / "ollama.py").read_text(), "local models are never counted"
