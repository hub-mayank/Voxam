"""A scripted student that completes a viva over the voice WebSocket (docs/VOICE_PROTOCOL.md): join, consent, start, then answer by
"speaking" (a loud tone) in push-to-talk or hands-free mode until the viva ends. Prints per-turn latency and checks message order.
Against VOICE_PROVIDER=stub it proves the transport and the engine hand-off, NOT speech recognition or speech quality.
Usage: python scripts/voice_bot.py --viva local-dsa --student LOCAL01 --code XXXX-XXXX [--base http://localhost:8000]
           [--mode push_to_talk|hands_free] [--answers 60] [--answer-seconds 1.5] [--out results/voice_bot_stub.csv]"""
import argparse
import asyncio
import csv
import json
import statistics
import sys
import time
from pathlib import Path

import httpx
import websockets

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.voice import audio  # noqa: E402


async def stream(ws, seconds: float, loud: bool, pace: float, pcm: bytes = None):
    """Send `seconds` of audio in 20 ms frames; pace 1.0 = real time (the recording's timeline stays realistic), 0 = as fast as possible."""
    for f in frames(seconds, loud, pcm=pcm):
        await ws.send(f)
        if pace:
            await asyncio.sleep(0.02 / pace)


def frames(seconds: float, loud: bool = True, ms: int = 20, pcm: bytes = None):
    if pcm is None:
        pcm = audio.tone(seconds, 16000, freq=300, amp=0.5) if loud else bytes(int(seconds * 16000) * 2)
    step = ms * 16 * 2
    return [pcm[i:i + step] for i in range(0, len(pcm), step)]


def load_speech(folder: str) -> list:
    """16 kHz mono PCM16 of every .wav in the folder, sorted by name (real or synthetic speech for a real STT)."""
    import wave
    clips = []
    for path in sorted(Path(folder).glob("*.wav")):
        with wave.open(str(path)) as w:
            pcm = w.readframes(w.getnframes())
            if w.getnchannels() == 2:
                pcm = b"".join(pcm[i:i + 2] for i in range(0, len(pcm), 4))
            clips.append(audio.resample(pcm, w.getframerate(), 16000))
    if not clips:
        raise SystemExit(f"no .wav files in {folder}")
    return clips


