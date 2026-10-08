import json
import httpx
import pytest
from app import telemetry
from app.llm.base import Reply
from app.llm.budget import CallCapExceeded, budget_path
from app.llm.errors import AllProvidersFailed
from app.llm.factory import make_llm
from app.llm.fake import FakeProvider
from app.llm.gemini import GeminiLLM
from app.llm.mock import MockLLM
from app.llm.ollama import OllamaLLM
from app.llm.resilient import ResilientLLM

REQ = httpx.Request("POST", "https://example.test")


def llm_for(*providers, **kw):
    sleeps = []
    kw = {"jitter": 0, "sleep": sleeps.append, **kw}
    return ResilientLLM(providers, **kw), sleeps


def records(tmp_path):
    return [json.loads(l) for l in (tmp_path / "telemetry.jsonl").read_text().splitlines()]


def test_429_storm_retries_then_falls_back(tmp_path):
    primary, backup = FakeProvider([429], model="primary"), FakeProvider(["ok"], model="backup", text="from backup")
    llm, sleeps = llm_for(primary, backup)
    assert llm.complete_text("s", "u") == "from backup"
    assert primary.calls == 3 and backup.calls == 1  # first try + 2 retries, then fallback
    assert sleeps == [0.5, 1.0]
    assert llm.name == "fake:backup"
    recs = records(tmp_path)
    assert [(r["model"], r["status"], r["retries"]) for r in recs] == [
        ("primary", "rate_limited", 0), ("primary", "rate_limited", 1), ("primary", "rate_limited", 2), ("backup", "ok", 0)]
    assert all(telemetry.validate_record(r) == [] for r in recs)


def test_recovers_after_a_retry_without_fallback(tmp_path):
    primary, backup = FakeProvider([503, "timeout", "ok"], model="primary"), FakeProvider(model="backup")
    llm, sleeps = llm_for(primary, backup)
    llm.complete_text("s", "u")
    assert primary.calls == 3 and backup.calls == 0 and llm.name == "fake:primary"
    assert [r["status"] for r in records(tmp_path)] == ["unavailable", "timeout", "ok"]


def test_non_retryable_error_falls_back_at_once():
    primary, backup = FakeProvider([404]), FakeProvider(["ok"])
    llm, sleeps = llm_for(primary, backup)
    llm.complete_text("s", "u")
    assert primary.calls == 1 and sleeps == []


def test_all_providers_failed_raises_with_last_status():
    llm, _ = llm_for(FakeProvider([429]), FakeProvider([503]))
    with pytest.raises(AllProvidersFailed) as e:
        llm.complete_text("s", "u")
    assert e.value.status == "unavailable" and e.value.retryable


def test_retry_after_raises_the_wait_and_max_delay_caps_it():
    llm, sleeps = llm_for(FakeProvider([429, "ok"], retry_after=5.0))
    llm.complete_text("s", "u")
    assert sleeps == [5.0]
    llm, sleeps = llm_for(FakeProvider([429, "ok"], retry_after=500.0), max_delay=8.0)
    llm.complete_text("s", "u")
    assert sleeps == [8.0]


def test_jitter_stays_within_bounds():
    llm, sleeps = llm_for(FakeProvider([429, 429, "ok"]), jitter=0.25)
    llm.complete_text("s", "u")
    assert 0.375 <= sleeps[0] <= 0.625 and 0.75 <= sleeps[1] <= 1.25


def test_bad_json_is_logged_not_retried(tmp_path):
    class Garbage(FakeProvider):
        def generate(self, system, user, max_tokens, json_mode):
            self.calls += 1
            return Reply("not json", 3, 2)

    p = Garbage()
    llm, _ = llm_for(p)
    with pytest.raises(json.JSONDecodeError):
        llm.complete_json("s", "u")
    assert p.calls == 1
    assert [(r["status"], r["tokens_in"]) for r in records(tmp_path)] == [("bad_output", 3)]


def test_kinds_and_tokens_are_logged(tmp_path):
    llm, _ = llm_for(FakeProvider())
    llm.complete_json("s", "two words", kind="score")
    llm.complete_text("s", "two words")
    recs = records(tmp_path)
    assert [r["kind"] for r in recs] == ["score", "phrase"]
    assert recs[0]["tokens_in"] == 2 and recs[0]["mode"] == "stub" and recs[0]["audio_seconds"] is None


