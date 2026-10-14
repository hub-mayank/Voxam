"""Modelled providers for load tests: the real server code (engine, WebSocket, database, recorder, scoring queue) runs, but speech
recognition, the LLM and speech synthesis are replaced by models of their *measured* behaviour, so 150 sessions can be driven on one
machine without 150 real model runs. Every number a model uses is read from a file in results/ (empirical samples, never typed in):
  STT  results/voice_spike/stt_concurrency.csv   decode time against concurrent decodes, and a worker cap (throughput plateaus)
  TTS  results/voice_spike/tts_piper-en_GB-alba-medium.csv   synthesis time per sentence, and a process cap (PIPER_PROCS)
  LLM  results/groq_interview_tokens.csv   per-call latency of classify and phrase (second run: sliding minute window), a per-minute
       request limit shared by all sessions (LOAD_LLM_RPM, 0 = no limit) and an optional 429 storm window.
These prove OUR orchestration under load, not vendor behaviour (D6): results are labelled provider=stub."""
import csv
import os
import random
import threading
import time
from collections import deque
from pathlib import Path

from .llm.base import Reply
from .llm.errors import ProviderError

RESULTS = Path(__file__).resolve().parents[2] / "results"


def _rows(path: Path) -> list:
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


class SttCurve:
    """decode_p50_s against concurrent decodes for one engine, linearly interpolated; beyond the last measured point it keeps growing
    with the last slope (work still queues)."""

    def __init__(self, model: str, path: Path = RESULTS / "voice_spike" / "stt_concurrency.csv"):
        rows = [r for r in _rows(path) if r["model"] == model]
        if not rows:
            raise ValueError(f"{model!r} is not in {path.name}: {sorted({r['model'] for r in _rows(path)})}")
        self.points = sorted((int(r["concurrent_decodes"]), float(r["decode_p50_s"])) for r in rows)
        self.ref_audio_s = float(rows[0]["clip_audio_s"])
        self.plateau = max(self.points, key=lambda p: int(p[0]) / p[1])[0]  # concurrency with the best throughput = sensible worker cap

    def decode_s(self, concurrent: int) -> float:
        c = max(1, concurrent)
        pts = self.points
        if c <= pts[0][0]:
            return pts[0][1]
        for (c0, t0), (c1, t1) in zip(pts, pts[1:]):
            if c <= c1:
                return t0 + (t1 - t0) * (c - c0) / (c1 - c0)
        (c0, t0), (c1, t1) = pts[-2], pts[-1]
        return t1 + (t1 - t0) / (c1 - c0) * (c - c1)


class ModelledSTT:
    """Queueing model: at most `workers` decodes run at once (the rest wait their turn); a decode takes the measured time for the
    current number of concurrent decodes, scaled by the audio length against the measured clip."""
    name = "modelled-stt"

    def __init__(self, model: str = None, workers: int = None, rng=None):
        self.curve = SttCurve(model or os.environ.get("LOAD_STT_MODEL", "faster-whisper-base-int8"))
        self.workers = workers or int(os.environ.get("LOAD_STT_WORKERS", 0)) or self.curve.plateau
        self.sem = threading.BoundedSemaphore(self.workers)
        self.lock, self.active, self.n, self.rng = threading.Lock(), 0, 0, rng or random.Random(7)
        self.peak_queue = self.waiting = 0

    def transcribe(self, pcm16k: bytes):
        from .voice.providers import STUB_SENTENCES
        audio_s = len(pcm16k) / 32000
        with self.lock:
            self.waiting += 1
            self.peak_queue = max(self.peak_queue, self.waiting)
        self.sem.acquire()
        with self.lock:
            self.waiting -= 1
            self.active += 1
            self.n += 1
            n, c = self.n, self.active
        try:
            time.sleep(self.curve.decode_s(c) * max(audio_s, 0.5) / self.curve.ref_audio_s)
        finally:
            with self.lock:
                self.active -= 1
            self.sem.release()
        return f"[modelled answer {n}] {STUB_SENTENCES[n % len(STUB_SENTENCES)]}", 0.9


