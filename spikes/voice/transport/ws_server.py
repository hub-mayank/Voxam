"""Option (a): a custom FastAPI WebSocket voice endpoint. The smallest thing that does the whole loop:
   browser/client --PCM16 16 kHz frames--> server: Silero VAD (speech start, endpoint, barge-in) -> faster-whisper -> reply -> Piper -> PCM back
Protocol
  client -> server  binary: PCM int16 little-endian, 16 kHz mono, any frame size (the browser worklet sends 20 ms = 640 bytes)
  server -> client  text JSON events: speech_start, endpoint, transcript, reply, audio (header for the binary chunk that follows),
                    audio_done, interrupt (barge-in: the student spoke while the AI was talking, so stop playing)
The reply here is a canned echo: the point is the transport. In the real system the reply comes from POST .../answer (brain.py).
Run: python -m uvicorn ws_server:app --port 8801   (from this folder, venv active)"""
import asyncio
import json
import os
import sys
import time
from pathlib import Path

import numpy as np
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from pysilero_vad import SileroVoiceActivityDetector

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from stt_fw import FasterWhisper  # noqa: E402
from tts_engines import Piper  # noqa: E402

FRAME_BYTES = 1024            # 512 samples = 32 ms, what the VAD requires
HANGOVER_FRAMES = 19          # 19 x 32 ms = 608 ms of silence ends the turn
START_FRAMES = 3              # 3 x 32 ms of speech before we say the student started (ignores clicks)
STT = FasterWhisper(os.environ.get("STT_SIZE", "base"))
TTS = Piper("en_US-lessac-medium")
STT.transcribe(np.zeros(16000, dtype="float32"))
app = FastAPI()


@app.get("/probe")
def probe():
    return FileResponse(Path(__file__).with_name("probe.html"))


@app.get("/sample.wav")
def sample():
    return FileResponse(Path(__file__).resolve().parents[1] / "data" / "synth" / "t11.wav")


async def speak(ws: WebSocket, text: str, interrupted: asyncio.Event, playing: dict):
    """Stream the reply as sentence chunks; stop at once if the student barges in. Audio is sent faster than real time, so the
    server tracks `playing["until"]`: the wall-clock moment the client will have finished playing everything sent so far.
    The student is barging in whenever they speak before that moment, not only while this task is still sending."""
    for chunk in await asyncio.to_thread(lambda: list(TTS.voice.synthesize(text))):
        if interrupted.is_set():
            return
        pcm = (chunk.audio_float_array * 32767).astype("<i2").tobytes()
        playing["until"] = max(playing["until"], time.time()) + len(chunk.audio_float_array) / chunk.sample_rate
        await ws.send_text(json.dumps({"type": "audio", "sample_rate": chunk.sample_rate, "bytes": len(pcm), "t": time.time()}))
        await ws.send_bytes(pcm)
    await ws.send_text(json.dumps({"type": "audio_done", "t": time.time()}))


@app.websocket("/voice")
async def voice(ws: WebSocket):
    await ws.accept()
    vad = SileroVoiceActivityDetector()
    buf, utterance = b"", []
    speech_run, silence_run, in_speech = 0, 0, False
    speaking: asyncio.Task | None = None
    interrupted = asyncio.Event()
    playing = {"until": 0.0}
    frames_in = 0
    try:
        while True:
            msg = await ws.receive()
            if msg.get("type") == "websocket.disconnect":
                break
            if msg.get("text"):
                continue
            buf += msg["bytes"]
            while len(buf) >= FRAME_BYTES:
                frame, buf = buf[:FRAME_BYTES], buf[FRAME_BYTES:]
                frames_in += 1
                is_speech = vad(frame) >= 0.5
                if is_speech:
                    speech_run, silence_run = speech_run + 1, 0
                else:
                    silence_run += 1
                    speech_run = 0
                if is_speech and not in_speech and speech_run >= START_FRAMES:
                    in_speech = True
                    if time.time() < playing["until"]:  # barge-in: the client is still playing our audio
                        interrupted.set()
                        playing["until"] = 0.0
                        await ws.send_text(json.dumps({"type": "interrupt", "t": time.time()}))
                    await ws.send_text(json.dumps({"type": "speech_start", "t": time.time()}))
                if in_speech or is_speech:
                    utterance.append(frame)
                if in_speech and silence_run >= HANGOVER_FRAMES:
                    in_speech = False
                    t_end = time.time()
                    audio = np.frombuffer(b"".join(utterance), dtype="<i2").astype("float32") / 32768
                    utterance = []
                    await ws.send_text(json.dumps({"type": "endpoint", "t": t_end, "audio_s": len(audio) / 16000}))
                    t0 = time.perf_counter()
                    text, _ = await asyncio.to_thread(STT.transcribe, audio)
                    await ws.send_text(json.dumps({"type": "transcript", "text": text, "stt_s": time.perf_counter() - t0, "t": time.time()}))
                    reply = f"I heard you say: {text[:60]}."
                    await ws.send_text(json.dumps({"type": "reply", "text": reply, "t": time.time()}))
                    interrupted = asyncio.Event()
                    speaking = asyncio.create_task(speak(ws, reply, interrupted, playing))
    except WebSocketDisconnect:
        pass
    finally:
        if speaking and not speaking.done():
            speaking.cancel()
