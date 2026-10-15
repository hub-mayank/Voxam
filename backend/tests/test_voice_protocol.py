"""The voice WebSocket (docs/VOICE_PROTOCOL.md) against the real backend in stub mode: the same engine, database and clock as HTTP."""
import json
import wave
from array import array
from uuid import UUID

import pytest
from sqlalchemy import select
from starlette.websockets import WebSocketDisconnect

from app.db import models as m
from app.voice import audio
from harness import RAO, auth, begin, build, db_of, join, make_viva


@pytest.fixture()
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("AUDIO_DIR", str(tmp_path / "audio"))
    monkeypatch.setenv("VOICE_PROVIDER", "stub")
    monkeypatch.setenv("VOICE_TIMER_S", "0.2")
    monkeypatch.setenv("VOICE_SILENCE_S", "999")
    monkeypatch.setenv("VOICE_STT_MS", "10")
    app, client, clock = build(tmp_path)
    codes = make_viva(client, students=("S1", "S2", "S3"))
    return app, client, clock, codes


def started(client, codes, student="S1"):
    sid, headers, body = join(client, codes[student], student_id=student)
    r = client.post(f"/student/sessions/{sid}/consent", headers=headers, json={"accepted": True, "rules_version": body["rules_version"]})
    assert r.status_code == 200
    assert client.post(f"/student/sessions/{sid}/start", headers=headers).status_code == 200
    return sid, headers, body["session_token"]


def loud(seconds):
    return audio.tone(seconds, 16000, freq=300, amp=0.5)


class Conn:
    """A thin client: collects JSON messages and the binary chunks that follow `audio` headers."""
    def __init__(self, ws):
        self.ws, self.log, self.chunks = ws, [], []

    def hello(self, token, mode="push_to_talk", **kw):
        self.ws.send_json({"type": "hello", "protocol": 1, "token": token, "mode": mode, "resume": False, **kw})

    def recv(self):
        msg = self.ws.receive()
        if msg.get("type") == "websocket.close":
            raise WebSocketDisconnect(msg.get("code", 1000))
        if msg.get("bytes") is not None:
            self.chunks.append(msg["bytes"])
            return {"type": "<binary>", "bytes": len(msg["bytes"])}
        data = json.loads(msg["text"])
        self.log.append(data)
        return data

    def until(self, kind, **match):
        while True:
            msg = self.recv()
            if msg["type"] == kind and all(msg.get(k) == v for k, v in match.items()):
                return msg

    def speak(self, seconds=1.0, frame_ms=20):
        pcm = loud(seconds)
        n = frame_ms * 16 * 2
        self.ws.send_json({"type": "ptt_start"})
        for i in range(0, len(pcm), n):
            self.ws.send_bytes(pcm[i:i + n])
        self.ws.send_json({"type": "ptt_end"})

    def types(self):
        return [x["type"] for x in self.log]


def connect(client, sid, token, **kw):
    ctx = client.websocket_connect(f"/student/sessions/{sid}/voice")
    ws = ctx.__enter__()
    c = Conn(ws)
    c.ctx = ctx
    c.hello(token, **kw)
    return c


def test_push_to_talk_viva_loop_stores_the_answer_like_the_http_api(env):
    app, client, clock, codes = env
    sid, h, token = started(client, codes)
    c = connect(client, sid, token)
    ready = c.until("ready")
    assert ready["protocol"] == 1 and ready["status"] == "in_progress" and ready["last_client_seq"] == 0 and ready["max_answer_ms"] == 90000
    opener = c.until("ai_turn")
    assert opener["idx"] == 0 and opener["latency_ms"] is None and "welcome" in opener["text"].lower()
    c.until("audio_done", turn_idx=0)
    c.until("state", state="listening")
    assert c.chunks and all(len(b) % 2 == 0 for b in c.chunks), "audio arrives as PCM16 chunks after their headers"
    c.speak(1.0)
    ep = c.until("endpoint")
    assert ep["reason"] == "ptt"
    tr = c.until("transcript")
    assert tr["seq"] == 1 and tr["text"].startswith("[stub answer 1]") and tr["confidence"] == 0.9
    nxt = c.until("ai_turn")
    assert nxt["idx"] == 2 and nxt["latency_ms"] is not None and nxt["latency_ms"] < 5000 and nxt["text"]
    c.until("audio_done", turn_idx=2)
    st = client.get(f"/student/sessions/{sid}/status", headers=h).json()
    assert st["last_client_seq"] == 1 and st["current_turn"]["idx"] == 2
    with db_of(app) as db:
        mine = db.scalar(select(m.Turn).where(m.Turn.session_id == UUID(sid), m.Turn.role == "student"))
    assert mine.client_seq == 1 and mine.meta == {"stt_confidence": 0.9}
    assert mine.t_start_ms is not None and mine.t_end_ms - mine.t_start_ms == pytest.approx(1000, abs=60)
    c.ctx.__exit__(None, None, None)


