"""Option (c) smallest proof without a LiveKit server (none installed; Docker is not available here): does livekit / livekit-agents
install and import on this Python, and does the native RTC layer move audio (frames, resampling) locally?"""
import asyncio
import sys

import numpy as np
from livekit import rtc

print("python", sys.version.split()[0])
import livekit.agents as agents
print("livekit-agents imported; AgentSession:", hasattr(agents, "AgentSession"), "| Agent:", hasattr(agents, "Agent"))
async def main():
    # 48 kHz tone -> 16 kHz through the native resampler (the same path a room track would take)
    t = np.arange(48000) / 48000
    tone = (np.sin(2 * np.pi * 440 * t) * 12000).astype("<i2")
    frame = rtc.AudioFrame(tone.tobytes(), 48000, 1, len(tone))
    resampler = rtc.AudioResampler(48000, 16000, num_channels=1)
    out = list(resampler.push(frame)) + list(resampler.flush())
    print(f"resampled 1.0 s @48 kHz -> {sum(f.samples_per_channel for f in out)} samples @16 kHz via the native library (expected 16000)")
    src = rtc.AudioSource(16000, 1)  # needs a running loop on Python 3.14: it calls asyncio.get_event_loop() in __init__
    print("AudioSource created inside a running event loop:", type(src).__name__)
    print("Room class present:", hasattr(rtc, "Room"), "(connecting needs a LiveKit server: not available here)")


asyncio.run(main())
try:
    rtc.AudioSource(16000, 1)
except RuntimeError as e:
    print("AudioSource created OUTSIDE a loop on 3.14 ->", e)
