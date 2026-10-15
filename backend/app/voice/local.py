"""Local speech providers (VOICE_PROVIDER=local): whisper.cpp for STT and Piper for TTS, both as separate processes.
Piper is GPL-3.0: we never import it, we only run its executable (D19). Nothing here needs numpy."""
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
import wave
from pathlib import Path

from .config import VoiceConfig

CLI_TIMEOUT_S = 60


class ProviderUnavailable(RuntimeError):
    pass


def _need(path: Path, what: str, hint: str):
    if not Path(path).exists():
        raise ProviderUnavailable(f"{what} not found at {path}. {hint}")


class WhisperCppSTT:
    """`whisper-cli` per answer (Metal on Apple Silicon). Each call starts a process, so model load and start-up (about 0.1 s for
    base q5_1) are part of the measured STT time. Confidence = mean token probability from the CLI's full JSON output."""
    def __init__(self, cfg: VoiceConfig):
        self.cfg = cfg
        self.model = cfg.models_dir / "whisper.cpp" / f"ggml-{cfg.whisper_size}-q5_1.bin"
        self.name = f"whisper.cpp-{cfg.whisper_size}-q5_1"
        self.slots = threading.BoundedSemaphore(cfg.stt_workers)  # more processes than cores only makes every answer slower
        if shutil.which(cfg.whisper_cli) is None and not Path(cfg.whisper_cli).exists():
            raise ProviderUnavailable(f"{cfg.whisper_cli!r} not found: brew install whisper-cpp (or set WHISPER_CLI)")
        _need(self.model, "whisper.cpp model", "Run spikes/voice/fetch_models.py or set VOICE_MODELS_DIR.")

    def transcribe(self, pcm16k: bytes):
        with tempfile.TemporaryDirectory() as d:
            wav, base = Path(d) / "in.wav", Path(d) / "out"
            with wave.open(str(wav), "wb") as w:
                w.setnchannels(1), w.setsampwidth(2), w.setframerate(16000), w.writeframes(pcm16k)
            cmd = [self.cfg.whisper_cli, "-m", str(self.model), "-f", str(wav), "-l", self.cfg.whisper_lang, "-nt",
                   "-t", str(self.cfg.whisper_threads), "-ojf", "-of", str(base)]
            with self.slots:
                done = subprocess.run(cmd, capture_output=True, text=True, timeout=CLI_TIMEOUT_S)
            out = base.with_suffix(".json")
            if done.returncode != 0 or not out.exists():
                raise ProviderUnavailable(f"whisper-cli failed (rc={done.returncode}): {done.stderr.strip()[-200:]}")
            return parse_whisper_json(json.loads(out.read_text()))


def parse_whisper_json(data: dict):
    """-> (text, mean token probability or None). Special tokens ([_BEG_], [_TT_...]) are ignored."""
    segments = data.get("transcription") or []
    text = " ".join(s.get("text", "").strip() for s in segments).strip()
    probs = [t["p"] for s in segments for t in s.get("tokens", []) if not t.get("text", "").startswith("[_") and "p" in t]
    return text, (round(sum(probs) / len(probs), 3) if probs else None)


