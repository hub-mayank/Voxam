"""The voice server with VOICE_PROVIDER=local, using fake whisper-cli/piper executables (see test_voice_local.py)."""
import wave
from array import array

import pytest
from starlette.websockets import WebSocketDisconnect

from app.voice import providers
from harness import build, make_viva
from test_voice_local import FAKE_PIPER, FAKE_WHISPER, make_exe
from test_voice_protocol import connect, started


@pytest.fixture()
def env(tmp_path, monkeypatch):
    models = tmp_path / "models"
    (models / "whisper.cpp").mkdir(parents=True)
    (models / "whisper.cpp" / "ggml-base-q5_1.bin").write_bytes(b"x")
    (tmp_path / "voice.onnx").write_bytes(b"x")
    for key, value in {"VOICE_PROVIDER": "local", "VOICE_MODELS_DIR": str(models), "AUDIO_DIR": str(tmp_path / "audio"),
                       "WHISPER_CLI": str(make_exe(tmp_path / "whisper-cli", FAKE_WHISPER)),
                       "PIPER_BIN": str(make_exe(tmp_path / "piper", FAKE_PIPER)), "PIPER_MODEL": str(tmp_path / "voice.onnx"),
                       "TTS_CACHE": str(tmp_path / "cache"), "VOICE_TIMER_S": "0.2", "VOICE_SILENCE_S": "999"}.items():
        monkeypatch.setenv(key, value)
    providers._LOCAL.clear()
    app, client, clock = build(tmp_path)
    codes = make_viva(client, students=("S1", "S2"))
    yield app, client, clock, codes
    for stt, tts in providers._LOCAL.values():
        tts.close()
    providers._LOCAL.clear()


def test_a_push_to_talk_turn_uses_whisper_for_the_text_and_piper_for_the_voice(env, tmp_path):
    app, client, clock, codes = env
    sid, h, token = started(client, codes)
    c = connect(client, sid, token)
    opener = c.until("ai_turn")
    assert "welcome" in opener["text"].lower()
    c.until("audio_done", turn_idx=0)
    c.until("state", state="listening")
    assert {m["sample_rate"] for m in c.log if m["type"] == "audio"} == {22050}, "audio came from the (fake) Piper voice"
    c.speak(1.0)
    tr = c.until("transcript")
    assert tr["text"] == "A hash table. (en)" and tr["confidence"] == pytest.approx(0.8, abs=0.001)
    assert c.until("ai_turn")["idx"] == 2
    clock.advance(901)
    c.until("ended")
    with wave.open(str(tmp_path / "audio" / f"{sid}.wav")) as w:
        raw = array("h", w.readframes(w.getnframes()))
    assert any(raw[0::2]) and any(raw[1::2])
    cache = list((tmp_path / "cache").glob("*.wav"))
    assert cache, "rendered sentences were cached for the next student"


def test_a_missing_model_is_an_error_message_not_a_crash(env, monkeypatch, tmp_path):
    monkeypatch.setenv("VOICE_MODELS_DIR", str(tmp_path / "nothing-here"))
    providers._LOCAL.clear()
    app, client, clock, codes = env
    sid, h, token = started(client, codes)
    c = connect(client, sid, token)
    err = c.until("error")
    assert err["code"] == "provider_unavailable" and err["retryable"] is False and "fetch_models.py" in err["message"]
    with pytest.raises(WebSocketDisconnect) as e:
        c.until("ready")
    assert e.value.code == 1011
