"""How much does Piper gain from more processes (PIPER_PROCS)? Real Piper, one run per process count, the same offered load:
`threads` callers each synthesise `per_thread` sentences back to back.
python scripts/piper_concurrency.py [--procs 1 2 4 8] [--threads 8] [--per-thread 6] [--out results/load/piper_procs.csv]"""
import argparse
import csv
import statistics
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.results_meta import write_meta  # noqa: E402
from app.voice.config import VoiceConfig  # noqa: E402
from app.voice.local import PiperTTS  # noqa: E402
from app.voice.providers import STUB_SENTENCES, split_sentences  # noqa: E402


def run(procs, threads, per_thread):
    cfg = VoiceConfig.from_env({"VOICE_PROVIDER": "local", "PIPER_PROCS": str(procs)})
    tts = PiperTTS(cfg)
    sentences = [s for text in STUB_SENTENCES for s in split_sentences(text)]
    tts.synthesize("Ready.")
    for p in tts.pool:  # every process is loaded before the clock starts
        p.say("Ready.")
    times, lock = [], threading.Lock()

    def caller(k):
        for i in range(per_thread):
            t = time.perf_counter()
            tts.synthesize(sentences[(k * per_thread + i) % len(sentences)])
            with lock:
                times.append(time.perf_counter() - t)

    start = time.perf_counter()
    pool = [threading.Thread(target=caller, args=(k,)) for k in range(threads)]
    [t.start() for t in pool]
    [t.join() for t in pool]
    wall = time.perf_counter() - start
    tts.close()
    times.sort()
    mean_words = statistics.mean(len(sentences[(k * per_thread + i) % len(sentences)].split()) for k in range(threads) for i in range(per_thread))
    return {"procs": procs, "threads": threads, "sentences": len(times), "mean_words": round(mean_words, 1), "wall_s": round(wall, 2),
            "sentences_per_s": round(len(times) / wall, 2), "call_p50_s": round(statistics.median(times), 3),
            "call_p95_s": round(times[int(0.95 * len(times)) - 1], 3)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--procs", type=int, nargs="+", default=[1, 2, 3, 4, 6, 8])
    ap.add_argument("--threads", type=int, default=8)
    ap.add_argument("--per-thread", type=int, default=6)
    ap.add_argument("--out", default=str(ROOT / "results" / "load" / "piper_procs.csv"))
    args = ap.parse_args()
    rows = []
    for p in args.procs:
        row = run(p, args.threads, args.per_thread)
        print(row)
        rows.append(row)
    with open(args.out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    write_meta(args.out, provider="live", model="piper-en_GB-alba-medium (real Piper process pool)", n=sum(r["sentences"] for r in rows),
               n_unit="sentences", threads=args.threads, per_thread=args.per_thread,
               note="TTS only, no STT running at the same time: the cores are not shared with whisper.cpp here")


if __name__ == "__main__":
    main()
