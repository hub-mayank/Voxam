"""How does local STT latency degrade when several students' turns are decoded at the same time on this one machine?
N threads each decode the same ~6 s clip K times back to back (a saturated worker: the worst case, not a viva's duty cycle).
One shared model, one CPU thread per decode (cpu_threads=1, num_workers=N), as a multi-student server would run it.
Usage: python spikes/voice/bench_stt_concurrency.py [--models base,small] [--levels 1,2,4,8,12]"""
import argparse
import threading
import time

import soundfile as sf
from faster_whisper import WhisperModel

from common import MODELS, RESULTS, SYNTH, percentile, write_csv, write_meta


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", default="base,small")
    ap.add_argument("--levels", default="1,2,4,8,12")
    ap.add_argument("--repeats", type=int, default=4)
    a = ap.parse_args()
    clip = sf.read(SYNTH / "t12.wav", dtype="float32")[0]
    audio_s = len(clip) / 16000
    rows = []
    for size in a.models.split(","):
        for n in [int(x) for x in a.levels.split(",")]:
            model = WhisperModel(str(MODELS / f"faster-whisper-{size}"), device="cpu", compute_type="int8", cpu_threads=1, num_workers=n)
            list(model.transcribe(clip, language="en", beam_size=1, temperature=0.0, without_timestamps=True)[0])  # warm-up
            lat, lock = [], threading.Lock()

            def worker():
                for _ in range(a.repeats):
                    t = time.perf_counter()
                    segs, _ = model.transcribe(clip, language="en", beam_size=1, temperature=0.0, condition_on_previous_text=False, without_timestamps=True)
                    list(segs)
                    with lock:
                        lat.append(time.perf_counter() - t)

            t0 = time.perf_counter()
            threads = [threading.Thread(target=worker) for _ in range(n)]
            [t.start() for t in threads]
            [t.join() for t in threads]
            wall = time.perf_counter() - t0
            rows.append([f"faster-whisper-{size}-int8", n, len(lat), round(audio_s, 2), round(percentile(lat, 50), 3), round(percentile(lat, 95), 3),
                         round(len(lat) / wall, 2), round(len(lat) * audio_s / wall, 1)])
            print(f"{size:6} N={n:2}: per-decode p50 {rows[-1][4]:.2f}s p95 {rows[-1][5]:.2f}s | throughput {rows[-1][6]:.2f} decodes/s = {rows[-1][7]:.1f} s of audio per s")
    out = RESULTS / "stt_concurrency.csv"
    write_csv(out, ["model", "concurrent_decodes", "decodes", "clip_audio_s", "decode_p50_s", "decode_p95_s", "decodes_per_s", "audio_seconds_per_second"], rows)
    write_meta(out, provider="live", model=[f"faster-whisper-{m}-int8" for m in a.models.split(",")], n=sum(r[2] for r in rows),
               n_unit="decodes of one 6 s synthetic clip", audio="synthetic", compute="CPU int8, Apple M2 (4P+4E cores), cpu_threads=1 per decode",
               note="saturated workers (worst case); STT only: VAD, LLM, TTS and the API not included")


if __name__ == "__main__":
    main()
