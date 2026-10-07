"""Drive ws_server.py with the synthetic turns streamed in REAL TIME (20 ms frames, paced like a microphone) and measure what a
browser would see. Also a barge-in test. Writes results/voice_spike/transport_ws.csv.
Usage: python spikes/voice/transport/proof_ws.py [--turns 12]"""
import argparse
import asyncio
import csv
import json
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import soundfile as sf
import websockets

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from common import RESULTS, SYNTH, percentile, write_csv, write_meta  # noqa: E402

PORT = 8801
FRAME = 320  # 20 ms at 16 kHz


async def stream(ws, audio, realtime=True, start_event=None):
    pcm = (np.clip(audio, -1, 1) * 32767).astype("<i2").tobytes()
    t0 = time.perf_counter()
    for i in range(0, len(pcm), FRAME * 2):
        await ws.send(pcm[i:i + FRAME * 2])
        if realtime:
            await asyncio.sleep(max(0, t0 + (i // 2 + FRAME) / 16000 - time.perf_counter()))


async def one_turn(uri, audio, true_end_s):
    async with websockets.connect(uri, max_size=None) as ws:
        events, first_audio_at = {}, None
        t_start = time.time()
        sender = asyncio.create_task(stream(ws, audio))
        while True:
            try:
                msg = await asyncio.wait_for(ws.recv(), timeout=20)
            except asyncio.TimeoutError:
                break
            if isinstance(msg, bytes):
                first_audio_at = first_audio_at or time.time()
                break
            ev = json.loads(msg)
            events.setdefault(ev["type"], ev)
        sender.cancel()
        true_end_wall = t_start + true_end_s
        return {"endpoint_delay_ms": (events["endpoint"]["t"] - true_end_wall) * 1000, "stt_s": events["transcript"]["stt_s"],
                "first_audio_ms": (first_audio_at - true_end_wall) * 1000, "text": events["transcript"]["text"]}


async def barge_in(uri, long_audio, interrupter):
    """Let the AI start talking, then speak over it. -> ms from the student's first speech sample to the server's interrupt event."""
    async with websockets.connect(uri, max_size=None) as ws:
        await stream(ws, long_audio)
        got_audio = False
        while not got_audio:
            msg = await asyncio.wait_for(ws.recv(), timeout=20)
            if isinstance(msg, bytes):
                got_audio = True
        t_speak = time.time()
        sender = asyncio.create_task(stream(ws, interrupter))
        while True:
            msg = await asyncio.wait_for(ws.recv(), timeout=10)
            if isinstance(msg, str) and json.loads(msg)["type"] == "interrupt":
                sender.cancel()
                return (json.loads(msg)["t"] - t_speak) * 1000


async def main(turns):
    manifest = list(csv.DictReader(open(SYNTH / "manifest.csv")))
    pick = [m for m in manifest if 3 <= float(m["speech_end_s"]) <= 9][:turns]
    uri = f"ws://127.0.0.1:{PORT}/voice"
    rows = []
    for m in pick:
        audio, _ = sf.read(SYNTH / f"{m['id']}.wav", dtype="float32")
        r = await one_turn(uri, audio, float(m["speech_end_s"]))
        rows.append([m["id"], round(float(m["speech_end_s"]), 2), round(r["endpoint_delay_ms"]), round(r["stt_s"], 3), round(r["first_audio_ms"]), r["text"]])
    long_audio = sf.read(SYNTH / "t13.wav", dtype="float32")[0]
    interrupter = sf.read(SYNTH / "t11.wav", dtype="float32")[0]
    barge_ms = await barge_in(uri, long_audio, interrupter)
    return rows, barge_ms


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--turns", type=int, default=12)
    ap.add_argument("--stt", default="base")
    a = ap.parse_args()
    env = {"PATH": "/usr/bin:/bin", "STT_SIZE": a.stt, "HOME": str(Path.home())}
    server = subprocess.Popen([sys.executable, "-m", "uvicorn", "ws_server:app", "--port", str(PORT), "--log-level", "warning"], cwd=HERE, env=env,
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    try:
        import urllib.request
        for _ in range(100):
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{PORT}/probe", timeout=1)
                break
            except Exception:
                time.sleep(0.3)
        rows, barge_ms = asyncio.run(main(a.turns))
    finally:
        server.terminate()
        server.wait(timeout=10)
    out = RESULTS / "transport_ws.csv"
    write_csv(out, ["turn", "true_speech_end_s", "endpoint_delay_ms_seen_by_client", "server_stt_s", "first_reply_audio_ms_after_speech_end", "transcript"], rows)
    write_meta(out, provider="live", model=["silero-vad", f"faster-whisper-{a.stt}-int8", "piper-en_US-lessac-medium"], n=len(rows),
               n_unit="turns over a real localhost WebSocket, audio paced in real time (synthetic speech)", audio="synthetic",
               barge_in_interrupt_ms=round(barge_ms), reply="canned echo (no LLM)", transport="FastAPI WebSocket + uvicorn + websockets")
    f = [r[4] for r in rows]
    print(f"WebSocket loop, {len(rows)} turns: first reply audio {percentile(f, 50):.0f} ms p50 / {percentile(f, 95):.0f} ms p95 after the student stopped "
          f"(endpoint {percentile([r[2] for r in rows], 50):.0f} ms, stt {percentile([r[3] for r in rows], 50):.2f}s); barge-in interrupt after {barge_ms:.0f} ms")
