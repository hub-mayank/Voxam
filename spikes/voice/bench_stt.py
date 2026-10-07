"""STT benchmark on the synthetic turns (macOS say, Indian-English voices).
Per turn and model:
  batch      decode the whole utterance after the endpoint fires (what a simple pipeline does)
  segmented  the utterance is cut at thinking pauses (or every <= 8 s at the quietest point); all pieces but the last are decoded
             WHILE the student is still talking, so only the last piece is on the critical path after the endpoint
Usage: python spikes/voice/bench_stt.py --models small,medium [--beam 1] [--hangover 600]"""
import argparse
import csv
import statistics

import numpy as np
import soundfile as sf

from common import RESULTS, SAMPLE_RATE, SYNTH, percentile, write_csv, write_meta
from stt_fw import FasterWhisper
from vad import FRAME, FRAME_MS, endpoint_frame, force_cuts, speech_probs, speech_segments
from wer import wer


def pieces_for(audio, probs, end_sample):
    """Cut [first speech, endpoint) into the pieces a streaming pipeline would decode as the student speaks."""
    segs = speech_segments(probs)
    if not segs:
        return [(0, end_sample)]
    pieces = []
    for a, b in segs:
        pieces += force_cuts(audio, a * FRAME, min(b * FRAME, end_sample))
    return pieces


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", default="small,medium")
    ap.add_argument("--beam", type=int, default=1)
    ap.add_argument("--hangover", type=int, default=600)
    ap.add_argument("--threads", type=int, default=4)
    args = ap.parse_args()
    manifest = list(csv.DictReader(open(SYNTH / "manifest.csv")))
    cache = {}
    for m in manifest:
        audio, _ = sf.read(SYNTH / f"{m['id']}.wav", dtype="float32")
        probs, _ = speech_probs(audio)
        f = endpoint_frame(probs, args.hangover)
        end = (f + 1) * FRAME if f is not None else len(audio)
        cache[m["id"]] = (audio[:end], probs[:f + 1] if f is not None else probs)
    for size in args.models.split(","):
        stt = FasterWhisper(size, cpu_threads=args.threads, beam=args.beam)
        stt.transcribe(cache[manifest[5]["id"]][0])  # warm-up (first call pays one-time costs); not recorded
        rows = []
        for m in manifest:
            audio, probs = cache[m["id"]]
            text_b, t_b = stt.transcribe(audio)
            pieces = [p for p in pieces_for(audio, probs, len(audio)) if (p[1] - p[0]) / SAMPLE_RATE >= 0.3]
            texts, times = [], []
            for a, b in pieces:
                t, s = stt.transcribe(audio[a:b])
                texts.append(t)
                times.append(s)
            text_s = " ".join(texts)
            rows.append([m["id"], m["voice"], m["has_pauses"], m["noisy"], int(m["words"]), round(len(audio) / SAMPLE_RATE, 3),
                         round(t_b, 4), round(t_b / (len(audio) / SAMPLE_RATE), 4), len(pieces), round(times[-1], 4), round((pieces[-1][1] - pieces[-1][0]) / SAMPLE_RATE, 3),
                         round(sum(times), 4), round(wer(m["text"], text_b), 4), round(wer(m["text"], text_s), 4), text_b])
        out = RESULTS / f"stt_faster_whisper_{size}.csv"
        write_csv(out, ["turn", "voice", "has_pauses", "noisy", "words", "audio_s", "batch_decode_s", "batch_rtf", "pieces", "last_piece_decode_s",
                        "last_piece_audio_s", "all_pieces_decode_s", "wer_batch", "wer_segmented", "text_batch"], rows)
        write_meta(out, provider="live", model=stt.name, n=len(rows), n_unit="synthetic turns (macOS say)", audio="synthetic",
                   compute="CPU int8, Apple M2", cpu_threads=args.threads, beam=args.beam, hangover_ms=args.hangover, model_load_s=round(stt.load_s, 2),
                   wer_note="WER on clean synthetic voices is optimistic; see Mayank's clips for accented speech")
        b = [r[6] for r in rows]
        last = [r[9] for r in rows]
        print(f"{stt.name}: load {stt.load_s:.1f}s | batch decode p50 {percentile(b, 50):.2f}s p95 {percentile(b, 95):.2f}s "
              f"(rtf mean {statistics.mean(r[7] for r in rows):.2f}) | last-piece decode p50 {percentile(last, 50):.2f}s p95 {percentile(last, 95):.2f}s "
              f"| WER batch {statistics.mean(r[12] for r in rows):.3f} segmented {statistics.mean(r[13] for r in rows):.3f}")
        short = [r[6] for r in rows if r[5] < 4]
        long = [r[6] for r in rows if r[5] > 10]
        print(f"   batch decode time by length: <4 s audio p50 {percentile(short, 50):.2f}s (n={len(short)}), >10 s audio p50 {percentile(long, 50):.2f}s (n={len(long)})")


if __name__ == "__main__":
    main()
