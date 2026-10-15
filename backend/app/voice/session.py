"""One voice connection: the server side of docs/VOICE_PROTOCOL.md.
The engine (clock, question flow, scoring queue) is the same StudentService the HTTP API uses; this class only moves audio, turns
speech into the `answer` call and turns the reply into audio. It never decides phases, timing or marks (D1)."""
import asyncio
import json
import re
from collections import deque
import logging
import time
from datetime import datetime

from sqlalchemy import select, update

from ..api.errors import ApiError, ErrorCode
from ..api.schemas.student import AnswerRequest
from ..db import models as m
from ..services.secrets_util import hash_token
from ..services.student import StudentService
from . import audio
from .config import VoiceConfig
from .providers import make_providers, split_sentences
from .vad import LevelVad, make_vad

log = logging.getLogger("aiviva.voice")
SENTENCE = re.compile(r"(?s)^\s*(.+?[.!?]['\")\]]?)\s+")  # a finished sentence: text up to ./!/? followed by a space
MIN_ANSWER_S = 0.3
TICK_S = 0.25
SILENCE_LINE = "Take your time. Whenever you are ready, go ahead and answer."
REPEAT_LINE = "Sorry, I did not catch that. Could you say it again?"
CONNECTIONS: dict = {}  # session id -> live VoiceSession (one connection per session)


class Closed(Exception):
    pass


