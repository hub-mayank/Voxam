"""Groq Whisper (whisper-large-v3-turbo) over the OpenAI-compatible transcription endpoint. Free tier: counted per call by the budget registry."""
import io

import httpx
import soundfile as sf

from counted import counted, key

URL = "https://api.groq.com/openai/v1/audio/transcriptions"


class GroqWhisper:
    def __init__(self, model="whisper-large-v3-turbo"):
        self.model, self.name, self.load_s = model, f"groq-{model}", 0.0
        self.key = key("GROQ_API_KEY")

    def transcribe(self, audio, language=None):
        """-> (text, seconds of the HTTP round trip, which is what a live call would wait). language: en, hi, or None/'auto'."""
        buf = io.BytesIO()
        sf.write(buf, audio, 16000, format="WAV", subtype="PCM_16")
        data = {"model": self.model, "response_format": "json", "temperature": "0"}
        if language and language != "auto":
            data["language"] = language

        def call():
            r = httpx.post(URL, headers={"Authorization": f"Bearer {self.key}"}, files={"file": ("clip.wav", buf.getvalue(), "audio/wav")}, data=data, timeout=60)
            r.raise_for_status()
            return r.json()["text"]

        text, seconds = counted("groq", self.model, "stt", call)
        return text.strip(), seconds
