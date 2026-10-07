"""Silero VAD (ONNX, via pysilero-vad) plus the endpointing and segmentation rules the voice pipeline would use."""
import numpy as np
from pysilero_vad import SileroVoiceActivityDetector

from common import SAMPLE_RATE, now

FRAME = 512                       # samples per VAD frame (32 ms at 16 kHz); the model requires exactly this
FRAME_MS = FRAME * 1000 / SAMPLE_RATE


def to_pcm16(audio: np.ndarray) -> bytes:
    return (np.clip(audio, -1, 1) * 32767).astype("<i2").tobytes()


def speech_probs(audio: np.ndarray, detector=None):
    """-> (probabilities per 32 ms frame, seconds of VAD compute per frame). Last partial frame is dropped."""
    detector = detector or SileroVoiceActivityDetector()
    pcm = to_pcm16(audio)
    probs, costs = [], []
    for i in range(len(audio) // FRAME):
        chunk = pcm[i * FRAME * 2:(i + 1) * FRAME * 2]
        t = now()
        probs.append(detector(chunk))
        costs.append(now() - t)
    return np.array(probs), np.array(costs)


def endpoint_frame(probs, hangover_ms: float, threshold: float = 0.5, min_speech_ms: float = 150):
    """Frame index at which end-of-turn fires: speech has started (>= min_speech_ms) and then `hangover_ms` of continuous
    non-speech has passed. None if it never fires. The turn's last speech frame is `fired - hangover frames`."""
    need = int(round(hangover_ms / FRAME_MS))
    speech_frames, silence = 0, 0
    for i, p in enumerate(probs):
        if p >= threshold:
            speech_frames, silence = speech_frames + 1, 0
        elif speech_frames * FRAME_MS >= min_speech_ms:
            silence += 1
            if silence >= need:
                return i
    return None


def speech_segments(probs, threshold: float = 0.5, min_pause_ms: float = 250, min_speech_ms: float = 100):
    """[(start_frame, end_frame_exclusive)] of speech separated by pauses of at least min_pause_ms."""
    gap = int(round(min_pause_ms / FRAME_MS))
    segs, start, last, run = [], None, None, 0
    for i, p in enumerate(probs):
        if p >= threshold:
            if start is None:
                start = i
            last, run = i, 0
        elif start is not None:
            run += 1
            if run >= gap:
                segs.append((start, last + 1))
                start, run = None, 0
    if start is not None:
        segs.append((start, last + 1))
    return [(a, b) for a, b in segs if (b - a) * FRAME_MS >= min_speech_ms]


def force_cuts(audio: np.ndarray, start: int, end: int, max_s: float = 8.0, search_s: float = 2.0):
    """Split [start, end) (sample indexes) into pieces of at most max_s, cutting at the quietest 20 ms inside the last
    search_s of each window, for continuous speech with no pause to cut at. -> list of (start, end)."""
    pieces, win, hop = [], int(max_s * SAMPLE_RATE), int(0.02 * SAMPLE_RATE)
    while end - start > win:
        lo = start + win - int(search_s * SAMPLE_RATE)
        energy = [np.sqrt(np.mean(audio[i:i + hop] ** 2)) for i in range(lo, start + win, hop)]
        cut = lo + int(np.argmin(energy)) * hop
        pieces.append((start, cut))
        start = cut
    pieces.append((start, end))
    return pieces
