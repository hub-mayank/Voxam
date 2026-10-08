"""The Interviewer as the pipeline's brain.

The voice pipeline never decides phases, timing, follow-ups or scores. It does exactly three things per turn:
    1. turn audio into text            (VAD endpoint -> STT final)
    2. POST that text to the backend   POST /student/sessions/{sid}/answer  {text, client_seq}   <- engine: clock, policy, LLM
    3. turn the reply text into audio  (first sentence first)
The backend (T2b) owns the session: it rebuilds the Interviewer from stored turns, uses the persisted deadline, enforces the 15 minute
limit, is idempotent on client_seq (a retry after a dropped websocket is safe) and stores the transcript. So the voice worker is
stateless too and any worker can serve any turn.

This module is that adapter, run in-process against the real FastAPI app (tests only: TestClient). In production the same three
calls go over HTTP. LLM latency is either REAL (`TimedLLM` around an Ollama/Gemini adapter) or SIMULATED (`SimulatedLLM`, which
returns the mock engine's answers and records an explicit latency drawn from a profile; it never sleeps and is always labelled).
"""
import random
import re
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from common import ROOT

sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "backend" / "tests"))

from fastapi.testclient import TestClient  # noqa: E402

from app.api.main import create_app  # noqa: E402
from app.llm.mock import MockLLM  # noqa: E402
from harness import Clock, RAO, answer, auth, join, make_viva, settings_for, start  # noqa: E402

TOKENS_PER_WORD = 1.4


@dataclass
class Profile:
    """Assumed LLM latency: time to first token and decode speed. NOT a measurement; every use is labelled simulated."""
    name: str
    ttft_s: float
    tokens_per_s: float
    jitter: float = 0.25  # lognormal sigma


@dataclass
class Call:
    kind: str                 # classify or phrase
    tokens: float             # output tokens in the whole reply
    first_tokens: float       # output tokens before the first sentence ends (when TTS can start)
    real_s: float | None = None   # measured seconds, only for a real LLM
    system: str = ""              # the prompt, kept for a real LLM so the same call can be replayed (streaming probe, other providers)
    user: str = ""
    json_mode: bool = False
    max_tokens: int = 0

    def seconds(self, profile: Profile | None, rng: random.Random, first_sentence: bool):
        """Seconds this call puts on the critical path. Real calls report what was measured; simulated ones use the profile."""
        if self.real_s is not None:
            return self.real_s
        base = profile.ttft_s * rng.lognormvariate(0, profile.jitter)
        return base + (self.first_tokens if first_sentence else self.tokens) / profile.tokens_per_s


@dataclass
class Recorder:
    calls: list = field(default_factory=list)

    def clear(self):
        self.calls.clear()

    def critical_path_s(self, profile, rng):
        """classify must finish before phrase starts; TTS can start at the first sentence of the phrase call."""
        return sum(c.seconds(profile, rng, first_sentence=(c.kind == "phrase")) for c in self.calls)


    def critical_path_parallel_s(self, profile, rng):
        """If classify and the phrase for the likely action were started together (speculative phrasing), the LLM leg is the slower
        of the two, not their sum. Costs an extra LLM call per turn (free-quota relevant) and an engine change; not implemented in the backend."""
        times = [c.seconds(profile, rng, first_sentence=(c.kind == "phrase")) for c in self.calls]
        return max(times) if times else 0.0


class SimulatedLLM(MockLLM):
    """MockLLM answers; records how many tokens each call produced. Never sleeps. Label: the model name starts with 'simulated'."""
    def __init__(self, recorder: Recorder, label: str = "simulated-llm"):
        self.recorder, self.name = recorder, label

    def complete_json(self, system, user, max_tokens=200, kind="classify"):
        out = super().complete_json(system, user, max_tokens, kind)
        self.recorder.calls.append(Call(kind, 10, 10))  # {"quality":"partial"} is about 10 tokens
        return out

    def complete_text(self, system, user, max_tokens=120, kind="phrase"):
        out = super().complete_text(system, user, max_tokens, kind)
        first_sentence = re.split(r"(?<=[.!?])\s", out.strip())[0]
        self.recorder.calls.append(Call(kind, len(out.split()) * TOKENS_PER_WORD, len(first_sentence.split()) * TOKENS_PER_WORD))
        return out


class TimedLLM:
    """Wraps a REAL adapter chain and records the measured wall time of each call. The adapters do not stream, so the
    first-sentence time is the full time (pessimistic)."""
    def __init__(self, inner, recorder: Recorder):
        from common import now
        self.inner, self.recorder, self._now = inner, recorder, now
        self.name = getattr(inner, "name", "real")

    def _timed(self, fn, kind, system, user, max_tokens, json_mode):
        t = self._now()
        out = fn(system, user, max_tokens, kind)
        self.recorder.calls.append(Call(kind, 0, 0, real_s=self._now() - t, system=system, user=user, json_mode=json_mode, max_tokens=max_tokens))
        return out

    def complete_json(self, system, user, max_tokens=200, kind="classify"):
        return self._timed(self.inner.complete_json, kind, system, user, max_tokens, True)

    def complete_text(self, system, user, max_tokens=120, kind="phrase"):
        return self._timed(self.inner.complete_text, kind, system, user, max_tokens, False)


class Brain:
    """One student session on the real backend. `say(text)` is step 2 above."""
    def __init__(self, llm_factory, students=8):
        self.tmp = tempfile.TemporaryDirectory()
        self.clock = Clock()
        self.app = create_app(settings_for(Path(self.tmp.name), faculty_tokens={"tok-rao-0123456789": "dr-rao"}), llm_factory=llm_factory, now=self.clock)
        self.client = TestClient(self.app, raise_server_exceptions=True)
        self.codes = make_viva(self.client, students=tuple(f"S{i}" for i in range(students)))
        self.next_student, self.sid, self.headers, self.seq = 0, None, None, 0
        self.sessions = 0

    def _new_session(self):
        student = f"S{self.next_student}"
        self.next_student += 1
        self.sid, self.headers, _ = join(self.client, self.codes[student], student_id=student)
        opener = start(self.client, self.sid, self.headers)
        self.seq, self.sessions = 0, self.sessions + 1
        return opener["turn"]["text"]

    def say(self, text):
        """-> (reply text, ended, wall seconds the backend took, replayed). Starts a new session when the last one has ended."""
        from common import now
        if self.sid is None:
            self._new_session()
        self.seq += 1
        t = now()
        r = answer(self.client, self.sid, self.headers, self.seq, text=text or "(inaudible)")
        wall = now() - t
        if r.status_code == 409 and r.json()["error"]["code"] in ("session_ended", "deadline_passed"):
            self._new_session()
            self.seq = 1
            t = now()
            r = answer(self.client, self.sid, self.headers, self.seq, text=text or "(inaudible)")
            wall = now() - t
        assert r.status_code == 200, r.text
        body = r.json()
        if body["turn"]["ended"]:
            self.sid = None
        return body["turn"]["text"], body["turn"]["ended"], wall, body["replayed"]
