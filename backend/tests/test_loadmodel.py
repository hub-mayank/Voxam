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