def test_bad_token_wrong_session_and_not_started_are_refused(env):
    app, client, clock, codes = env
    sid, h, token = started(client, codes, "S1")
    other, oh, otoken = started(client, codes, "S2")
    with pytest.raises(WebSocketDisconnect) as e:
        c = connect(client, sid, "st_nope")
        c.until("ready")
    assert e.value.code == 4401
    c = connect(client, sid, otoken)
    assert c.until("error")["code"] == "forbidden"
    with pytest.raises(WebSocketDisconnect) as e:
        c.until("ready")
    assert e.value.code == 4403
    sid3, h3, body3 = join(client, codes["S3"], student_id="S3")
    c = connect(client, sid3, body3["session_token"])
    assert c.until("error")["code"] == "invalid_state"


def test_a_too_short_answer_is_no_speech_and_nothing_is_stored(env):
    app, client, clock, codes = env
    sid, h, token = started(client, codes)
    c = connect(client, sid, token)
    c.until("state", state="listening")
    c.speak(0.1)
    err = c.until("error")
    assert (err["code"], err["retryable"]) == ("no_speech", True)
    assert client.get(f"/student/sessions/{sid}/status", headers=h).json()["last_client_seq"] == 0


def test_a_typed_answer_flows_the_same_way_with_no_confidence(env):
    app, client, clock, codes = env
    sid, h, token = started(client, codes)
    c = connect(client, sid, token)
    c.until("state", state="listening")
    c.ws.send_json({"type": "text_answer", "text": "I built a small web app with a database and a React front end."})
    tr = c.until("transcript")
    assert tr["seq"] == 1 and tr["confidence"] is None
    assert c.until("ai_turn")["idx"] == 2
    c.ws.send_json({"type": "text_answer", "text": ""})
    assert c.until("error")["code"] == "bad_message"


def test_reconnect_resumes_without_duplicating_and_the_old_connection_is_replaced(env):
    app, client, clock, codes = env
    sid, h, token = started(client, codes)
    first = connect(client, sid, token)
    first.until("state", state="listening")
    first.speak(0.6)
    first.until("audio_done", turn_idx=2)
    second = connect(client, sid, token, resume=True)
    ready = second.until("ready")
    assert ready["last_client_seq"] == 1 and ready["current_turn"]["idx"] == 2
    assert second.until("ai_turn")["idx"] == 2, "the open question is spoken again on every connect"
    replaced = first.until("error")
    assert replaced["code"] == "replaced"
    with pytest.raises(WebSocketDisconnect) as e:
        first.recv()
    assert e.value.code == 4409
    second.until("state", state="listening")
    second.speak(0.6)
    assert second.until("transcript")["seq"] == 2


def test_speaking_over_the_ai_is_an_interrupt(env):
    app, client, clock, codes = env
    sid, h, token = started(client, codes)
    c = connect(client, sid, token)
    c.until("audio_done", turn_idx=0)  # audio is sent faster than real time: the client is still "playing" it
    c.ws.send_json({"type": "ptt_start"})
    assert c.until("interrupt")["type"] == "interrupt"


