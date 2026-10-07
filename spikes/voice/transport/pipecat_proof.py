"""Option (b) smallest proof: does Pipecat install on this Python and move audio through its pipeline with its Silero VAD?
Run in the isolated venv: spikes/voice/transport/.venv/bin/python pipecat_proof.py
Feeds one synthetic turn as 20 ms InputAudioRawFrames and records the frames the pipeline emits (speaking events, timing)."""
import asyncio
import sys
import time
from pathlib import Path

import numpy as np
import soundfile as sf
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.frames.frames import EndFrame, Frame, InputAudioRawFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.audio.vad_processor import VADProcessor
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

WAV = Path(__file__).resolve().parents[1] / "data" / "synth" / "t13.wav"


class Recorder(FrameProcessor):
    """Logs every frame type that reaches it, with the number of audio frames pushed so far."""
    def __init__(self):
        super().__init__()
        self.seen, self.events, self.audio_frames = {}, [], 0

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)
        name = type(frame).__name__
        self.seen[name] = self.seen.get(name, 0) + 1
        if isinstance(frame, InputAudioRawFrame):
            self.audio_frames += 1
        elif "Speaking" in name:
            self.events.append((name, self.audio_frames * 0.02))
        await self.push_frame(frame, direction)


async def main():
    audio, sr = sf.read(WAV, dtype="float32")
    pcm = (audio * 32767).astype("<i2").tobytes()
    rec = Recorder()
    pipeline = Pipeline([VADProcessor(vad_analyzer=SileroVADAnalyzer(sample_rate=16000)), rec])
    task = PipelineTask(pipeline, params=PipelineParams(audio_in_sample_rate=16000))
    step = 640  # 20 ms of 16-bit mono at 16 kHz
    frames = [InputAudioRawFrame(audio=pcm[i:i + step], sample_rate=16000, num_channels=1) for i in range(0, len(pcm) - step + 1, step)]
    t = time.perf_counter()
    runner = PipelineRunner(handle_sigint=False)
    await task.queue_frames(frames + [EndFrame()])
    await runner.run(task)
    wall = time.perf_counter() - t
    print(f"python {sys.version.split()[0]}: pushed {len(frames)} audio frames ({len(frames) * 0.02:.1f} s of speech) in {wall:.2f} s wall")
    print("frames seen by the last processor:", rec.seen)
    print("speaking events (name, seconds of audio pushed when it fired):", [(n, round(s, 2)) for n, s in rec.events])


asyncio.run(main())
