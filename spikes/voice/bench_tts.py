"""TTS benchmark: time from 'text ready' to 'first audio chunk' for the AI's sentences (the AI replies are short on purpose).
Each sentence is synthesised REPEATS times after a warm-up; the first-audio time is what the student waits for.
Usage: python spikes/voice/bench_tts.py"""
import statistics

from common import RESULTS, percentile, write_csv, write_meta
from corpus import AI_SENTENCES
from tts_engines import Kokoro, MacSay, Piper

REPEATS = 3


def main():
    engines = [MacSay("Rishi"), MacSay("Tara"), Piper("en_US-lessac-medium"), Piper("en_GB-alba-medium"), Kokoro("af_heart", stream=False),
               Kokoro("am_adam", stream=True)]
    summary = []
    for e in engines:
        e.first_chunk("Warm up.")
        rows = []
        for i, text in enumerate(AI_SENTENCES):
            for rep in range(REPEATS):
                first, first_audio, total, audio = e.first_chunk(text)
                rows.append([i, rep, len(text.split()), round(first, 4), round(first_audio, 3), round(total, 4), round(audio, 3), round(total / audio, 4)])
        out = RESULTS / f"tts_{e.name}.csv"
        write_csv(out, ["sentence", "repeat", "words", "first_chunk_s", "first_chunk_audio_s", "total_synth_s", "total_audio_s", "rtf"], rows)
        write_meta(out, provider="live", model=e.name, n=len(rows), n_unit="synthesis runs (16 AI sentences x 3 repeats)", compute="CPU, Apple M2",
                   model_load_s=round(e.load_s, 2))
        f = [r[3] for r in rows]
        print(f"{e.name:34} first chunk p50 {percentile(f, 50):.3f}s p95 {percentile(f, 95):.3f}s | rtf mean {statistics.mean(r[7] for r in rows):.3f} | load {e.load_s:.2f}s")
        summary.append(e.name)


if __name__ == "__main__":
    main()
