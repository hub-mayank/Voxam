"""TTS candidates behind one interface: first_chunk(text) -> (seconds until the first audio chunk exists, audio_seconds_of_that_chunk, total_seconds, total_audio_seconds)."""
import asyncio
import subprocess
import tempfile
from pathlib import Path

import numpy as np
import soundfile as sf

from common import MODELS, now


class MacSay:
    """macOS `say`: baseline. It can only write a finished file, so time-to-first-chunk equals the whole synthesis."""
    def __init__(self, voice="Rishi"):
        self.voice, self.name = voice, f"macos-say-{voice}"
        self.load_s = 0.0

    def first_chunk(self, text):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "o.aiff"
            t = now()
            subprocess.run(["say", "-v", self.voice, "-o", str(out), text], check=True)
            total = now() - t
            audio, sr = sf.read(out)
        dur = len(audio) / sr
        return total, dur, total, dur


class Piper:
    """Piper (ONNX VITS) via piper-tts: yields one chunk per sentence."""
    def __init__(self, voice="en_US-lessac-medium"):
        from piper import PiperVoice
        t = now()
        self.voice = PiperVoice.load(next((MODELS / "piper").rglob(f"{voice}.onnx")))
        self.name, self.load_s = f"piper-{voice}", now() - t

    def first_chunk(self, text):
        t = now()
        first, durs = None, []
        for chunk in self.voice.synthesize(text):
            if first is None:
                first = now() - t
            durs.append(len(chunk.audio_float_array) / chunk.sample_rate)
        return first, durs[0], now() - t, sum(durs)


class Kokoro:
    """Kokoro-82M via kokoro-onnx. `stream=True` uses create_stream (sentence-level chunks)."""
    def __init__(self, voice="af_heart", stream=True):
        from kokoro_onnx import Kokoro as K
        t = now()
        self.k = K(str(MODELS / "kokoro" / "kokoro-v1.0.onnx"), str(MODELS / "kokoro" / "voices-v1.0.bin"))
        self.voice, self.stream = voice, stream
        self.name, self.load_s = f"kokoro-v1.0-{voice}{'-stream' if stream else ''}", now() - t

    def first_chunk(self, text):
        t = now()
        if not self.stream:
            audio, sr = self.k.create(text, voice=self.voice, speed=1.0, lang="en-us")
            total = now() - t
            return total, len(audio) / sr, total, len(audio) / sr

        async def run():
            first, durs = None, []
            async for audio, sr in self.k.create_stream(text, voice=self.voice, speed=1.0, lang="en-us"):
                if first is None:
                    first = now() - t
                durs.append(len(audio) / sr)
            return first, durs[0], now() - t, sum(durs)
        return asyncio.run(run())
