"""End-of-speech detectors for hands-free mode, one interface: feed PCM16 mono 16 kHz frames of any size, get back the events
"speech_start" and "speech_end" those frames caused; `in_speech` says where we are; `set_start_ms` changes how much continuous
speech counts as a start (the session raises it while the AI is talking, so echo does not interrupt it); `reset` clears state.
  SileroVad  the real one: Silero VAD (pysilero-vad, MIT). A speech start needs `start_ms` of speech, an end needs `hangover_ms` of quiet.
  LevelVad   a loudness threshold, no model: used by the stub provider and as a fallback when pysilero-vad is not installed."""
import logging
from array import array
from typing import Callable

from .audio import _le

log = logging.getLogger("aiviva.voice")
THRESHOLD = 250  # mean absolute sample value that counts as speech (LevelVad)
SILERO_CHUNK_BYTES = 1024  # 512 samples = 32 ms, the size the model requires


class LevelVad:
    def __init__(self, hangover_ms: int = 600, start_ms: int = 60):
        self.hangover, self.start_need = hangover_ms, start_ms
        self.in_speech = False
        self.loud_ms = self.quiet_ms = 0.0

    def set_start_ms(self, ms: int):
        self.start_need = ms

    def reset(self):
        self.in_speech = False
        self.loud_ms = self.quiet_ms = 0.0

    def feed(self, frame: bytes, rate: int = 16_000) -> list[str]:
        """-> events from {"speech_start", "speech_end"} caused by this frame."""
        samples = _le(array("h", frame[: len(frame) // 2 * 2]))
        if not samples:
            return []
        ms = len(samples) * 1000 / rate
        loud = sum(abs(s) for s in samples) / len(samples) > THRESHOLD
        events = []
        if loud:
            self.loud_ms, self.quiet_ms = self.loud_ms + ms, 0.0
            if not self.in_speech and self.loud_ms >= self.start_need:
                self.in_speech = True
                events.append("speech_start")
        else:
            self.loud_ms = 0.0
            if self.in_speech:
                self.quiet_ms += ms
                if self.quiet_ms >= self.hangover:
                    self.in_speech = False
                    self.quiet_ms = 0.0
                    events.append("speech_end")
        return events


class SileroVad:
    """Silero VAD with start and hangover rules. `prob_fn(chunk_bytes) -> probability` is injectable for tests; by default the
    packaged model is loaded (one detector per session: it keeps recurrent state, which `reset` clears between answers)."""

    def __init__(self, hangover_ms: int = 600, start_ms: int = 96, threshold: float = 0.5, prob_fn: Callable[[bytes], float] = None):
        self.hangover, self.start_need, self.threshold = hangover_ms, start_ms, threshold
        self._model = None
        if prob_fn is None:
            from pysilero_vad import SileroVoiceActivityDetector  # raises ImportError when the package is missing
            self._model = SileroVoiceActivityDetector()
            prob_fn = self._model
        self._prob = prob_fn
        self._buf = b""
        self.in_speech = False
        self.loud_ms = self.quiet_ms = 0.0

    def set_start_ms(self, ms: int):
        self.start_need = ms

    def reset(self):
        if self._model is not None:
            self._model.reset()
        self._buf = b""
        self.in_speech = False
        self.loud_ms = self.quiet_ms = 0.0

    def feed(self, frame: bytes, rate: int = 16_000) -> list[str]:
        self._buf += frame[: len(frame) // 2 * 2]
        events = []
        while len(self._buf) >= SILERO_CHUNK_BYTES:
            chunk, self._buf = self._buf[:SILERO_CHUNK_BYTES], self._buf[SILERO_CHUNK_BYTES:]
            ms = SILERO_CHUNK_BYTES / 2 * 1000 / rate
            if self._prob(chunk) >= self.threshold:
                self.loud_ms, self.quiet_ms = self.loud_ms + ms, 0.0
                if not self.in_speech and self.loud_ms >= self.start_need:
                    self.in_speech = True
                    events.append("speech_start")
            else:
                self.loud_ms = 0.0
                if self.in_speech:
                    self.quiet_ms += ms
                    if self.quiet_ms >= self.hangover:
                        self.in_speech = False
                        self.quiet_ms = 0.0
                        events.append("speech_end")
        return events


def make_vad(kind: str, hangover_ms: int):
    """kind: 'silero' (falls back to the level detector with a warning if pysilero-vad is missing) or 'level'."""
    if kind == "silero":
        try:
            return SileroVad(hangover_ms=hangover_ms)
        except ImportError:
            log.warning("pysilero-vad is not installed: using the loudness detector (pip install pysilero-vad)")
    return LevelVad(hangover_ms=hangover_ms)
