"""VAD benchmark on the synthetic turns: how long after the student stops does the endpoint fire, and how often does it fire
too early (cutting the student off in a thinking pause)? Hangover is the silence required before the endpoint.
Usage: python spikes/voice/bench_vad.py"""
import csv
import statistics

import soundfile as sf

from common import RESULTS, SYNTH, percentile, write_csv, write_meta
from vad import FRAME_MS, endpoint_frame, speech_probs

HANGOVERS = [300, 500, 700, 900]


def main():
    manifest = list(csv.DictReader(open(SYNTH / "manifest.csv")))
    rows, per_frame = [], []
    for m in manifest:
        audio, _ = sf.read(SYNTH / f"{m['id']}.wav", dtype="float32")
        probs, costs = speech_probs(audio)
        per_frame += list(costs)
        true_end = float(m["speech_end_s"])
        for h in HANGOVERS:
            f = endpoint_frame(probs, h)
            fired_s = None if f is None else (f + 1) * FRAME_MS / 1000
            # the endpoint fires `h` ms after the last speech VAD saw; it is premature if that last speech is well before the true end
            last_speech_s = None if fired_s is None else fired_s - h / 1000
            premature = fired_s is not None and last_speech_s < true_end - 0.5
            delay_ms = None if fired_s is None else round((fired_s - true_end) * 1000)
            rows.append([m["id"], m["voice"], m["has_pauses"], m["noisy"], h, true_end, "" if fired_s is None else round(fired_s, 3),
                         "" if delay_ms is None else delay_ms, int(premature), round(statistics.mean(costs) * 1000, 3)])
    out = RESULTS / "vad_endpoint.csv"
    write_csv(out, ["turn", "voice", "has_pauses", "noisy", "hangover_ms", "true_speech_end_s", "endpoint_s", "endpoint_delay_ms_after_true_end",
                    "premature_cut", "vad_ms_per_32ms_frame"], rows)
    write_meta(out, provider="live", model="silero-vad (pysilero-vad ONNX)", n=len(manifest), n_unit="synthetic turns (macOS say), each tried at 4 hangovers",
               audio="synthetic")
    print(f"VAD cost per 32 ms frame: mean {statistics.mean(per_frame) * 1000:.3f} ms, p95 {percentile(per_frame, 95) * 1000:.3f} ms "
          f"(real-time factor {statistics.mean(per_frame) / (FRAME_MS / 1000):.4f})")
    for h in HANGOVERS:
        sel = [r for r in rows if r[4] == h]
        d = [r[7] for r in sel if r[7] != ""]
        pa = [r for r in sel if r[2] == "1"]
        print(f"hangover {h} ms: endpoint delay p50 {percentile(d, 50):.0f} ms p95 {percentile(d, 95):.0f} ms; "
              f"premature cuts {sum(r[8] for r in sel)}/{len(sel)} turns ({sum(r[8] for r in pa)}/{len(pa)} of those with thinking pauses)")


if __name__ == "__main__":
    main()
