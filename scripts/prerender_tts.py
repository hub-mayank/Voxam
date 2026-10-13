"""Render the AI's fixed lines once so a live viva never waits for speech synthesis on them: the opener, the closer, the fallback and
canned replies, the silence/repeat prompts, and every question of a viva's bank. Writes into the TTS cache (TTS_CACHE or
<AUDIO_DIR>/tts_cache). Needs the local providers (VOICE_PROVIDER=local settings, see backend/app/voice/config.py).
Usage: python scripts/prerender_tts.py --bank config/question_bank.dsa.json [--bank another.json]   (a bank file needs no database)"""
import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app import interviewer  # noqa: E402
from app.voice.config import VoiceConfig  # noqa: E402
from app.voice.local import CachedTTS, PiperTTS  # noqa: E402
from app.voice.providers import split_sentences  # noqa: E402
from app.voice.session import REPEAT_LINE, SILENCE_LINE  # noqa: E402


def fixed_lines() -> list:
    lines = [interviewer.OPENER["text"], interviewer.CLOSER, interviewer.DEFAULT_REPLY, SILENCE_LINE, REPEAT_LINE]
    lines += [f["text"] for f in interviewer.FALLBACKS] + list(interviewer.FALLBACK_REPLIES.values())
    return lines


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bank", action="append", default=[], help="question bank JSON file (repeatable)")
    a = ap.parse_args()
    cfg = VoiceConfig.from_env()
    tts = CachedTTS(PiperTTS(cfg), cfg.tts_cache)
    texts = fixed_lines()
    for path in a.bank:
        texts += [q["text"] for q in json.loads(Path(path).read_text())]
    sentences = list(dict.fromkeys(s for t in texts for s in split_sentences(t)))
    t0 = time.perf_counter()
    for s in sentences:
        tts.synthesize(s)
    print(f"{len(sentences)} sentences: {tts.misses} rendered, {tts.hits} already cached, {time.perf_counter() - t0:.1f}s -> {cfg.tts_cache}")
    tts.close()


if __name__ == "__main__":
    main()