def test_hands_free_uses_voice_activity_to_end_the_answer(env):
    app, client, clock, codes = env
    sid, h, token = started(client, codes)
    c = connect(client, sid, token, mode="hands_free")
    c.until("state", state="listening")
    for _ in range(40):
        c.ws.send_bytes(loud(0.02))
    assert c.until("speech_start")["type"] == "speech_start"
    for _ in range(35):
        c.ws.send_bytes(bytes(640))
    assert c.until("endpoint")["reason"] == "silence"
    assert c.until("transcript")["seq"] == 1


def test_one_silence_prompt_per_question(env, monkeypatch):
    monkeypatch.setenv("VOICE_SILENCE_S", "0.3")
    app, client, clock, codes = env
    sid, h, token = started(client, codes)
    c = connect(client, sid, token)
    c.until("audio_done", turn_idx=0)
    prompt = c.until("silence_prompt")
    assert "ready" in prompt["text"].lower()
    c.until("state", state="listening")
    import time
    time.sleep(1.0)
    c.ws.send_json({"type": "ping", "t": 7})
    assert c.until("pong")["t"] == 7
    assert c.types().count("silence_prompt") == 1, "only once per question"


def test_hard_stop_speaks_the_closing_turn_ends_the_session_and_closes(env):
    app, client, clock, codes = env
    sid, h, token = started(client, codes)
    c = connect(client, sid, token)
    c.until("state", state="listening")
    clock.advance(901)
    closing = c.until("ai_turn")
    assert closing["ended"] is True
    ended = c.until("ended")
    assert ended["status"] == "ended"
    assert client.get(f"/student/sessions/{sid}/status", headers=h).json()["status"] == "ended"
    with pytest.raises(WebSocketDisconnect) as e:
        c.recv()
    assert e.value.code == 1000
    with db_of(app) as db:
        assert db.scalar(select(m.Job).where(m.Job.session_id == UUID(sid))).status == "queued", "scoring was queued"


def test_the_recording_has_both_sides_and_the_turn_offsets_point_into_it(env, tmp_path):
    app, client, clock, codes = env
    sid, h, token = started(client, codes)
    c = connect(client, sid, token)
    c.until("state", state="listening")
    c.speak(1.0)
    c.until("audio_done", turn_idx=2)
    clock.advance(901)
    c.until("ended")
    wav = tmp_path / "audio" / f"{sid}.wav"
    with wave.open(str(wav)) as w:
        assert (w.getnchannels(), w.getframerate()) == (2, 16000) and w.getnframes() > 16000
        raw = array("h", w.readframes(w.getnframes()))
    left, right = raw[0::2], raw[1::2]
    assert any(left) and any(right), "student on the left, AI on the right"
    with db_of(app) as db:
        mine = db.scalar(select(m.Turn).where(m.Turn.session_id == UUID(sid), m.Turn.role == "student"))
        s = db.get(m.Session, UUID(sid))
        assert s.audio_uri == f"file://{wav}"
    first, last = mine.t_start_ms * 16, mine.t_end_ms * 16
    assert any(left[first:last]), "the stored offsets cover the student's speech"
    detail = client.get(f"/faculty/sessions/{sid}", headers=RAO).json()
    assert detail["audio"]["available"] and detail["audio"]["duration_ms"] > 1000


def test_bad_json_and_unknown_messages_do_not_break_the_connection(env):
    app, client, clock, codes = env
    sid, h, token = started(client, codes)
    c = connect(client, sid, token)
    c.until("state", state="listening")
    c.ws.send_text("{not json")
    assert c.until("error")["code"] == "bad_message"
    c.ws.send_json({"type": "something_new"})
    c.ws.send_json({"type": "ping", "t": 1})
    assert c.until("pong")["t"] == 1


