"""Per-(provider, model) free-tier budgets (D18). All with a fake clock and sleep: no real waiting."""
import json
import subprocess
import sys
from pathlib import Path

import httpx
import pytest

from app.llm.base import Reply
from app.llm.budget import (CallCapExceeded, budget_path, count_call, estimate_tokens, model_cap, record_tokens, token_usage, tokens_used,
                            usage)
from app.llm.errors import ProviderError
from app.llm.openai_compat import OpenAICompatLLM
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
    clock.t += 1000  # the early calls are now older than 24 h
    assert call(clock) == 1


def test_a_short_burst_goes_straight_through_then_calls_wait_for_the_minute_window(clock):
    start = clock.t
    for _ in range(4):  # floor(0.9 x 5 requests/min) = 4
        call(clock)
    assert clock.slept == [], "the first four calls are not delayed"
    call(clock)
    assert clock.slept == [60.0] and clock.t - start == pytest.approx(60), "the fifth waits until the first has aged out of the minute"
    clock.t += 100
    call(clock)
    assert clock.slept == [60.0], "after a quiet period no wait is needed"


def test_a_wait_longer_than_the_limit_refuses_instead_of_blocking_the_caller(clock, monkeypatch):
    monkeypatch.setenv("FREE_TIER_MAX_WAIT_S", "5")
    for _ in range(4):
        call(clock)
    with pytest.raises(CallCapExceeded, match="requests/min needs a 60.0 s wait"):
        call(clock)
    assert clock.slept == [] and usage(clock)["p|m"] == 4, "a refused call is not counted and reserves nothing"
    clock.t += 60
    assert call(clock) == 5


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
    for m in ("gemini-3.5-flash", "gemini-3.8-flash", "gemini-3.6-flash", "gemini-3.7-flash", "gemini-3-flash-preview"):
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
        assert "count_call(self.provider, self.model, est_tokens=reserved)" in (ROOT / "backend" / "app" / "llm" / name).read_text()
    assert "count_call" not in (ROOT / "backend" / "app" / "llm" / "ollama.py").read_text(), "local models are never counted"


def test_every_gemini_id_in_the_registry_was_seen_in_the_models_list():
    """IDs confirmed with the one list_models call (2026-10-08). A typo here would silently give a model the unlisted default."""
    confirmed = {"gemini-3.5-flash", "gemini-3.8-flash", "gemini-3.6-flash", "gemini-3.7-flash", "gemini-3-flash-preview", "gemini-3.5-flash-lite",
                 "gemini-3.1-flash-lite", "gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-3.8-flash-tts", "gemini-3.8-flash-lite-tts",
                 "gemini-3.1-flash-tts-preview", "gemini-2.5-flash-preview-tts", "gemini-3.5-transcribe"}
    assert {m for (p, m) in load_limits() if p == "gemini"} == confirmed


# ---------- tokens per minute and per day ----------

TOKEN_LIMITS = {("p", "t"): Limits("p", "t", rpm=None, rpd=1000, tpm=1000, tpd=5000, source="test", retrieved="2026-10-08")}


def tcall(clock, est, model="t"):
    return count_call("p", model, est_tokens=est, clock=clock, sleep=clock.sleep, limits=TOKEN_LIMITS)


def test_tokens_per_day_refuse_at_the_margin_and_roll_off_after_24_hours(clock):
    for _ in range(5):  # floor(0.9 x 5000) = 4500 tokens a day
        tcall(clock, 900)
        clock.t += 61  # keep the minute window clear
    with pytest.raises(CallCapExceeded, match="token budget used"):
        tcall(clock, 10)
    assert token_usage(clock)["p|t"]["tpd"] == 4500
    clock.t += 24 * 3600
    assert tcall(clock, 900) == 1  # old calls rolled off


def test_tokens_per_minute_wait_for_the_window_instead_of_refusing(clock):
    tcall(clock, 500)
    clock.t += 10
    tcall(clock, 400)  # 900 = floor(0.9 x 1000): the minute is full
    t0 = clock.t
    tcall(clock, 300)  # needs the first call (500 tokens, 10 s old) to leave the window
    assert clock.slept[-1] == pytest.approx(50.0, abs=0.01) and clock.t == pytest.approx(t0 + 50.0, abs=0.01)


