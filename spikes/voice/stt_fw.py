"""faster-whisper (CTranslate2) on CPU, int8: the local STT candidate. Whisper pads every input to a 30 s window, so decode time is
mostly flat in utterance length; stt_bench measures that instead of assuming it."""
import numpy as np
from faster_whisper import WhisperModel

from common import MODELS, now


class FasterWhisper:
    def __init__(self, size: str, compute_type: str = "int8", cpu_threads: int = 4, beam: int = 1, language="en"):
        self.size, self.compute_type, self.cpu_threads, self.beam, self.language = size, compute_type, cpu_threads, beam, language
        t = now()
        self.model = WhisperModel(str(MODELS / f"faster-whisper-{size}"), device="cpu", compute_type=compute_type, cpu_threads=cpu_threads)
        self.load_s = now() - t
        self.name = f"faster-whisper-{size}-{compute_type}"

    def transcribe(self, audio: np.ndarray, language=None):
        """-> (text, seconds). The generator is consumed inside the timer: lazy decoding would hide the cost."""
        t = now()
        segments, info = self.model.transcribe(audio, language=language or self.language, beam_size=self.beam, temperature=0.0,
                                               condition_on_previous_text=False, vad_filter=False, without_timestamps=True)
        text = " ".join(s.text.strip() for s in segments).strip()
        return text, now() - t

    def transcribe_auto(self, audio: np.ndarray):
        """Let the model detect the language (it may pick Hindi for Hinglish and answer in Devanagari)."""
        t = now()
        segments, info = self.model.transcribe(audio, language=None, beam_size=self.beam, temperature=0.0, condition_on_previous_text=False,
                                               vad_filter=False, without_timestamps=True)
        return " ".join(s.text.strip() for s in segments).strip(), now() - t
