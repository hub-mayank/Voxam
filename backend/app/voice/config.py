"""Voice server settings, read from the environment when a connection opens (so tests can change them).
VOICE_PROVIDER   stub (no models: scripted transcripts, tone audio) | local (whisper.cpp + Piper; arrives with V2)
AUDIO_DIR        where the per-session recordings go (default ./audio, gitignored)
VOICE_TIMER_S    seconds between `timer` messages (default 5)
VOICE_SILENCE_S  seconds without speech before the one silence prompt per question (default 20)
VOICE_STT_MS     simulated STT time in stub mode (default 300)"""
import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class VoiceConfig:
    provider: str = "stub"
    audio_dir: Path = Path("audio")
    timer_s: float = 5.0
    silence_s: float = 20.0
    stt_ms: int = 300
    warning_ms: int = 60_000

    @classmethod
    def from_env(cls, env=None) -> "VoiceConfig":
        env = os.environ if env is None else env
        return cls(provider=env.get("VOICE_PROVIDER", "stub").strip().lower() or "stub",
                   audio_dir=Path(env.get("AUDIO_DIR") or "audio").resolve(),
                   timer_s=float(env.get("VOICE_TIMER_S", 5)), silence_s=float(env.get("VOICE_SILENCE_S", 20)),
                   stt_ms=int(env.get("VOICE_STT_MS", 300)))
