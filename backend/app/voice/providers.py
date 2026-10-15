"""STT and TTS adapters for the voice server. One interface per kind so a bigger model or a cloud voice is a config change (D19).
`stub` needs no models: scripted transcripts and a quiet tone, so the frontend and the protocol tests run anywhere.
`local` (whisper.cpp + Piper in a subprocess) arrives with V2."""
import re
import threading
import time
from typing import Protocol

from . import audio
from .config import VoiceConfig

STUB_SENTENCES = [
    "A hash table maps a key to an array index with a hash function, and collisions are handled by chaining or open addressing, "
    "so lookups are constant time on average.",
    "Big O describes how running time grows with input size and ignores constants, so binary search is logarithmic while a linear scan is linear.",
    "An index is an extra structure, usually a B-tree, that lets the database find rows without scanning the table, at the cost of slower writes and more space.",
    "A process has its own memory space while threads inside a process share memory, which makes threads cheaper but needs synchronisation.",
    "I would check what changed recently, look at logs and metrics to see where the time goes, and isolate whether it is the database or the network.",
    "I would generate a short unique id, store the mapping in a database with an index on the id, and cache hot links to keep reads fast.",
]


class STT(Protocol):
    name: str

    def transcribe(self, pcm16k: bytes, language: str | None = None) -> tuple[str, float | None]:
        """16 kHz mono PCM16 -> (text, confidence 0-1 or None). language: en | hi | auto, or None for the server default."""


class TTS(Protocol):
    name: str

    def synthesize(self, sentence: str, *, cache: bool = True) -> tuple[bytes, int]:
        """One sentence -> (PCM16 mono, sample rate)."""


def split_sentences(text: str) -> list[str]:
    parts = [p.strip() for p in re.split(r"(?<=[.!?])\s+", text.strip()) if p.strip()]
    return parts or [text.strip()]


class StubSTT:
    name = "stub-stt"

    def __init__(self, delay_ms: int = 300):
        self.delay, self.n = delay_ms / 1000, 0

    def transcribe(self, pcm16k: bytes, language: str | None = None):
        time.sleep(self.delay)
        self.n += 1
        return f"[stub answer {self.n}] {STUB_SENTENCES[(self.n - 1) % len(STUB_SENTENCES)]}", 0.9


class StubTTS:
    name = "stub-tts"
    rate = 22_050

    def synthesize(self, sentence: str, *, cache: bool = True):
        seconds = max(0.6, 0.055 * len(sentence.split()))
        return audio.tone(seconds, self.rate), self.rate


_LOCAL = {}
_LOCAL_LOCK = threading.Lock()  # sessions starting together must not each start their own Piper processes
# one set of local providers per process: Piper keeps model processes alive between connections


def make_providers(cfg: VoiceConfig):
    if cfg.provider == "stub":
        return StubSTT(cfg.stt_ms), StubTTS()
    if cfg.provider == "modelled":  # load tests: measured latency and capacity models instead of real speech models (app/loadmodel.py)
        from ..loadmodel import shared
        return shared("stt"), shared("tts")
    if cfg.provider == "local":
        from .local import CachedTTS, PiperTTS, WhisperCppSTT
        key = (str(cfg.models_dir), cfg.whisper_size, cfg.whisper_lang, str(cfg.piper_model), cfg.piper_procs, str(cfg.tts_cache))
        with _LOCAL_LOCK:
            if key not in _LOCAL:
                stt, tts = WhisperCppSTT(cfg), CachedTTS(PiperTTS(cfg), cfg.tts_cache)
                stt.transcribe(bytes(32000))  # one second of silence: loads the model into the page cache
                tts.inner.synthesize("Ready.")  # starts the Piper process(es) and loads the voice
                _LOCAL[key] = (stt, tts)
            return _LOCAL[key]
    raise RuntimeError(f"unknown VOICE_PROVIDER={cfg.provider!r}; use stub, local or modelled")
