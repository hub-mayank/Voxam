"""Audio helpers and the two-sided session recorder (no network, no models)."""
import wave
from array import array

import pytest

from app.voice import audio
from app.voice.vad import LevelVad

T0 = 1_000_000.0


def samples(path):
    with wave.open(str(path)) as w:
        assert (w.getnchannels(), w.getframerate(), w.getsampwidth()) == (2, 16000, 2)
        raw = array("h", w.readframes(w.getnframes()))
    return raw[0::2], raw[1::2]


def loud(seconds, rate=16000):
    return audio.tone(seconds, rate, freq=300, amp=0.5)


def test_tone_and_resample_lengths():
    t = audio.tone(1.0, 22050)
    assert len(t) == 22050 * 2 and any(t)
    assert len(audio.resample(t, 22050, 16000)) == pytest.approx(16000 * 2, abs=4)
    assert audio.resample(t, 16000, 16000) is t and audio.resample(b"", 22050) == b""


def test_student_and_ai_land_on_one_timeline_with_silence_between(tmp_path):
    r = audio.SessionRecorder(tmp_path / "s.wav", T0)
    assert r.write_ai(loud(1.0), T0) == (0, 1000)                 # AI speaks 0-1 s
    assert r.write_student(loud(1.0), T0 + 3.0) == (2000, 3000)   # frame ends at 3 s, so it starts at 2 s
    r.close(T0 + 4.0)
    left, right = samples(tmp_path / "s.wav")
    assert len(left) == len(right) == 4 * 16000
    assert any(right[:16000]) and not any(right[16000:]), "AI voice only in its second"
    assert not any(left[:2 * 16000]) and any(left[2 * 16000:3 * 16000]) and not any(left[3 * 16000:])


def test_ai_audio_sent_faster_than_real_time_queues_behind_itself(tmp_path):
    r = audio.SessionRecorder(tmp_path / "s.wav", T0)
    r.write_ai(loud(1.0), T0)
    assert r.write_ai(loud(1.0), T0 + 0.1) == (1000, 2000), "the second chunk starts when the first ends, not on top of it"
    assert r.write_ai(loud(0.5), T0 + 5.0)[0] == 5000, "a later turn starts at its own time"


def test_the_file_is_valid_while_recording_and_a_reconnect_continues_it(tmp_path):
    path = tmp_path / "s.wav"
    r = audio.SessionRecorder(path, T0)
    r.write_student(loud(0.5), T0 + 0.5)
    r.tick(T0 + 1.0)
    with wave.open(str(path)) as w:
        assert w.getnframes() == 16000, "readable mid-session, header up to date"
    r2 = audio.SessionRecorder(path, T0)  # the student reconnects
    assert r2.position_ms("student") == 1000
    r2.write_student(loud(0.5), T0 + 3.0)
    r2.close(T0 + 3.0)
    left, _ = samples(path)
    assert len(left) == 3 * 16000 and not any(left[16000:2 * 16000]), "the gap while disconnected is silence"


def test_close_pads_the_shorter_channel_so_nothing_is_lost(tmp_path):
    r = audio.SessionRecorder(tmp_path / "s.wav", T0)
    r.write_ai(loud(2.0), T0)  # AI audio was queued 2 s ahead of the wall clock
    r.close(T0 + 0.5)
    left, right = samples(tmp_path / "s.wav")
    assert len(left) == len(right) == 2 * 16000 and any(right[-100:])


def test_level_vad_needs_speech_then_the_hangover_of_quiet():
    vad, quiet = LevelVad(hangover_ms=600), bytes(640)
    events = []
    for _ in range(10):
        events += vad.feed(loud(0.02))
    assert events == ["speech_start"]
    for _ in range(29):  # 580 ms of quiet: not yet
        assert vad.feed(quiet) == []
    assert vad.feed(quiet) == ["speech_end"] and not vad.in_speech
