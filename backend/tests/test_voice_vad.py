"""Hands-free end-of-speech detection: the Silero detector's rules (with an injected probability function), the session's pre-roll and
barge-in guard, and one run of the real model where the package and Piper are available."""
import shutil
from pathlib import Path

import pytest

from app.voice import audio
from app.voice.config import VoiceConfig
from app.voice.vad import LevelVad, SileroVad, make_vad

CHUNK = bytes(1024)  # one 32 ms Silero chunk


def feed_probs(vad, probs):
    """One 32 ms chunk per probability. -> list of (index, event)."""
    out = []
    for i, _ in enumerate(probs):
        for e in vad.feed(CHUNK):
            out.append((i, e))
    return out


def scripted(probs):
    it = iter(probs)
    return lambda chunk: next(it)


def test_silero_rules_start_after_enough_speech_and_end_after_the_hangover():
    probs = [0.1] * 5 + [0.9] * 10 + [0.1] * 25
    vad = SileroVad(hangover_ms=600, start_ms=96, prob_fn=scripted(probs))
    events = feed_probs(vad, probs)
    assert events[0] == (7, "speech_start"), "3 chunks of 32 ms = 96 ms of speech"
    assert events[1] == (15 + 19 - 1, "speech_end"), "ceil(600 / 32) = 19 quiet chunks after the last speech chunk"
    assert len(events) == 2 and not vad.in_speech


def test_a_short_blip_is_not_speech_and_a_short_pause_does_not_end_the_answer():
    probs = [0.9, 0.9] + [0.1] * 10 + [0.9] * 6 + [0.1] * 8 + [0.9] * 6 + [0.1] * 25
    vad = SileroVad(hangover_ms=600, start_ms=96, prob_fn=scripted(probs))
    names = [e for _, e in feed_probs(vad, probs)]
    assert names == ["speech_start", "speech_end"], "two chunks never start; the 256 ms pause inside the answer is bridged"


def test_the_start_threshold_can_be_raised_for_barge_in_and_frames_of_any_size_are_buffered():
    probs = [0.9] * 5
    vad = SileroVad(start_ms=320, prob_fn=scripted(probs + [0.9] * 10))
    assert feed_probs(vad, probs) == [], "5 x 32 ms = 160 ms is below a 320 ms barge-in threshold"
    vad.set_start_ms(96)
    frames = [bytes(640)] * 5  # 5 x 20 ms client frames = 3200 bytes = 3 whole chunks + a remainder
    seen = [e for f in frames for e in vad.feed(f)]
    assert seen == ["speech_start"] and len(vad._buf) == 128


def test_reset_clears_the_state_between_answers():
    vad = SileroVad(prob_fn=scripted([0.9] * 10))
    feed_probs(vad, [0.9] * 5)
    assert vad.in_speech
    vad.reset()
    assert not vad.in_speech and vad._buf == b"" and vad.loud_ms == 0


def test_make_vad_picks_the_requested_detector_and_falls_back_without_the_package(monkeypatch):
    assert isinstance(make_vad("level", 600), LevelVad)
    import builtins
    real_import = builtins.__import__

    def no_silero(name, *a, **k):
        if name == "pysilero_vad":
            raise ImportError("not installed")
        return real_import(name, *a, **k)
    monkeypatch.setattr(builtins, "__import__", no_silero)
    assert isinstance(make_vad("silero", 600), LevelVad)


def test_config_defaults_follow_the_provider():
    assert VoiceConfig.from_env({"VOICE_PROVIDER": "stub"}).vad == "level"
    assert VoiceConfig.from_env({"VOICE_PROVIDER": "local"}).vad == "silero"
    cfg = VoiceConfig.from_env({"VOICE_PROVIDER": "local", "VOICE_VAD": "level", "VOICE_HANGOVER_MS": "800", "VOICE_PREROLL_MS": "200"})
    assert (cfg.vad, cfg.hangover_ms, cfg.preroll_ms) == ("level", 800, 200)


def have_real_vad_and_voice():
    try:
        import pysilero_vad  # noqa: F401
    except ImportError:
        return False
    cfg = VoiceConfig.from_env()
    return bool(shutil.which(cfg.piper_bin) or Path(cfg.piper_bin).exists()) and cfg.piper_model.exists()


@pytest.mark.skipif(not have_real_vad_and_voice(), reason="needs pysilero-vad, Piper and the voice model")
def test_real_silero_hears_synthetic_speech_in_20ms_frames_and_ends_it_after_the_hangover():
    from app.voice.local import PiperTTS
    cfg = VoiceConfig.from_env()
    tts = PiperTTS(cfg)
    try:
        pcm, rate = tts.synthesize("An index is an extra structure that lets the database find rows without scanning the whole table.")
    finally:
        tts.close()
    speech = audio.resample(pcm, rate)
    stream = bytes(16000 * 2) + speech + bytes(16000 * 2)  # 1 s quiet, the sentence, 1 s quiet
    vad = SileroVad(hangover_ms=600)
    events = []
    for i in range(0, len(stream), 640):
        events += [(i / 32000, e) for e in vad.feed(stream[i:i + 640])]
    names = [e for _, e in events]
    assert names == ["speech_start", "speech_end"], events
    start_s, end_s = events[0][0], events[1][0]
    assert 0.9 < start_s < 1.4, "speech starts about where it does in the audio"
    speech_end_s = 1 + len(speech) / 32000
    assert speech_end_s + 0.4 < end_s < speech_end_s + 1.2, "the end fires about one hangover after the last word"