class VoiceSession:
    def __init__(self, ws, sid, app_state, cfg: VoiceConfig = None, providers=None):
        self.ws, self.sid, self.app, self.cfg = ws, sid, app_state, cfg or VoiceConfig.from_env()
        self.stt, self.tts = providers or (None, None)  # made on connect, so a missing model is an error message, not a crash
        self.state, self.mode, self.language = "listening", "push_to_talk", None
        self.recorder = None
        self.deadline = None
        self.last_seq = 0
        self.max_answer_ms = 90_000
        self.utt, self.utt_start, self.utt_end = bytearray(), None, None
        self.ptt_active = False
        self.vad = LevelVad()
        self.preroll = deque()  # (frame, start_ms, end_ms) of the latest hands-free audio, so a start is never clipped
        self.playing_until = 0.0
        self.current_idx = self.prompted_idx = -1
        self.muted = self.closing = self.finished = self.warned = False
        self.turn_task = self.timer = None
        self.interrupted = asyncio.Event()
        self.t_stop = None
        self.last_activity = time.time()

    # ---------- plumbing ----------

    def now(self) -> datetime:
        return self.app.now()

    def ts(self) -> float:
        return self.now().timestamp()

    async def send(self, **msg):
        await self.ws.send_json(msg)

    async def set_state(self, state: str):
        if state != self.state:
            self.state = state
            await self.send(type="state", state=state)

    def _run(self, fn):
        """Run a blocking engine/database call off the event loop, with its own database session."""
        def call():
            with self.app.sessionmaker() as db:
                svc = StudentService(db, self.app.settings, self.app.now, self.app.llm_factory, ip_throttle=getattr(self.app, "ip_throttle", None))
                return fn(svc, db)
        return asyncio.to_thread(call)

    async def _status(self):
        return await self._run(lambda svc, db: svc.status(self.sid))

    async def error(self, code: str, message: str, retryable: bool, close: int = None):
        await self.send(type="error", code=code, message=message, retryable=retryable)
        if close is not None:
            await self.ws.close(code=close)
            raise Closed

    def begin_turn(self, coro):
        """Run one answer-and-reply cycle in the background so the receive loop keeps reading (ping, mute, barge-in)."""
        self.turn_task = asyncio.create_task(self._guard(coro))

    async def _guard(self, coro):
        try:
            await coro
        except Closed:
            pass
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("voice turn failed: %s", self.sid)
            try:
                await self.error("provider_unavailable", "Something went wrong on the server; please try again.", True)
                await self.set_state("listening")
            except Exception:
                pass

    # ---------- connection ----------

    async def run(self):
        await self.ws.accept()
        try:
            hello = await asyncio.wait_for(self.ws.receive_json(), timeout=5)
        except Exception:
            await self.ws.close(code=4401)
            return
        try:
            await self.open(hello)
            await self.loop()
        except Closed:
            pass
        except Exception:
            log.exception("voice session crashed: %s", self.sid)
            try:
                await self.ws.close(code=1011)
            except Exception:
                pass
        finally:
            await self.cleanup()

    async def open(self, hello):
        if not isinstance(hello, dict) or hello.get("type") != "hello" or hello.get("protocol") != 1 or not isinstance(hello.get("token"), str):
            await self.error("bad_message", "The first message must be hello with protocol 1 and a token.", False, 4401)
        token_hash = hash_token(hello["token"])
        owner = await self._run(lambda svc, db: db.scalar(select(m.Session.id).where(m.Session.token_hash == token_hash)))
        if owner is None:
            await self.error("unauthorized", "Unknown or replaced session token.", False, 4401)
        if owner != self.sid:
            await self.error("forbidden", "This token belongs to another session.", False, 4403)
        self.mode = hello.get("mode") if hello.get("mode") in ("push_to_talk", "hands_free") else "push_to_talk"
        self.language = hello.get("language") if hello.get("language") in ("en", "hi", "auto") else None  # speech language, per student
        st = await self._status()
        if st.status.value in ("created", "consented"):
            await self.error("invalid_state", "The viva has not started: call start first.", False, 4400)
        if st.status.value != "in_progress":
            await self.error("session_ended", "The viva is over.", False, 1000)
        if self.stt is None:
            try:
                self.stt, self.tts = await asyncio.to_thread(make_providers, self.cfg)
            except Exception as e:
                log.error("voice providers unavailable: %s", e)
                await self.error("provider_unavailable", f"Speech providers are not available: {e}", False, 1011)
        if self.mode == "hands_free":
            self.vad = await asyncio.to_thread(make_vad, self.cfg.vad, self.cfg.hangover_ms)
        old = CONNECTIONS.get(self.sid)
        if old is not None and old is not self:
            await old.kicked()
        CONNECTIONS[self.sid] = self
        self.deadline, self.last_seq = st.deadline_at, st.last_client_seq
        config = await self._run(lambda svc, db: svc._viva(svc._session(self.sid)).config)
        self.max_answer_ms = int(config.get("answer_cap_seconds", 90)) * 1000
        path = self.cfg.audio_dir / f"{self.sid}.wav"
        self.recorder = audio.SessionRecorder(path, st.started_at.timestamp())

        def remember_recording(svc, db):
            db.execute(update(m.Session).where(m.Session.id == self.sid, m.Session.audio_uri.is_(None)).values(audio_uri=f"file://{path}"))
            db.commit()
        await self._run(remember_recording)
        turn = st.current_turn
        await self.send(type="ready", protocol=1, session_id=str(self.sid), status=st.status.value, remaining_ms=st.remaining_ms,
                        server_now=st.model_dump(mode="json")["server_now"], last_client_seq=self.last_seq,
                        current_turn=turn.model_dump(mode="json") if turn else None, max_answer_ms=self.max_answer_ms)
        self.timer = asyncio.create_task(self.timer_loop())
        if turn and not turn.ended:
            self.begin_turn(self.speak_turn(turn.idx, turn.text, turn.phase, False, st.remaining_ms, None))

    async def kicked(self):
        self.finished = self.closing = True
        try:
            await self.send(type="error", code="replaced", message="A newer connection took over this session.", retryable=False)
            await self.ws.close(code=4409)
        except Exception:
            pass

    async def cleanup(self):
        for task in (self.timer, self.turn_task):
            if task and not task.done() and task is not asyncio.current_task():
                task.cancel()
        if self.recorder:
            try:
                self.recorder.close(self.ts())
            except Exception:
                log.exception("closing the recording failed: %s", self.sid)
        if CONNECTIONS.get(self.sid) is self:
            del CONNECTIONS[self.sid]

    # ---------- receive loop ----------

    async def loop(self):
        while not self.finished:
            msg = await self.ws.receive()
            if msg.get("type") == "websocket.disconnect":
                return
            if msg.get("bytes") is not None:
                await self.on_audio(msg["bytes"])
            elif msg.get("text") is not None:
                await self.on_text(msg["text"])

    async def on_text(self, raw: str):
        try:
            msg = json.loads(raw)
            kind = msg["type"]
        except (ValueError, KeyError, TypeError):
            await self.error("bad_message", "Not a JSON message with a type.", True)
            return
        if kind == "ping":
            await self.send(type="pong", t=msg.get("t"))
        elif kind == "ptt_start" and self.mode == "push_to_talk" and self.state != "thinking":
            await self.barge_in()
            self.reset_utterance()
            self.ptt_active = True
        elif kind == "ptt_end" and self.ptt_active:
            self.ptt_active = False
            await self.end_utterance("ptt")
        elif kind == "end_turn" and self.mode == "hands_free" and self.utt:
            await self.end_utterance("button")
        elif kind == "text_answer" and self.state != "thinking":
            text = msg.get("text")
            if not isinstance(text, str) or not 1 <= len(text.strip()) <= 4000:
                await self.error("bad_message", "text_answer needs 1-4000 characters.", True)
                return
            await self.barge_in()
            self.t_stop = time.perf_counter()
            await self.set_state("thinking")
            self.begin_turn(self.handle_answer(text.strip(), None, None, None, 0, self.t_stop))
        elif kind == "mute":
            self.muted = True
        elif kind == "unmute":
            self.muted, self.last_activity = False, time.time()

    def reset_utterance(self):
        self.utt, self.utt_start, self.utt_end = bytearray(), None, None
        self.last_activity = time.time()

    async def on_audio(self, frame: bytes):
        if self.state == "thinking" or self.recorder is None or self.muted:
            return
        if self.mode == "push_to_talk":
            if not self.ptt_active:
                return
            start, end = self.recorder.write_student(frame, self.ts())
            self.collect(frame, start, end)
        else:
            start, end = self.recorder.write_student(frame, self.ts())
            # speech must last longer to count as a barge-in while our own audio may still be playing (echo, a cough)
            self.vad.set_start_ms(320 if time.time() < self.playing_until else 96)
            self.preroll.append((frame, start, end))
            keep = (self.vad.start_need + self.cfg.preroll_ms) // 20 + 1  # the detection delay plus the lead-in we promise
            while len(self.preroll) > keep:
                self.preroll.popleft()
            events = self.vad.feed(frame)
            if "speech_start" in events:
                await self.barge_in()
                self.reset_utterance()
                for f, s, e in self.preroll:  # includes this frame and ~300 ms before the detector was sure
                    self.collect(f, s, e)
                await self.send(type="speech_start", t_ms=self.utt_start)
            elif self.vad.in_speech or "speech_end" in events:
                self.collect(frame, start, end)
            if "speech_end" in events:
                await self.end_utterance("silence")
                return
        if len(self.utt) / 2 / audio.RATE * 1000 >= self.max_answer_ms:
            self.ptt_active = False
            await self.end_utterance("cap")

    def collect(self, frame: bytes, start: int, end: int):
        self.utt += frame
        self.utt_start = start if self.utt_start is None else self.utt_start
        self.utt_end = end
        self.last_activity = time.time()

    async def barge_in(self):
        """The student speaks (or types) while our audio may still be playing on their side."""
        if time.time() < self.playing_until:
            self.interrupted.set()
            self.playing_until = 0.0
            await self.send(type="interrupt")

    async def end_utterance(self, reason: str):
        pcm, start, end = bytes(self.utt), self.utt_start, self.utt_end
        self.reset_utterance()
        self.vad.reset()
        self.preroll.clear()
        if not pcm:
            return
        self.t_stop = time.perf_counter()
        await self.send(type="endpoint", t_ms=end, reason=reason)
        if audio.duration_s(pcm, audio.RATE) < MIN_ANSWER_S:
            await self.error("no_speech", "That was too short to be an answer.", True)
            return
        await self.set_state("thinking")
        self.begin_turn(self.process_audio(pcm, start, end, self.t_stop))

    # ---------- answer, reply ----------

    async def process_audio(self, pcm: bytes, start, end, t_stop):
        t0 = time.perf_counter()
        text, confidence = await asyncio.to_thread(self.stt.transcribe, pcm, self.language)
        stt_ms = int((time.perf_counter() - t0) * 1000)
        if not text.strip():
            await self.error("no_speech", "Nothing recognisable in that answer.", True)
            await self.set_state("listening")
            await self.say(REPEAT_LINE)
            return
        await self.handle_answer(text.strip(), confidence, start, end, stt_ms, t_stop)

    async def handle_answer(self, text, confidence, start, end, stt_ms, t_stop):
        text = text[:4000]
        self.interrupted.clear()  # a barge-in that started this answer has done its job: the reply may be spoken again
        seq = self.last_seq + 1
        await self.send(type="transcript", seq=seq, text=text, confidence=confidence, stt_ms=stt_ms)
        resp = None
        loop = asyncio.get_running_loop()
        pieces: asyncio.Queue = asyncio.Queue()
        streamer = asyncio.create_task(self.stream_reply(pieces))  # speaks finished sentences while the model is still writing
        try:
            for attempt in range(3):
                try:
                    body = AnswerRequest(text=text, client_seq=seq, t_start_ms=start, t_end_ms=end)
                    resp = await self._run(lambda svc, db: svc.answer(
                        self.sid, body, stt_confidence=confidence, stt_language=self.language,
                        on_phrase_delta=lambda piece: loop.call_soon_threadsafe(pieces.put_nowait, piece)))
                    break
                except ApiError as e:
                    if e.code in (ErrorCode.deadline_passed, ErrorCode.session_ended):
                        await self.finish()
                        return
                    if e.code == ErrorCode.bad_client_seq and attempt < 2:
                        seq = (await self._status()).last_client_seq + 1
                        continue
                    if e.code == ErrorCode.provider_unavailable and attempt < 2:
                        await asyncio.sleep(0.5)
                        continue
                    await self.error(e.code.value, e.message, e.code == ErrorCode.provider_unavailable)
                    await self.set_state("listening")
                    return
        finally:
            pieces.put_nowait(None)
            streamed = await streamer
        self.last_seq = seq
        turn = resp.turn
        await self.finish_reply(turn, resp.remaining_ms, t_stop, streamed)
        if turn.ended:
            await self.finish(spoken=True)

    async def stream_reply(self, pieces: asyncio.Queue) -> dict:
        """Consumes the model's text as it arrives and speaks each finished sentence at once. -> what was spoken, the unfinished tail,
        and when the first audio went out. Nothing is sent for a reply that is not model-phrased (bank question, closing line)."""
        buf, spoken, first_at = "", [], None
        idx = self.current_idx + 2  # the answer is turn current_idx + 1, the reply the one after
        while True:
            piece = await pieces.get()
            if piece is None:
                break
            buf += piece
            while not self.interrupted.is_set():
                m = SENTENCE.match(buf)
                if not m:
                    break
                sentence, buf = m.group(1).strip(), buf[m.end():]
                if first_at is None:
                    self.interrupted.clear()
                    await self.set_state("speaking")
                    first_at = time.perf_counter()
                await self.send_sentence(sentence, idx, last=False, cache=False)  # model-written text: never reusable, so never cached
                spoken.append(sentence)
        return {"spoken": " ".join(spoken), "tail": buf, "first_at": first_at}

    async def send_sentence(self, sentence: str, turn_idx: int, last: bool, cache: bool = True):
        try:
            pcm, rate = await asyncio.to_thread(self.tts.synthesize, sentence, cache=cache)
        except Exception as e:  # the text still reaches the student; only this sentence is silent
            log.error("tts failed for one sentence: %s", e)
            await self.error("provider_unavailable", "Speech synthesis failed for part of this turn.", True)
            pcm, rate = bytes(2 * 22_050 // 4), 22_050
        if self.interrupted.is_set():
            return
        await self.send(type="audio", turn_idx=turn_idx, sample_rate=rate, format="pcm_s16le", bytes=len(pcm), last=last)
        await self.ws.send_bytes(pcm)
        self.recorder.write_ai(audio.resample(pcm, rate), self.ts())
        self.playing_until = max(self.playing_until, time.time()) + audio.duration_s(pcm, rate)

    async def finish_reply(self, turn, remaining_ms: int, t_stop, streamed: dict):
        """Say the reply. If sentences were already spoken while it was being written and they are the start of the final text, only the
        rest is spoken now; if the final text differs (the provider failed midway and a canned line replaced it), stop and say it all."""
        said, final = " ".join(streamed["spoken"].split()), " ".join(turn.text.split())
        if streamed["first_at"] is None or turn.ended:  # a bank question, the closing line or a canned reply: fixed text, cacheable
            await self.speak_turn(turn.idx, turn.text, turn.phase, turn.ended, remaining_ms, t_stop)
            return
        if not final.startswith(said):
            await self.send(type="interrupt")
            self.playing_until = 0.0
            await self.speak_turn(turn.idx, turn.text, turn.phase, turn.ended, remaining_ms, t_stop, cache=False)
            return
        latency = None if t_stop is None else int((streamed["first_at"] - t_stop) * 1000)
        self.current_idx = turn.idx
        await self.send(type="ai_turn", idx=turn.idx, text=turn.text, phase=turn.phase, ended=turn.ended, remaining_ms=remaining_ms, latency_ms=latency)
        rest = final[len(said):].strip()
        if rest and not self.interrupted.is_set():
            await self.stream_audio(rest, turn.idx, cache=False)
        else:
            await self.send(type="audio_done", turn_idx=turn.idx)
        await self.set_state("listening")
        self.last_activity = time.time()

    async def stream_audio(self, text: str, turn_idx: int, on_first=None, cache: bool = True):
        """Synthesize `text` sentence by sentence and send each chunk; stops at once after a barge-in."""
        sentences = split_sentences(text)
        for i, sentence in enumerate(sentences):
            try:
                pcm, rate = await asyncio.to_thread(self.tts.synthesize, sentence, cache=cache)
            except Exception as e:  # the text still reaches the student; only this sentence is silent
                log.error("tts failed for one sentence: %s", e)
                await self.error("provider_unavailable", "Speech synthesis failed for part of this turn.", True)
                pcm, rate = bytes(2 * 22_050 // 4), 22_050
            if on_first and i == 0:
                await on_first()
            if self.interrupted.is_set():
                break
            await self.send(type="audio", turn_idx=turn_idx, sample_rate=rate, format="pcm_s16le", bytes=len(pcm), last=i == len(sentences) - 1)
            await self.ws.send_bytes(pcm)
            self.recorder.write_ai(audio.resample(pcm, rate), self.ts())
            self.playing_until = max(self.playing_until, time.time()) + audio.duration_s(pcm, rate)
        await self.send(type="audio_done", turn_idx=turn_idx)

    async def speak_turn(self, idx, text, phase, ended, remaining_ms, t_stop, cache: bool = True):
        self.current_idx = idx
        self.interrupted.clear()
        await self.set_state("speaking")

        async def announce():  # sent when the first audio chunk is ready, so latency_ms covers speech recognition, engine and TTS
            latency = None if t_stop is None else int((time.perf_counter() - t_stop) * 1000)
            await self.send(type="ai_turn", idx=idx, text=text, phase=phase, ended=ended, remaining_ms=remaining_ms, latency_ms=latency)
        await self.stream_audio(text, idx, announce, cache=cache)
        if not ended:
            await self.set_state("listening")
            self.last_activity = time.time()

    async def say(self, line: str):
        """A short spoken prompt that is not a stored turn (silence, please repeat)."""
        self.interrupted.clear()
        await self.send(type="silence_prompt", text=line)
        await self.set_state("speaking")
        await self.stream_audio(line, self.current_idx)
        await self.set_state("listening")
        self.last_activity = time.time()

    async def finish(self, spoken: bool = False):
        """The viva is over: say the closing turn (unless it was just spoken), tell the client, close."""
        if self.closing and not spoken:
            return
        self.closing = True
        st = await self._status()
        turn = st.current_turn
        if not spoken and turn is not None:
            await self.speak_turn(turn.idx, turn.text, turn.phase, True, 0, None)
        await self.set_state("ended")
        await self.send(type="ended", status=st.status.value, text=turn.text if turn else "")
        self.finished = True
        await self.ws.close(code=1000)

    # ---------- clock ----------

    async def timer_loop(self):
        last_timer = 0.0
        while not self.finished and not self.closing:
            await asyncio.sleep(TICK_S)
            now = self.now()
            remaining = int((self.deadline - now).total_seconds() * 1000)
            self.recorder.tick(now.timestamp())
            if remaining <= 0:
                await self.finish()
                return
            if time.time() - last_timer >= self.cfg.timer_s:
                last_timer = time.time()
                await self.send(type="timer", remaining_ms=remaining, server_now=now.strftime("%Y-%m-%dT%H:%M:%SZ"))
            if remaining <= self.cfg.warning_ms and not self.warned:
                self.warned = True
                await self.send(type="time_warning", remaining_ms=remaining)
            quiet = time.time() - max(self.last_activity, self.playing_until)
            if (self.state == "listening" and not self.ptt_active and not self.utt and not self.muted
                    and quiet >= self.cfg.silence_s and self.prompted_idx != self.current_idx):
                self.prompted_idx = self.current_idx
                self.begin_turn(self.say(SILENCE_LINE))