class ModelledTTS:
    """Synthesis time per sentence sampled from the measured Piper runs; `procs` sentences at a time (PIPER_PROCS)."""
    name = "modelled-tts"
    rate = 22_050

    def __init__(self, procs: int = None, path: Path = RESULTS / "voice_spike" / "tts_piper-en_GB-alba-medium.csv", rng=None):
        rows = _rows(path)
        self.per_word = sorted(float(r["total_synth_s"]) / max(1, int(r["words"])) for r in rows)
        self.sem = threading.BoundedSemaphore(procs or int(os.environ.get("LOAD_TTS_PROCS", 1)))
        self.rng = rng or random.Random(11)

    def synthesize(self, sentence: str):
        from .voice import audio
        words = max(1, len(sentence.split()))
        with self.sem:
            time.sleep(self.rng.choice(self.per_word) * words)
        return audio.tone(max(0.6, 0.055 * words), self.rate), self.rate


class ModelledLLM:
    """A provider with the measured per-call latency, one request-per-minute budget for the whole process, and a 429 storm."""
    provider, model, mode = "modelled", "groq-gpt-oss-20b-profile", "stub"
    name = "modelled:groq-gpt-oss-20b-profile"

    def __init__(self, rpm: float = None, storm: tuple = None, rng=None, path: Path = RESULTS / "groq_interview_tokens.csv"):
        rows = _rows(path)[59:]  # the second Groq run: sliding-window budget (the first run was delayed by fixed spacing)
        self.latency = {k: sorted(float(r["latency_ms"]) / 1000 for r in rows if r["kind"] == k) for k in ("classify", "phrase")}
        self.rpm = float(os.environ.get("LOAD_LLM_RPM", 27)) if rpm is None else rpm
        if storm is None and os.environ.get("LOAD_LLM_STORM"):
            start, dur, rate = os.environ["LOAD_LLM_STORM"].split(":")  # seconds after the first call, seconds, failure share
            storm = (float(start), float(dur), float(rate))
        self.storm, self.rng, self.t0 = storm, rng or random.Random(3), None
        self.window, self.lock, self.calls, self.rejected = deque(), threading.Lock(), 0, 0

    def generate(self, system: str, user: str, max_tokens: int, json_mode: bool) -> Reply:
        now = time.time()
        with self.lock:
            self.t0 = self.t0 or now
            self.calls += 1
            if self.storm and self.storm[0] <= now - self.t0 < self.storm[0] + self.storm[1] and self.rng.random() < self.storm[2]:
                self.rejected += 1
                raise ProviderError("HTTP 429 (storm)", "rate_limited", True, 429, retry_after=1.0)
            if self.rpm:
                while self.window and now - self.window[0] > 60:
                    self.window.popleft()
                if len(self.window) >= self.rpm:
                    self.rejected += 1
                    raise ProviderError("HTTP 429 (per-minute budget)", "rate_limited", True, 429, retry_after=max(1.0, 60 - (now - self.window[0])))
                self.window.append(now)
        kind = "classify" if json_mode else "phrase"
        time.sleep(self.rng.choice(self.latency[kind]))
        if json_mode:
            return Reply('{"quality": "%s"}' % self.rng.choice(["strong", "partial", "partial", "none"]), 250, 30)
        return Reply("Good. What trade-offs would you consider here?", 150, 25)


# One model of each per process, shared by every session: the queue, the worker cap and the request budget only mean something if all
# sessions compete for the same ones (a new object per request would give every student a private machine).
_SHARED = {}


def shared(kind: str):
    """kind: stt | tts | llm"""
    if kind not in _SHARED:
        _SHARED[kind] = {"stt": ModelledSTT, "tts": ModelledTTS, "llm": ModelledLLM}[kind]()
    return _SHARED[kind]
