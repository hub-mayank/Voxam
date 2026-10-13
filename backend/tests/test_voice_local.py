"""The local speech providers (whisper.cpp, Piper) with fake executables, so no models are needed; plus one real round trip
that runs only where the binaries and models exist."""
import json
import os
import shutil
import stat
import sys
import threading
import wave
from pathlib import Path

import pytest

from app.voice import audio, local
from app.voice.config import REPO, VoiceConfig
from app.voice.local import CachedTTS, PiperTTS, ProviderUnavailable, WhisperCppSTT, parse_whisper_json

FAKE_WHISPER = '''#!{py}
import json, sys
args = sys.argv[1:]
if "FAIL" in open(args[args.index("-f") + 1], "rb").read()[44:50].decode("latin1", "ignore") + " ".join(args):
    sys.stderr.write("boom"); sys.exit(3)
base = args[args.index("-of") + 1]
lang = args[args.index("-l") + 1]
toks = [{{"text": "[_BEG_]", "p": 0.99}}, {{"text": " hash", "p": 0.9}}, {{"text": " table", "p": 0.7}}, {{"text": "[_TT_5]", "p": 0.1}}]
json.dump({{"transcription": [{{"text": " A hash table. (" + lang + ")", "tokens": toks}}]}}, open(base + ".json", "w"))
'''

FAKE_PIPER = '''#!{py}
import math, os, struct, sys, time, wave
args = sys.argv[1:]
out = args[args.index("-d") + 1]
n = 0
for line in sys.stdin:
    words = max(1, len(line.split()))
    rate, secs = 22050, 0.05 * words
    frames = b"".join(struct.pack("<h", int(8000 * math.sin(i / 8))) for i in range(int(rate * secs)))
    path = os.path.join(out, f"{{os.getpid()}}_{{n}}_{{time.time_ns()}}.wav")
    with wave.open(path, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate); w.writeframes(frames)
    n += 1
'''


def make_exe(path: Path, body: str) -> Path:
    path.write_text(body.format(py=sys.executable))
    path.chmod(path.stat().st_mode | stat.S_IEXEC)
    return path


@pytest.fixture()
def fakes(tmp_path):
    models = tmp_path / "models"
    (models / "whisper.cpp").mkdir(parents=True)
    (models / "whisper.cpp" / "ggml-base-q5_1.bin").write_bytes(b"x")
    voice = tmp_path / "voice.onnx"
    voice.write_bytes(b"x")
    cfg = VoiceConfig(provider="local", audio_dir=tmp_path / "audio", models_dir=models, piper_model=voice,
                      whisper_cli=str(make_exe(tmp_path / "whisper-cli", FAKE_WHISPER)), piper_bin=str(make_exe(tmp_path / "piper", FAKE_PIPER)),
                      tts_cache=tmp_path / "cache")
    return cfg


def test_whisper_json_gives_text_and_the_mean_token_probability_without_special_tokens():
    data = {"transcription": [{"text": " Hello there.", "tokens": [{"text": "[_BEG_]", "p": 0.2}, {"text": " Hello", "p": 0.9},
                                                                  {"text": " there", "p": 0.7}, {"text": ".", "p": 0.8}]},
                              {"text": " Bye.", "tokens": [{"text": " Bye", "p": 0.5}]}]}
    text, conf = parse_whisper_json(data)
    assert text == "Hello there. Bye." and conf == pytest.approx((0.9 + 0.7 + 0.8 + 0.5) / 4, abs=0.001)
    assert parse_whisper_json({"transcription": []}) == ("", None)


def test_whisper_adapter_runs_the_cli_with_the_language_and_returns_text_and_confidence(fakes):
    stt = WhisperCppSTT(fakes)
    text, conf = stt.transcribe(audio.tone(1.0, 16000, amp=0.5))
    assert text == "A hash table. (en)" and conf == pytest.approx(0.8, abs=0.001)
    hindi = WhisperCppSTT(VoiceConfig(**{**fakes.__dict__, "whisper_lang": "hi"}))
    assert hindi.transcribe(bytes(32000))[0].endswith("(hi)")


