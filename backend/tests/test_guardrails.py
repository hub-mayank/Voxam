import subprocess
import sys
from pathlib import Path
import pytest
from app.llm.budget import CallCapExceeded, count_call
from app.llm.gemini import GeminiLLM

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "check_secrets.py"


def run_scan(*files):
    return subprocess.run([sys.executable, str(SCRIPT), *map(str, files)], capture_output=True, text=True)


def test_cap_raises_after_n_calls(monkeypatch):
    monkeypatch.setenv("LLM_DAILY_CALL_CAP", "3")
    assert [count_call() for _ in range(3)] == [1, 2, 3]
    with pytest.raises(CallCapExceeded):
        count_call()


def test_cap_default_is_30(monkeypatch):
    monkeypatch.delenv("LLM_DAILY_CALL_CAP", raising=False)
    for _ in range(30):
        count_call()
    with pytest.raises(CallCapExceeded):
        count_call()


def test_cap_persists_across_restarts(monkeypatch, tmp_path):
    monkeypatch.setenv("LLM_DAILY_CALL_CAP", "2")
    code = "from app.llm.budget import count_call; print(count_call())"
    # each call is a fresh process, so only the file can carry the count
    runs = [subprocess.run([sys.executable, "-c", code], cwd=ROOT / "backend", capture_output=True, text=True)
            for _ in range(3)]
    assert [r.stdout.strip() for r in runs[:2]] == ["1", "2"]
    assert runs[2].returncode != 0 and "cap reached" in runs[2].stderr


def test_cap_resets_next_day(monkeypatch, tmp_path):
    monkeypatch.setenv("LLM_DAILY_CALL_CAP", "1")
    (tmp_path / "budget.json").write_text('{"date": "2000-01-01", "count": 99}')
    assert count_call() == 1


def test_corrupt_counter_fails_closed(tmp_path):
    (tmp_path / "budget.json").write_text("{nope")
    with pytest.raises(RuntimeError, match="corrupt"):
        count_call()


def test_gemini_adapter_stops_at_cap(monkeypatch):
    monkeypatch.setenv("LLM_DAILY_CALL_CAP", "2")
    calls = []

    class Reply:
        def raise_for_status(self): pass
        def json(self): return {"candidates": [{"content": {"parts": [{"text": "hi"}]}}]}

    monkeypatch.setattr("app.llm.gemini.httpx.post", lambda *a, **kw: calls.append(1) or Reply())
    llm = GeminiLLM(model="fake-model", api_key="fake-key")
    llm.complete_text("s", "u")
    llm.complete_text("s", "u")
    with pytest.raises(CallCapExceeded):
        llm.complete_text("s", "u")
    assert len(calls) == 2


def test_secrets_script_flags_fake_key(tmp_path):
    fake = "AIza" + "x" * 35
    bad = tmp_path / "config.txt"
    bad.write_text(f"line one\nGEMINI_API_KEY={fake}\n")
    out = run_scan(bad)
    assert out.returncode == 1
    assert "config.txt:2" in out.stdout
    assert fake not in out.stdout + out.stderr


def test_secrets_script_passes_clean_file(tmp_path):
    ok = tmp_path / "ok.txt"
    ok.write_text("key = os.environ.get('GEMINI_API_KEY')\n")
    assert run_scan(ok).returncode == 0


def test_secrets_script_clean_on_repo():
    assert run_scan().returncode == 0


@pytest.mark.live
def test_live_gemini_roundtrip():
    # one real call; counts against the daily cap
    out = GeminiLLM().complete_text("Reply with one word.", "Say hello.", max_tokens=10)
    assert out
