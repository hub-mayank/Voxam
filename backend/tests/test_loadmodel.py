"""The modelled providers used by the load harness: they must carry the measured curves and limits, and be shared by all sessions."""
import threading
import time

import pytest

from app import loadmodel
from app.llm.errors import ProviderError
from app.llm.factory import make_llm


def test_the_stt_curve_is_read_from_the_measured_file_and_interpolates():
    c = loadmodel.SttCurve("faster-whisper-base-int8")
    assert c.decode_s(1) == pytest.approx(0.931) and c.decode_s(8) == pytest.approx(2.274)
    assert c.decode_s(6) == pytest.approx((1.373 + 2.274) / 2)  # between the measured 4 and 8
    assert c.decode_s(16) > c.decode_s(12) > c.decode_s(8), "beyond the last measured point it keeps growing"
    assert c.plateau == 8, "throughput stops improving at 8 concurrent decodes: the worker cap"
    with pytest.raises(ValueError, match="not in stt_concurrency.csv"):
        loadmodel.SttCurve("no-such-model")


def test_stt_workers_queue_beyond_the_cap_and_slow_down_with_concurrency(monkeypatch):
    stt = loadmodel.ModelledSTT(workers=2)
    stt.curve.points = [(1, 0.10), (2, 0.20)]  # fast, so the test is quick: 1 decode 0.10 s, 2 concurrent 0.20 s each
    stt.curve.ref_audio_s = 1.0
    audio = bytes(32000)  # 1 s
    done = []

    def run():
        t = time.perf_counter()
        stt.transcribe(audio)
        done.append(time.perf_counter() - t)
    threads = [threading.Thread(target=run) for _ in range(4)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert stt.peak_queue >= 2, "with 2 workers and 4 requests two had to wait"
    assert max(done) > 0.35, f"the last request waited for the first two: {sorted(done)}"
    assert min(done) >= 0.09


def test_llm_budget_is_per_minute_for_the_whole_process_and_answers_429(monkeypatch):
    llm = loadmodel.ModelledLLM(rpm=3)
    llm.latency = {"classify": [0.0], "phrase": [0.0]}
    for _ in range(3):
        assert llm.generate("s", "u", 50, True).text.startswith('{"quality"')
    with pytest.raises(ProviderError) as e:
        llm.generate("s", "u", 50, False)
    assert e.value.status == "rate_limited" and e.value.retryable and e.value.status_code == 429 and e.value.retry_after >= 1
    assert llm.rejected == 1


def test_a_storm_window_fails_a_share_of_calls_only_while_it_lasts():
    llm = loadmodel.ModelledLLM(rpm=0, storm=(0.0, 0.3, 1.0))
    llm.latency = {"classify": [0.0], "phrase": [0.0]}
    with pytest.raises(ProviderError):
        llm.generate("s", "u", 50, True)
    time.sleep(0.35)
    assert llm.generate("s", "u", 50, True)  # the storm is over


def test_the_factory_hands_every_request_the_same_modelled_provider(monkeypatch):
    monkeypatch.setattr(loadmodel, "_SHARED", {})
    a, b = make_llm("modelled"), make_llm("modelled")
    assert a.providers[0] is b.providers[0], "one request budget for all students"


def test_blocking_calls_run_in_a_pool_larger_than_the_default_twelve(monkeypatch):
    """The knee found by the load test: queued STT answers sat in asyncio's small default pool and starved TTS and the engine."""
    import asyncio
    from fastapi.testclient import TestClient
    from app.api.main import create_app
    from app.api.settings import Settings

    monkeypatch.setenv("EXECUTOR_THREADS", "40")

    async def pool_size():
        return asyncio.get_running_loop()._default_executor._max_workers

    app = create_app(Settings(faculty_tokens={}, contract_stub=True))

    @app.get("/_pool")
    async def pool():
        return {"threads": await pool_size()}

    with TestClient(app) as client:
        assert client.get("/_pool").json() == {"threads": 40}


def test_real_stt_runs_no_more_processes_than_its_worker_cap():
    from app.voice.config import VoiceConfig
    assert VoiceConfig.from_env({"STT_WORKERS": "3"}).stt_workers == 3
    assert 1 <= VoiceConfig.from_env({}).stt_workers <= 8


def test_tts_processes_share_the_cores_so_a_second_one_adds_little(monkeypatch):
    """Real Piper measurement (results/load/piper_procs.csv): more processes do not add throughput, and the cap is honoured."""
    import threading
    import time as t
    from app.loadmodel import ModelledTTS

    tts = ModelledTTS(procs=2)
    assert tts.points[0][0] == 1 and tts.ref_words > 5
    peak, now, lock = [0], [0], threading.Lock()
    real_sleep = t.sleep

    def watched(seconds):
        with lock:
            now[0] += 1
            peak[0] = max(peak[0], now[0])
        real_sleep(0.01)
        with lock:
            now[0] -= 1

    monkeypatch.setattr("app.loadmodel.time.sleep", watched)
    jobs = [threading.Thread(target=tts.synthesize, args=("one short sentence here",)) for _ in range(6)]
    [j.start() for j in jobs]
    [j.join() for j in jobs]
    assert peak[0] <= 2
    best = max(tts.points, key=lambda p: p[0] / p[1])
    assert best[0] / best[1] < 2 * tts.points[0][0] / tts.points[0][1]  # two processes are less than twice one