def test_unknown_kind_is_rejected():
    llm, _ = llm_for(FakeProvider())
    with pytest.raises(ValueError):
        llm.complete_text("s", "u", kind="chat")


def gemini_429(monkeypatch):
    monkeypatch.setattr("app.llm.gemini.httpx.post", lambda *a, **k: httpx.Response(429, request=REQ))
    return GeminiLLM(model="m", api_key="k")


def test_cap_counts_every_attempt_including_retries(monkeypatch):
    monkeypatch.setenv("LLM_DAILY_CALL_CAP", "10")
    llm, _ = llm_for(gemini_429(monkeypatch))
    with pytest.raises(AllProvidersFailed):
        llm.complete_text("s", "u")
    assert len(json.loads(budget_path().read_text())["calls"]["gemini|m"]) == 3  # 1 try + 2 retries


def test_a_provider_out_of_budget_is_skipped_and_the_chain_moves_on(monkeypatch, tmp_path):
    monkeypatch.setenv("LLM_DAILY_CALL_CAP", "2")
    calls = []
    body = {"candidates": [{"content": {"parts": [{"text": "hi"}]}}]}
    monkeypatch.setattr("app.llm.gemini.httpx.post", lambda *a, **k: calls.append(1) or httpx.Response(200, json=body, request=REQ))
    backup = FakeProvider(text="from backup")
    llm, _ = llm_for(GeminiLLM(model="m", api_key="k"), backup)
    assert llm.complete_text("s", "u") == "hi" and llm.complete_text("s", "u") == "hi"
    assert llm.complete_text("s", "u") == "from backup", "third call: the budget is used up, so the backup serves"
    assert len(calls) == 2 and backup.calls == 1 and llm.name == "fake:flaky"
    assert [r["status"] for r in records(tmp_path)][-2:] == ["cap_exceeded", "ok"]


def test_when_every_provider_is_out_of_budget_the_cap_error_surfaces(monkeypatch):
    monkeypatch.setenv("LLM_DAILY_CALL_CAP", "1")
    body = {"candidates": [{"content": {"parts": [{"text": "hi"}]}}]}
    monkeypatch.setattr("app.llm.gemini.httpx.post", lambda *a, **k: httpx.Response(200, json=body, request=REQ))
    llm, _ = llm_for(GeminiLLM(model="m", api_key="k"))
    llm.complete_text("s", "u")
    with pytest.raises(CallCapExceeded):
        llm.complete_text("s", "u")


def test_mock_stub_and_local_providers_are_not_counted(monkeypatch):
    monkeypatch.setenv("LLM_DAILY_CALL_CAP", "1")
    body = {"message": {"content": "hi"}}
    monkeypatch.setattr("app.llm.ollama.httpx.post", lambda *a, **k: httpx.Response(200, json=body, request=REQ))
    llm, _ = llm_for(OllamaLLM(model="m"), FakeProvider())
    for _ in range(5):
        llm.complete_text("s", "u")
        FakeProvider().generate("s", "u", 5, False)
        MockLLM().complete_json("s", "ANSWER: x")
    assert not budget_path().exists()


def test_factory(monkeypatch):
    assert isinstance(make_llm("mock"), MockLLM)
    monkeypatch.delenv("LLM_CHAIN", raising=False)
    assert isinstance(make_llm(), MockLLM)
    monkeypatch.setenv("OLLAMA_MODEL", "m")
    monkeypatch.setenv("GEMINI_MODEL", "g")
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    llm = make_llm("gemini,ollama")
    assert [p.name for p in llm.providers] == ["gemini:g", "ollama:m"]
    with pytest.raises(SystemExit):
        make_llm("gpt")


def test_scorer_does_not_retry_provider_failures():
    from app.config import load_config
    from app.scorer import ScoreError, score_session
    from pathlib import Path
    cfg = load_config(Path(__file__).resolve().parents[2] / "config/viva.config.json")
    events = [json.loads(l) for l in open(Path(__file__).parent / "personas" / "strong.jsonl")]
    p = FakeProvider([503])
    llm, _ = llm_for(p, retries=1)
    with pytest.raises(ScoreError, match="provider failed"):
        score_session(llm, cfg, events, runs=3)
    assert p.calls == 2  # llm layer retried once; the scorer did not add 3 more rounds
