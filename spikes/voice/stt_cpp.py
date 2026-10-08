"""whisper.cpp (Metal on Apple Silicon) through its `whisper-cli` binary (brew install whisper-cpp). Each call starts a process, so the
reported time is the CLI's own `total time` minus `load time` (inference only), and the wall time of the whole process is kept separately."""
import re
import subprocess
import tempfile
from pathlib import Path

import numpy as np
import soundfile as sf

from common import MODELS


class WhisperCpp:
    def __init__(self, size: str, quant: str = "q5_1", threads: int = 4, language: str = "en"):
        self.model = MODELS / "whisper.cpp" / f"ggml-{size}-{quant}.bin"
        if not self.model.exists():
            raise FileNotFoundError(f"{self.model} missing: run spikes/voice/fetch_models.py")
        self.name, self.threads, self.language, self.load_s = f"whisper.cpp-{size}-{quant}-metal", threads, language, 0.0
        self.last = {}

    def transcribe(self, audio, language=None, wav_path=None):
        """-> (text, inference seconds). `audio` is a float32 16 kHz array (or pass wav_path). Sets self.last with the CLI's timings."""
        with tempfile.TemporaryDirectory() as d:
            path = wav_path
            if path is None:
                path = Path(d) / "in.wav"
                sf.write(path, audio, 16000, subtype="PCM_16")
            import time
            t = time.perf_counter()
            out = subprocess.run(["whisper-cli", "-m", str(self.model), "-f", str(path), "-l", language or self.language, "-nt", "-t", str(self.threads)],
                                 capture_output=True, text=True, check=True)
            wall = time.perf_counter() - t
        timings = {k: float(v) / 1000 for k, v in re.findall(r"whisper_print_timings:\s+(\w+) time =\s+([\d.]+) ms", out.stderr)}
        self.last = {"wall_s": wall, **timings, "metal": "ggml_metal_device_init" in out.stderr and "no GPU" not in out.stderr}
        inference = timings.get("total", wall) - timings.get("load", 0.0)
        return " ".join(out.stdout.split()), inference
