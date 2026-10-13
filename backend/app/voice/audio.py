"""Audio helpers with no dependencies (PCM16 little-endian mono as `bytes`/`array('h')`) and the two-sided session recorder.
Pure Python on purpose: V1 needs no numpy; the real providers (V2) bring their own libraries."""
import math
import struct
import sys
import wave
from array import array
from pathlib import Path

RATE = 16_000          # the recording and the student's stream
HEADER = 44            # canonical WAV header


def _le(a: array) -> array:
    if sys.byteorder == "big":  # pragma: no cover
        a.byteswap()
    return a


def tone(seconds: float, rate: int = 22_050, freq: float = 220.0, amp: float = 0.03) -> bytes:
    """A quiet sine tone: the stub TTS voice. amp 0.03 is about -30 dBFS."""
    n = int(seconds * rate)
    peak = amp * 32767
    return _le(array("h", (int(peak * math.sin(2 * math.pi * freq * i / rate)) for i in range(n)))).tobytes()


def resample(pcm: bytes, src: int, dst: int = RATE) -> bytes:
    """Linear-interpolation resampler, good enough for a replay recording (not for speech recognition)."""
    if src == dst or not pcm:
        return pcm
    samples = _le(array("h", pcm))
    n_out = int(len(samples) * dst / src)
    out = array("h", bytes(2 * n_out))
    ratio = src / dst
    last = len(samples) - 1
    for i in range(n_out):
        pos = i * ratio
        j = int(pos)
        if j >= last:
            out[i] = samples[last]
        else:
            frac = pos - j
            out[i] = int(samples[j] * (1 - frac) + samples[j + 1] * frac)
    return _le(out).tobytes()


def duration_s(pcm: bytes, rate: int) -> float:
    return len(pcm) / 2 / rate


def wav_header(frames: int, channels: int = 2, rate: int = RATE) -> bytes:
    data = frames * channels * 2
    return (b"RIFF" + struct.pack("<I", 36 + data) + b"WAVEfmt " + struct.pack("<IHHIIHH", 16, 1, channels, rate, rate * channels * 2, channels * 2, 16)
            + b"data" + struct.pack("<I", data))


class SessionRecorder:
    """One stereo WAV per session, 16 kHz 16-bit: left = student, right = AI, both on the wall-clock timeline that starts at
    `t0` (the session's started_at as epoch seconds). Writes land at their time on the timeline; gaps become silence; a channel
    never goes backwards (AI audio sent faster than real time is queued behind what was already written).
    Frames are flushed to the file (header kept valid) by `tick`, at most ~1 s behind; a reconnect re-opens the same file."""

    def __init__(self, path: Path, t0: float, tolerance_s: float = 0.04):
        self.path, self.t0, self.tol = Path(path), t0, int(tolerance_s * RATE)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.frames = 0  # frames already in the file
        if self.path.exists() and self.path.stat().st_size >= HEADER:
            with wave.open(str(self.path)) as w:
                self.frames = w.getnframes()
        else:
            self.path.write_bytes(wav_header(0))
        self.buf = {"student": array("h"), "ai": array("h")}

    def _end(self, side: str) -> int:
        return self.frames + len(self.buf[side])  # next free sample index of this channel

    def _index(self, at: float) -> int:
        return max(0, round((at - self.t0) * RATE))

    def _write(self, side: str, pcm: bytes, start: int) -> tuple[int, int]:
        cursor = self._end(side)
        if start - cursor > self.tol:
            self.buf[side].extend(array("h", bytes(2 * (start - cursor))))
            cursor = start
        self.buf[side].extend(_le(array("h", pcm[: len(pcm) // 2 * 2])))
        return cursor, self._end(side)

    def write_student(self, pcm: bytes, at: float) -> tuple[int, int]:
        """`pcm` ends at wall time `at` (a frame is received after it was spoken). -> (start_ms, end_ms) on the timeline."""
        s, e = self._write("student", pcm, self._index(at) - len(pcm) // 2)
        return s * 1000 // RATE, e * 1000 // RATE

    def write_ai(self, pcm16k: bytes, at: float) -> tuple[int, int]:
        """`pcm16k` starts no earlier than wall time `at` and after the AI audio already written."""
        s, e = self._write("ai", pcm16k, self._index(at))
        return s * 1000 // RATE, e * 1000 // RATE

    def position_ms(self, side: str) -> int:
        return self._end(side) * 1000 // RATE

    def tick(self, now: float):
        """Pad both channels up to `now`, then write every frame both channels have to the file."""
        upto = self._index(now)
        for side in ("student", "ai"):
            if upto - self._end(side) > 0:
                self.buf[side].extend(array("h", bytes(2 * (upto - self._end(side)))))
        self.flush()

    def flush(self):
        n = min(len(self.buf["student"]), len(self.buf["ai"]))
        if n == 0:
            return
        out = array("h", bytes(4 * n))
        out[0::2], out[1::2] = self.buf["student"][:n], self.buf["ai"][:n]
        with open(self.path, "r+b") as f:
            f.seek(HEADER + self.frames * 4)
            f.write(_le(out).tobytes())
            self.frames += n
            f.seek(0)
            f.write(wav_header(self.frames))
        for side in self.buf:
            del self.buf[side][:n]

    def close(self, now: float):
        self.tick(now)
        # whatever one channel still has beyond the other is padded on the other side, so nothing is lost
        longest = max(self._end("student"), self._end("ai"))
        for side in self.buf:
            self.buf[side].extend(array("h", bytes(2 * (longest - self._end(side)))))
        self.flush()
