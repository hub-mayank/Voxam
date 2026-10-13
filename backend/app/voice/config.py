"""Voice server settings, read from the environment when a connection opens (so tests can change them).
VOICE_PROVIDER   stub (no models: scripted transcripts, tone audio) | local (whisper.cpp + Piper; arrives with V2)
AUDIO_DIR        where the per-session recordings go (default ./audio, gitignored)
VOICE_TIMER_S    seconds between `timer` messages (default 5)
VOICE_SILENCE_S  seconds without speech before the one silence prompt per question (default 20)
VOICE_STT_MS     simulated STT time in stub mode (default 300)
Local providers (VOICE_PROVIDER=local):
VOICE_MODELS_DIR models folder (default <repo>/spikes/voice/data/models: whisper.cpp/ggml-<size>-q5_1.bin and piper/en/en_GB/alba/medium/...)
WHISPER_CLI      whisper.cpp binary (default whisper-cli on PATH: brew install whisper-cpp)
WHISPER_SIZE     base | small (default base); WHISPER_LANG en | hi | auto (default en: Hinglish is decoded as English, D19); WHISPER_THREADS (4)
PIPER_BIN        the piper executable, run as a separate process (GPL isolation, D19); default `piper` on PATH, then <repo>/.venv/bin/piper
PIPER_MODEL      voice file (default en_GB-alba-medium.onnx in the models folder); PIPER_PROCS persistent processes (default 1)
VOICE_VAD        silero | level: end-of-speech detector for hands-free mode (default silero with local speech, level with the stub)
VOICE_HANGOVER_MS  quiet that ends an answer (default 600); VOICE_PREROLL_MS audio kept from before speech was detected (default 300)
TTS_CACHE        rendered-audio cache folder (default <AUDIO_DIR>/tts_cache); fixed lines are rendered once and reused"""
import os
import shutil
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]


@dataclass(frozen=True)
class VoiceConfig:
    provider: str = "stub"
    audio_dir: Path = Path("audio")
    timer_s: float = 5.0
    silence_s: float = 20.0
    stt_ms: int = 300
    warning_ms: int = 60_000
    models_dir: Path = REPO / "spikes" / "voice" / "data" / "models"
    whisper_cli: str = "whisper-cli"
    whisper_size: str = "base"
    whisper_lang: str = "en"
    whisper_threads: int = 4
    piper_bin: str = "piper"
    piper_model: Path = None
    piper_procs: int = 1
    tts_cache: Path = None
    vad: str = "level"
    hangover_ms: int = 600
    preroll_ms: int = 300

    @classmethod
    def from_env(cls, env=None) -> "VoiceConfig":
        env = os.environ if env is None else env
        models = Path(env.get("VOICE_MODELS_DIR") or REPO / "spikes" / "voice" / "data" / "models").resolve()
        audio_dir = Path(env.get("AUDIO_DIR") or "audio").resolve()
        piper = env.get("PIPER_BIN") or shutil.which("piper") or str(REPO / ".venv" / "bin" / "piper")
        provider = env.get("VOICE_PROVIDER", "stub").strip().lower() or "stub"
        return cls(provider=provider, audio_dir=audio_dir,
                   vad=(env.get("VOICE_VAD") or ("silero" if provider == "local" else "level")).strip().lower(),
                   hangover_ms=int(env.get("VOICE_HANGOVER_MS", 600)), preroll_ms=int(env.get("VOICE_PREROLL_MS", 300)),
                   timer_s=float(env.get("VOICE_TIMER_S", 5)), silence_s=float(env.get("VOICE_SILENCE_S", 20)),
                   stt_ms=int(env.get("VOICE_STT_MS", 300)), models_dir=models,
                   whisper_cli=env.get("WHISPER_CLI") or "whisper-cli", whisper_size=env.get("WHISPER_SIZE", "base"),
                   whisper_lang=env.get("WHISPER_LANG", "en"), whisper_threads=int(env.get("WHISPER_THREADS", 4)),
                   piper_bin=piper, piper_model=Path(env["PIPER_MODEL"]) if env.get("PIPER_MODEL") else
                   models / "piper" / "en" / "en_GB" / "alba" / "medium" / "en_GB-alba-medium.onnx",
                   piper_procs=max(1, int(env.get("PIPER_PROCS", 1))),
                   tts_cache=Path(env["TTS_CACHE"]).resolve() if env.get("TTS_CACHE") else audio_dir / "tts_cache")
