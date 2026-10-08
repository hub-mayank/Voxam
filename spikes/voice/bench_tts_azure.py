"""Azure Speech (F0 free tier) en-IN neural voice vs Piper alba, first-audio latency over 24 AI sentences.
Azure: POST the SSML, read the streamed body, time to the first audio bytes (headers arrive first; the first body chunk is audio). Every request is
counted by the budget registry and logged. Piper alba runs locally on the same sentences in the same script.
Usage: python spikes/voice/bench_tts_azure.py [--voice en-IN-NeerjaNeural] [--repeats 2]"""
import argparse
import statistics
import time
from xml.sax.saxutils import escape

import httpx

from common import RESULTS, percentile, write_csv, write_meta
from corpus import ALL_AI_SENTENCES
from counted import counted, key
from tts_engines import Piper


def azure_first_chunk(region, k, voice, text):
    ssml = f"<speak version='1.0' xml:lang='en-IN'><voice name='{voice}'>{escape(text)}</voice></speak>"
    headers = {"Ocp-Apim-Subscription-Key": k, "Content-Type": "application/ssml+xml", "X-Microsoft-OutputFormat": "riff-16khz-16bit-mono-pcm",
               "User-Agent": "ai-viva-voice-spike"}
    url = f"https://{region}.tts.speech.microsoft.com/cognitiveservices/v1"

    def call():
        t = time.perf_counter()
        first, size = None, 0
        with httpx.stream("POST", url, content=ssml.encode(), headers=headers, timeout=30) as r:
            if r.status_code >= 400:
                r.read()
                r.raise_for_status()
            for chunk in r.iter_bytes():
                if chunk and first is None:
                    first = time.perf_counter() - t
                size += len(chunk)
        return first, time.perf_counter() - t, size

    (first, total, size), _ = counted("azure-speech", voice, "tts", call)
    return first, total, size


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--voice", default="en-IN-NeerjaNeural")
    ap.add_argument("--repeats", type=int, default=2)
    a = ap.parse_args()
    k, region = key("AZURE_SPEECH_KEY"), key("AZURE_SPEECH_REGION")
    azure_first_chunk(region, k, a.voice, "Warm up.")  # connection set-up and DNS: not recorded (but counted)
    piper = Piper("en_GB-alba-medium")
    piper.first_chunk("Warm up.")
    rows = []
    for i, text in enumerate(ALL_AI_SENTENCES):
        for rep in range(a.repeats):
            first, total, size = azure_first_chunk(region, k, a.voice, text)
            rows.append([f"azure:{a.voice}", i, rep, len(text.split()), round(first, 4), round(total, 4), size])
            pf, pa, pt, pta = piper.first_chunk(text)
            rows.append([piper.name, i, rep, len(text.split()), round(pf, 4), round(pt, 4), ""])
    out = RESULTS / "tts_azure_vs_piper_alba.csv"
    write_csv(out, ["engine", "sentence", "repeat", "words", "first_audio_s", "total_s", "bytes"], rows)
    write_meta(out, provider="live", model=[f"azure-speech:{a.voice}", piper.name], n=len(rows) // 2, n_unit="synthesis requests per engine (24 sentences x repeats)",
               azure_requests=len(rows) // 2 + 1, free_tier="Azure Speech F0", region=region, note="Azure time includes the network round trip from this Mac; Piper is local")
    for engine in sorted({r[0] for r in rows}):
        v = [r[4] for r in rows if r[0] == engine]
        print(f"{engine:34} first audio p50 {percentile(v, 50):.3f}s p95 {percentile(v, 95):.3f}s (n={len(v)})")


if __name__ == "__main__":
    main()
