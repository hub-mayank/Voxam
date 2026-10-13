"""Level-based end-of-speech detector used by the stub (hands-free) mode. The real one is Silero (V3); same interface.
Feed it PCM16 frames; it says when speech started and when `hangover_ms` of quiet ended the answer."""
from array import array

from .audio import _le

THRESHOLD = 250  # mean absolute sample value that counts as speech


class LevelVad:
    def __init__(self, hangover_ms: int = 600, start_ms: int = 60):
        self.hangover, self.start_need = hangover_ms, start_ms
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