def test_a_token_wait_longer_than_the_limit_refuses_and_leaves_no_trace(clock, monkeypatch):
    monkeypatch.setenv("FREE_TIER_MAX_WAIT_S", "5")
    tcall(clock, 900)
    with pytest.raises(CallCapExceeded, match="tokens/min needs a"):
        tcall(clock, 300)
    assert usage(clock)["p|t"] == 1 and token_usage(clock)["p|t"]["tpd"] == 900


def test_a_call_that_can_never_fit_a_minute_is_refused(clock):
    with pytest.raises(CallCapExceeded, match="can never fit"):
        tcall(clock, 901)


def test_record_tokens_swaps_the_reservation_for_the_real_use(clock):
    tcall(clock, 900)
    record_tokens("p", "t", 900, 120, clock=clock, limits=TOKEN_LIMITS)
    assert token_usage(clock)["p|t"] == {"tpm": 120, "tpd": 120}
    record_tokens("p", "t", 120, 0, clock=clock, limits=TOKEN_LIMITS)  # a failed attempt releases it
    assert token_usage(clock)["p|t"]["tpd"] == 0


def test_models_without_token_limits_track_nothing(clock):
    count_call("p", "other", est_tokens=10_000, clock=clock, sleep=clock.sleep, limits=TOKEN_LIMITS)
    record_tokens("p", "other", 10_000, 5, clock=clock, limits=TOKEN_LIMITS)
    assert token_usage(clock) == {}


def test_tokens_used_prefers_the_provider_numbers_and_falls_back_to_chars_over_4():
    assert tokens_used(Reply("hello", 11, 5), "s" * 400, "u" * 400) == 16
    assert tokens_used(Reply("r" * 40, None, None), "s" * 40, "u" * 40) == 30
    assert tokens_used(Reply("r" * 40, 11, None), "s" * 40, "u" * 40) == 30  # half a number is no number
    assert estimate_tokens("abcde") == 2


def groq(monkeypatch, body):
    monkeypatch.setenv("GROQ_API_KEY", "k")
    monkeypatch.setenv("LLM_DAILY_CALL_CAP", "1000")
    monkeypatch.setattr("app.llm.openai_compat.httpx.post", lambda *a, **k: httpx.Response(200, json=body, request=httpx.Request("POST", "https://x.test")))
    return OpenAICompatLLM("groq", model="openai/gpt-oss-20b")


def test_the_adapter_books_the_providers_token_counts(monkeypatch):
    body = {"choices": [{"message": {"content": "{}"}, "finish_reason": "stop"}], "usage": {"prompt_tokens": 300, "completion_tokens": 40}}
    groq(monkeypatch, body).generate("s", "u", 50, True)
    assert token_usage()["groq|openai/gpt-oss-20b"]["tpd"] == 340  # not the reservation (about 1000 headroom + 50)


def test_the_adapter_estimates_when_the_provider_sends_no_usage(monkeypatch):
    body = {"choices": [{"message": {"content": "r" * 80}, "finish_reason": "stop"}]}
    groq(monkeypatch, body).generate("s" * 400, "u" * 400, 50, False)
    assert token_usage()["groq|openai/gpt-oss-20b"]["tpd"] == 200 + 20  # chars / 4 of prompt (800) and reply (80)


def test_a_failed_attempt_counts_the_request_but_releases_the_tokens(monkeypatch):
    llm = groq(monkeypatch, {})
    monkeypatch.setattr("app.llm.openai_compat.httpx.post", lambda *a, **k: (_ for _ in ()).throw(httpx.ConnectError("refused")))
    with pytest.raises(ProviderError):
        llm.generate("s", "u", 50, False)
    assert usage()["groq|openai/gpt-oss-20b"] == 1 and token_usage()["groq|openai/gpt-oss-20b"]["tpd"] == 0