def test_hands_free_keeps_the_lead_in_from_before_the_detector_was_sure(env):
    """The detector needs ~100 ms of speech before it says "start"; the answer must still begin where the speech did."""
    app, client, clock, codes = env
    sid, h, token = started(client, codes)
    c = connect(client, sid, token, mode="hands_free")
    c.until("audio_done", turn_idx=0)
    c.until("state", state="listening")
    for _ in range(15):
        c.ws.send_bytes(bytes(640))  # 300 ms of quiet
    for _ in range(40):
        c.ws.send_bytes(loud(0.02))  # 800 ms of speech
    for _ in range(40):
        c.ws.send_bytes(bytes(640))  # 800 ms of quiet ends the answer
    c.until("transcript")
    assert c.until("ai_turn")["idx"] == 2, "the answer was stored before the reply"
    with db_of(app) as db:
        mine = db.scalar(select(m.Turn).where(m.Turn.session_id == UUID(sid), m.Turn.role == "student"))
    assert mine.t_start_ms <= 40, f"answer starts at {mine.t_start_ms} ms: the lead-in was kept, not cut at the detection point"
    assert mine.t_end_ms - mine.t_start_ms >= 1100, "lead-in + speech + the hangover are all in the answer"


def test_a_short_noise_while_the_ai_talks_is_not_a_barge_in_but_real_speech_is(env):
    app, client, clock, codes = env
    sid, h, token = started(client, codes)
    c = connect(client, sid, token, mode="hands_free")
    c.until("audio_done", turn_idx=0)  # audio is sent faster than real time, so the client is still "playing" it
    for _ in range(5):
        c.ws.send_bytes(loud(0.02))  # 100 ms: a cough or echo
    c.ws.send_json({"type": "ping", "t": 1})
    c.until("pong")
    assert "interrupt" not in c.types() and "speech_start" not in c.types()
    for _ in range(20):
        c.ws.send_bytes(loud(0.02))  # 400 ms more: somebody is talking
    c.until("interrupt")
    assert c.until("speech_start")["type"] == "speech_start"


# ---------- reply streaming: speak finished sentences while the model is still writing ----------

import time as _time

from app.llm.errors import ProviderError
from app.llm.mock import MockLLM


class StreamingLLM(MockLLM):
    """Phrases a follow-up in pieces with a gap between them, like a slow local model."""
    def __init__(self, pieces, gap=0.15, fail_at=None):
        self.pieces, self.gap, self.fail_at = pieces, gap, fail_at

    def complete_text(self, system, user, max_tokens=120, kind="phrase", on_delta=None):
        for i, piece in enumerate(self.pieces):
            if self.fail_at == i:
                raise ProviderError("model died midway", status="unavailable", retryable=True)
            _time.sleep(self.gap)
            if on_delta:
                on_delta(piece)
        return "".join(self.pieces).strip()


def streaming_env(tmp_path, monkeypatch, llm):
    monkeypatch.setenv("AUDIO_DIR", str(tmp_path / "audio"))
    monkeypatch.setenv("VOICE_PROVIDER", "stub")
    monkeypatch.setenv("VOICE_TIMER_S", "0.2")
    monkeypatch.setenv("VOICE_SILENCE_S", "999")
    app, client, clock = build(tmp_path, llm=lambda spec: llm)
    codes = make_viva(client, students=("S1",))
    return app, client, clock, codes


def reach_a_followup(c, clock):
    """Past the warm-up (a new question, no model), then a short answer that the engine follows up with the model."""
    c.until("state", state="listening")
    clock.advance(70)
    c.ws.send_json({"type": "text_answer", "text": "I built a small web app."})
    c.until("audio_done", turn_idx=2)
    c.ws.send_json({"type": "text_answer", "text": "it stores keys"})


def test_a_followup_is_spoken_sentence_by_sentence_before_the_model_has_finished(tmp_path, monkeypatch):
    app, client, clock, codes = streaming_env(tmp_path, monkeypatch, StreamingLLM(["Good point. ", "What about ", "hash ", "collisions?"]))
    sid, h, token = started(client, codes)
    c = connect(client, sid, token)
    reach_a_followup(c, clock)
    first_audio = c.until("audio", turn_idx=4)
    turn = c.until("ai_turn", idx=4)
    assert turn["text"] == "Good point. What about hash collisions?"
    order = [(m["type"], m.get("turn_idx", m.get("idx"))) for m in c.log]
    assert order.index(("audio", 4)) < order.index(("ai_turn", 4)), "the first sentence's audio went out before the reply was complete"
    assert first_audio["last"] is False
    c.until("audio_done", turn_idx=4)
    assert len([m for m in c.log if m["type"] == "audio" and m["turn_idx"] == 4]) == 2, "sentence one while streaming, the rest after"
    assert turn["latency_ms"] is not None
    st = client.get(f"/student/sessions/{sid}/status", headers=h).json()
    assert st["current_turn"]["text"] == "Good point. What about hash collisions?"