def test_whisper_adapter_reports_a_failing_cli_and_missing_files_clearly(fakes, tmp_path):
    with pytest.raises(ProviderUnavailable, match="whisper-cli failed"):
        WhisperCppSTT(VoiceConfig(**{**fakes.__dict__, "whisper_lang": "FAIL"})).transcribe(bytes(32000))
    with pytest.raises(ProviderUnavailable, match="not found: brew install whisper-cpp"):
        WhisperCppSTT(VoiceConfig(**{**fakes.__dict__, "whisper_cli": "no-such-whisper-binary"}))
    with pytest.raises(ProviderUnavailable, match="fetch_models.py"):
        WhisperCppSTT(VoiceConfig(**{**fakes.__dict__, "models_dir": tmp_path / "empty"}))


def test_piper_runs_as_one_persistent_process_and_returns_exact_audio_per_sentence(fakes):
    tts = PiperTTS(fakes)
    try:
        pcm1, rate = tts.synthesize("Can you explain how a hash table works?")
        pid = tts.pool[0].proc.pid
        pcm2, _ = tts.synthesize("Good.")
        assert rate == 22050 and tts.pool[0].proc.pid == pid, "the same process served both sentences"
        assert len(pcm1) / 2 / rate == pytest.approx(0.05 * 8, abs=0.01) and len(pcm2) / 2 / rate == pytest.approx(0.05, abs=0.01)
    finally:
        tts.close()


def test_piper_is_restarted_if_the_process_dies(fakes):
    tts = PiperTTS(fakes)
    try:
        tts.synthesize("first")
        tts.pool[0].proc.kill()
        tts.pool[0].proc.wait()
        pcm, _ = tts.synthesize("second line here")
        assert len(pcm) > 0 and tts.pool[0].proc.poll() is None
    finally:
        tts.close()


def test_two_piper_processes_serve_concurrent_requests(fakes):
    tts = PiperTTS(VoiceConfig(**{**fakes.__dict__, "piper_procs": 2}))
    results = []
    try:
        threads = [threading.Thread(target=lambda n=n: results.append(tts.synthesize(f"sentence number {n} with some words")[0])) for n in range(6)]
        [t.start() for t in threads]
        [t.join(timeout=30) for t in threads]
        assert len(results) == 6 and all(results)
        assert {p.proc.pid for p in tts.pool if p.proc} and len({p.proc.pid for p in tts.pool}) == 2
    finally:
        tts.close()


def test_cached_voice_renders_each_sentence_once_and_keys_on_the_voice(fakes, tmp_path):
    tts = PiperTTS(fakes)
    try:
        cached = CachedTTS(tts, tmp_path / "c")
        a = cached.synthesize("Hello there.")
        b = cached.synthesize("Hello there.")
        assert a == b and (cached.hits, cached.misses) == (1, 1)
        other = CachedTTS(type("Other", (), {"name": "other-voice", "synthesize": lambda self, s: (b"\0\0" * 10, 16000)})(), tmp_path / "c")
        assert other.synthesize("Hello there.")[1] == 16000, "another voice never gets this voice's audio"
        next(Path(tmp_path / "c").glob("*.wav")).write_bytes(b"corrupt")
        assert CachedTTS(tts, tmp_path / "c").synthesize("Hello there.")[0], "a damaged cache file is rendered again"
    finally:
        tts.close()


def have_real():
    cfg = VoiceConfig.from_env()
    return (shutil.which(cfg.whisper_cli) and (cfg.models_dir / "whisper.cpp" / "ggml-base-q5_1.bin").exists()
            and (shutil.which(cfg.piper_bin) or Path(cfg.piper_bin).exists()) and cfg.piper_model.exists())


@pytest.mark.skipif(not have_real(), reason="needs whisper-cli, Piper and the models (spikes/voice/fetch_models.py)")
def test_real_round_trip_piper_speaks_whisper_hears_it():
    cfg = VoiceConfig.from_env()
    tts, stt = PiperTTS(cfg), WhisperCppSTT(cfg)
    try:
        pcm, rate = tts.synthesize("An index is an extra structure that lets the database find rows without scanning the whole table.")
        text, conf = stt.transcribe(audio.resample(pcm, rate))
        heard = [w for w in ("index", "structure", "database", "rows", "scanning", "table") if w in text.lower()]
        assert len(heard) >= 4 and conf and conf > 0.5, (text, conf)
    finally:
        tts.close()


def test_a_sentence_with_nothing_to_say_is_a_pause_not_a_crash(fakes):
    tts = PiperTTS(fakes)
    try:
        pcm, rate = tts.synthesize("...")
        assert rate == 22050 and 0.2 < len(pcm) / 2 / rate < 0.3
        assert tts.pool[0].proc is None, "Piper was not even started for it"
    finally:
        tts.close()
