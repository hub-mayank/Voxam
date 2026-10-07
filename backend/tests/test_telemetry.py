import json
import pytest
from app import telemetry

GOOD = {"ts": "2026-10-07T09:30:00.123Z", "provider": "gemini", "model": "m", "mode": "live", "kind": "score",
        "latency_ms": 12.5, "tokens_in": 10, "tokens_out": None, "audio_seconds": None, "status": "ok", "retries": 0}


def test_good_record_is_valid():
    assert telemetry.validate_record(GOOD) == []


@pytest.mark.parametrize("change", [
    {"ts": "yesterday"}, {"kind": "chat"}, {"status": "boom"}, {"mode": "mock"}, {"latency_ms": -1},
    {"latency_ms": "5"}, {"retries": 1.5}, {"retries": True}, {"tokens_in": -3}, {"provider": ""},
    {"audio_seconds": "3s"}, {"extra": 1}])
def test_bad_records_are_rejected(change):
    assert telemetry.validate_record({**GOOD, **change})


def test_missing_field_is_rejected():
    rec = dict(GOOD)
    del rec["status"]
    assert telemetry.validate_record(rec) == ["missing field status"]


def test_log_call_writes_valid_jsonl(tmp_path):
    telemetry.log_call("deepgram", "nova", "live", "stt", 180.0, "ok", audio_seconds=4.2)
    telemetry.log_call("gemini", "m", "live", "phrase", 90, "timeout", retries=2)
    lines = (tmp_path / "telemetry.jsonl").read_text().splitlines()
    recs = [json.loads(l) for l in lines]
    assert len(recs) == 2 and all(telemetry.validate_record(r) == [] for r in recs)
    assert recs[0]["audio_seconds"] == 4.2 and recs[1]["retries"] == 2


def test_log_call_refuses_an_invalid_record(tmp_path):
    with pytest.raises(ValueError):
        telemetry.log_call("gemini", "m", "live", "chat", 1.0, "ok")
    assert not (tmp_path / "telemetry.jsonl").exists()


def test_unwritable_log_warns_instead_of_breaking_the_viva(monkeypatch, tmp_path):
    blocker = tmp_path / "file"
    blocker.write_text("x")
    monkeypatch.setenv("TELEMETRY_FILE", str(blocker / "t.jsonl"))
    with pytest.warns(UserWarning, match="telemetry not written"):
        telemetry.log_call("gemini", "m", "live", "phrase", 1.0, "ok")