def test_if_the_stream_dies_the_started_sentence_is_cut_and_the_real_reply_is_spoken(tmp_path, monkeypatch):
    app, client, clock, codes = streaming_env(tmp_path, monkeypatch, StreamingLLM(["Alpha beta. ", "gamma delta"], fail_at=1))
    sid, h, token = started(client, codes)
    c = connect(client, sid, token)
    reach_a_followup(c, clock)
    c.until("audio", turn_idx=4)            # "Alpha beta." was already on its way
    c.until("interrupt")                    # then the model failed, so that audio is cancelled
    turn = c.until("ai_turn", idx=4)
    assert "Alpha" not in turn["text"] and turn["text"], "the canned reply replaced it"
    c.until("audio_done", turn_idx=4)
    assert client.get(f"/student/sessions/{sid}/status", headers=h).json()["current_turn"]["text"] == turn["text"]


def test_the_students_speech_language_reaches_the_recogniser_and_the_stored_turn(env, monkeypatch):
    from app.voice.providers import StubSTT
    seen = []
    original = StubSTT.transcribe

    def spy(self, pcm16k, language=None):
        seen.append(language)
        return original(self, pcm16k, language)

    monkeypatch.setattr(StubSTT, "transcribe", spy)
    app, client, clock, codes = env
    sid, h, token = started(client, codes)
    c = connect(client, sid, token, language="auto")
    c.until("ready")
    c.until("state", state="listening")
    c.speak(1.0)
    c.until("transcript")
    c.until("ai_turn", idx=2)
    assert seen == ["auto"]
    with db_of(app) as db:
        mine = db.scalar(select(m.Turn).where(m.Turn.session_id == UUID(sid), m.Turn.role == "student"))
    assert mine.meta == {"stt_confidence": 0.9, "stt_language": "auto"}
    c.ctx.__exit__(None, None, None)


def test_an_unknown_speech_language_is_ignored_not_an_error(env, monkeypatch):
    from app.voice.providers import StubSTT
    seen = []
    original = StubSTT.transcribe
    monkeypatch.setattr(StubSTT, "transcribe", lambda self, pcm, language=None: (seen.append(language), original(self, pcm, language))[1])
    app, client, clock, codes = env
    sid, h, token = started(client, codes, "S2")
    c = connect(client, sid, token, language="klingon")
    c.until("ready")
    c.until("state", state="listening")
    c.speak(1.0)
    c.until("transcript")
    assert seen == [None]
    c.ctx.__exit__(None, None, None)


def test_model_written_sentences_are_never_cached_but_fixed_lines_stay_cacheable(tmp_path, monkeypatch):
    """Dynamic replies carry what the student said; only fixed lines (opener, bank questions, closing) may be reused from the cache."""
    from app.voice.providers import StubTTS
    calls = []
    original = StubTTS.synthesize

    def spy(self, sentence, *, cache=True):
        calls.append((sentence, cache))
        return original(self, sentence, cache=cache)

    monkeypatch.setattr(StubTTS, "synthesize", spy)
    app, client, clock, codes = streaming_env(tmp_path, monkeypatch, StreamingLLM(["Good point. ", "What about ", "hash ", "collisions?"]))
    sid, h, token = started(client, codes)
    c = connect(client, sid, token)
    reach_a_followup(c, clock)
    c.until("audio_done", turn_idx=4)
    dynamic = [cache for sentence, cache in calls if sentence.startswith(("Good point", "What about"))]
    assert dynamic and not any(dynamic), "every model-written sentence is synthesised with cache=False"
    fixed = [cache for sentence, cache in calls if "welcome" in sentence.lower()]
    assert fixed and all(fixed), "the opener is a fixed line and stays cacheable"
    c.ctx.__exit__(None, None, None)