class _PiperProc:
    """One persistent `piper` process: one text line in, one WAV file out (-d dir), so audio boundaries are exact."""
    def __init__(self, cfg: VoiceConfig, n: int):
        self.cfg, self.n = cfg, n
        self.dir = Path(tempfile.mkdtemp(prefix=f"piper{n}_"))
        self.lock = threading.Lock()
        self.proc = None

    def _start(self):
        self.proc = subprocess.Popen([self.cfg.piper_bin, "-m", str(self.cfg.piper_model), "-d", str(self.dir), "--output-dir-naming", "timestamp"],
                                     stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def say(self, text: str) -> tuple[bytes, int]:
        with self.lock:
            for attempt in (0, 1):
                if self.proc is None or self.proc.poll() is not None:
                    self._start()
                try:
                    return self._request(text)
                except (BrokenPipeError, TimeoutError, OSError):
                    if self.proc and self.proc.poll() is None:
                        self.proc.kill()
                    self.proc = None
                    if attempt:
                        raise ProviderUnavailable("piper process died twice in a row")

    def _request(self, text: str):
        before = set(self.dir.glob("*.wav"))
        self.proc.stdin.write((text.replace("\n", " ") + "\n").encode())
        self.proc.stdin.flush()
        deadline, seen = time.monotonic() + CLI_TIMEOUT_S, []
        while time.monotonic() < deadline:
            fresh = set(self.dir.glob("*.wav")) - before
            if fresh:
                f = fresh.pop()
                size = f.stat().st_size
                seen = (seen + [size])[-3:]
                if size > 44 and len(seen) == 3 and len(set(seen)) == 1:  # the file stopped growing
                    with wave.open(str(f)) as w:
                        pcm, rate = w.readframes(w.getnframes()), w.getframerate()
                    f.unlink()
                    return pcm, rate
            if self.proc.poll() is not None:
                raise OSError("piper exited")
            time.sleep(0.01)
        raise TimeoutError("piper did not answer")

    def close(self):
        if self.proc and self.proc.poll() is None:
            try:
                self.proc.stdin.close()
                self.proc.wait(timeout=5)
            except Exception:
                self.proc.kill()
        shutil.rmtree(self.dir, ignore_errors=True)


class PiperTTS:
    """Piper voice (default en_GB alba) through persistent separate processes, a small pool (PIPER_PROCS)."""
    RATE = 22_050  # every Piper medium voice; only used for the silence above

    def __init__(self, cfg: VoiceConfig):
        self.name = f"piper-{cfg.piper_model.stem}"
        if shutil.which(cfg.piper_bin) is None and not Path(cfg.piper_bin).exists():
            raise ProviderUnavailable(f"piper executable {cfg.piper_bin!r} not found (set PIPER_BIN)")
        _need(cfg.piper_model, "Piper voice", "Run spikes/voice/fetch_models.py or set PIPER_MODEL.")
        self.pool = [_PiperProc(cfg, i) for i in range(cfg.piper_procs)]
        self._next, self._guard = 0, threading.Lock()

    def synthesize(self, sentence: str, *, cache: bool = True):
        if not re.search(r"\w", sentence):  # "..." has nothing to say; Piper exits on it, so give a short pause instead
            return bytes(2 * int(0.25 * self.RATE)), self.RATE
        with self._guard:
            free = next((p for p in self.pool if not p.lock.locked()), None)
            if free is None:
                free = self.pool[self._next % len(self.pool)]
                self._next += 1
        return free.say(sentence)

    def close(self):
        for p in self.pool:
            p.close()


class CachedTTS:
    """Write-through cache for reusable speech; dynamic student-specific turns opt out.
    The key includes the voice name, so changing the voice never serves old audio."""
    def __init__(self, inner, cache_dir: Path):
        self.inner, self.dir, self.name = inner, Path(cache_dir), inner.name
        self.dir.mkdir(parents=True, exist_ok=True)
        self.hits = self.misses = 0

    def _path(self, sentence: str) -> Path:
        return self.dir / (hashlib.sha1(f"{self.inner.name}\n{sentence}".encode()).hexdigest() + ".wav")

    def synthesize(self, sentence: str, *, cache: bool = True):
        if not cache:
            return self.inner.synthesize(sentence)
        path = self._path(sentence)
        if path.exists():
            try:
                with wave.open(str(path)) as w:
                    self.hits += 1
                    return w.readframes(w.getnframes()), w.getframerate()
            except (wave.Error, EOFError):
                pass  # a half-written file from a crash: render again
        pcm, rate = self.inner.synthesize(sentence)
        self.misses += 1
        tmp = path.with_suffix(f".{os.getpid()}.tmp")
        with wave.open(str(tmp), "wb") as w:
            w.setnchannels(1), w.setsampwidth(2), w.setframerate(rate), w.writeframes(pcm)
        os.replace(tmp, path)
        return pcm, rate

    def close(self):
        getattr(self.inner, "close", lambda: None)()