async def run(a) -> dict:
    async with httpx.AsyncClient(base_url=a.base, timeout=30) as http:
        j = (await http.post("/student/join", json={"viva_id": a.viva, "student_id": a.student, "access_code": a.code})).json()
        headers = {"Authorization": f"Bearer {j['session_token']}"}
        sid = j["session_id"]
        await http.post(f"/student/sessions/{sid}/consent", headers=headers, json={"accepted": True, "rules_version": j["rules_version"]})
        started = await http.post(f"/student/sessions/{sid}/start", headers=headers)
        assert started.status_code == 200, started.text
    uri = a.base.replace("http", "ws", 1) + f"/student/sessions/{sid}/voice"
    rows, order_errors = [], []
    answers = 0
    sent_at = None
    waiting = False
    seen_ready = False
    speech = load_speech(a.speech_dir) if a.speech_dir else None
    stt_ms = None
    play_until = 0.0  # when the audio the server sent so far would finish playing; a polite student waits for it
    async with websockets.connect(uri, max_size=None) as ws:
        await ws.send(json.dumps({"type": "hello", "protocol": 1, "token": j["session_token"], "mode": a.mode, "resume": False}))
        async for raw in ws:
            if isinstance(raw, bytes):
                continue
            msg = json.loads(raw)
            kind = msg["type"]
            if not seen_ready and kind != "ready":
                order_errors.append(f"expected ready first, got {kind!r}")
            if kind == "ready":
                seen_ready = True
            elif kind == "audio":
                play_until = max(play_until, time.time()) + msg["bytes"] / 2 / msg["sample_rate"]
            elif kind == "interrupt":
                play_until = 0.0
            elif kind == "transcript":
                stt_ms = msg["stt_ms"]
            elif kind == "ai_turn":
                if sent_at is not None:
                    rows.append({"turn": msg["idx"], "stt_ms": stt_ms, "server_latency_ms": msg["latency_ms"],
                                 "client_latency_ms": int((time.perf_counter() - sent_at) * 1000), "ended": msg["ended"]})
                    sent_at, waiting = None, False
            elif kind == "error":
                print(f"server error: {msg['code']} {msg['message']}")
                if not msg["retryable"]:
                    break
            elif kind == "ended":
                return {"sid": sid, "answers": answers, "rows": rows, "order_errors": order_errors, "ended": True, "status": msg["status"]}
            elif kind == "state" and msg["state"] == "listening" and not waiting and answers < a.answers:
                answers += 1
                waiting = True
                if a.pace:
                    await asyncio.sleep(max(0.0, play_until - time.time()) / a.pace)
                if a.mode == "push_to_talk":
                    await ws.send(json.dumps({"type": "ptt_start"}))
                clip = speech[(answers - 1) % len(speech)] if speech else None
                await stream(ws, a.answer_seconds, True, a.pace, pcm=clip)
                if a.mode == "push_to_talk":
                    sent_at = time.perf_counter()
                    await ws.send(json.dumps({"type": "ptt_end"}))
                else:
                    await stream(ws, 0.8, False, a.pace)
                    sent_at = time.perf_counter()
    return {"sid": sid, "answers": answers, "rows": rows, "order_errors": order_errors, "ended": False, "status": "?"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://localhost:8000")
    ap.add_argument("--viva", required=True)
    ap.add_argument("--student", required=True)
    ap.add_argument("--code", required=True)
    ap.add_argument("--mode", default="push_to_talk", choices=["push_to_talk", "hands_free"])
    ap.add_argument("--answers", type=int, default=60)
    ap.add_argument("--answer-seconds", type=float, default=1.5)
    ap.add_argument("--pace", type=float, default=1.0, help="1 = send audio in real time (default), 2 = twice as fast, 0 = no pacing")
    ap.add_argument("--speech-dir", help="folder of 16 kHz .wav answers to speak in order (cycled); default: a tone")
    ap.add_argument("--provider", default="stub", choices=["stub", "live"], help="label for the result sidecar (local real models count as live)")
    ap.add_argument("--model", default="stub-stt+stub-tts", help="model description for the result sidecar")
    ap.add_argument("--out", help="write per-turn latencies to this CSV (+ .meta.json sidecar)")
    a = ap.parse_args()
    res = asyncio.run(run(a))
    lat = [r["client_latency_ms"] for r in res["rows"]]
    q = lambda p: sorted(lat)[min(len(lat) - 1, int(p * len(lat)))] if lat else None  # noqa: E731
    srv = [r["server_latency_ms"] for r in res["rows"] if r["server_latency_ms"] is not None]
    sq = lambda p: sorted(srv)[min(len(srv) - 1, int(p * len(srv)))] if srv else None  # noqa: E731
    print(f"session {res['sid']}: ended={res['ended']} status={res['status']} answers={res['answers']} turns={len(lat)} "
          f"server latency p50={statistics.median(srv) if srv else None} p95={sq(0.95)} ms; client latency p50={statistics.median(lat) if lat else None} "
          f"p95={q(0.95)} ms; order errors: {res['order_errors'] or 'none'}")
    if a.out and res["rows"]:
        from app.results_meta import write_meta
        out = Path(a.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(res["rows"][0]))
            w.writeheader()
            w.writerows(res["rows"])
        note = ("scripted bot against VOICE_PROVIDER=stub: transport and engine hand-off only, not speech recognition or speech quality"
                if a.provider == "stub" else "scripted bot with recorded/synthetic speech through the real STT, engine and TTS; latency = student stops speaking -> first AI audio, measured by the server")
        write_meta(out, provider=a.provider, model=a.model, n=len(res["rows"]), n_unit="turns", mode=a.mode, speech_dir=a.speech_dir, note=note)
    sys.exit(0 if res["ended"] and not res["order_errors"] else 1)


if __name__ == "__main__":
    main()
