"""STT on long answers (the viva caps an answer at 90 s; Whisper's window is 30 s). Mayank's real English clips (c01-c05) are joined with
0.5 s of silence into answers of about 22, 45, 67 and 93 s (real speech, concatenated: stated, not synthesised). Each engine decodes each answer
3 times; decode time is the median. WER is against the concatenated reference text.
Usage: python spikes/voice/bench_long.py [--models base,small] [--cpp base,small]"""
import argparse
import statistics

import numpy as np
import soundfile as sf

from bench_wer import wav_for
from clip_refs import REFS
from common import RESULTS, write_csv, write_meta
from stt_cpp import WhisperCpp
from stt_fw import FasterWhisper
from wer import wer

COMBOS = [("c01",), ("c01", "c02"), ("c01", "c02", "c04"), ("c01", "c02", "c03", "c04")]
GAP = np.zeros(8000, dtype="float32")  # 0.5 s


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", default="base,small")
    ap.add_argument("--cpp", default="base,small")
    ap.add_argument("--repeats", type=int, default=3)
    a = ap.parse_args()
    answers = []
    for combo in COMBOS:
        audio = np.concatenate([x for c in combo for x in (wav_for(c), GAP)][:-1])
        answers.append((combo, audio, " ".join(REFS[c] for c in combo)))
    engines = [FasterWhisper(s) for s in a.models.split(",") if s] + [WhisperCpp(s) for s in a.cpp.split(",") if s]
    rows = []
    for stt in engines:
        stt.transcribe(answers[0][1][:16000 * 3])
        for combo, audio, ref in answers:
            times, text = [], ""
            for _ in range(a.repeats):
                text, secs = stt.transcribe(audio)
                times.append(secs)
            dur = len(audio) / 16000
            rows.append([stt.name, "+".join(combo), round(dur, 1), len(ref.split()), round(statistics.median(times), 3), round(min(times), 3), round(max(times), 3),
                         round(statistics.median(times) / dur, 3), round(wer(ref, text), 4)])
            print(f"{stt.name:30} {dur:5.1f} s answer: decode {statistics.median(times):5.2f} s (rtf {statistics.median(times) / dur:.2f}) WER {rows[-1][-1]:.3f}")
    out = RESULTS / "stt_long_answers.csv"
    write_csv(out, ["engine", "clips", "audio_s", "ref_words", "decode_median_s", "decode_min_s", "decode_max_s", "rtf", "wer"], rows)
    write_meta(out, provider="live", model=sorted({r[0] for r in rows}), n=len(rows), n_unit="engine x answer length (median of 3 decodes)",
               audio="real, Mayank, read aloud; clips concatenated with 0.5 s silence", note="one speaker; batch decode of the whole answer, no streaming")


if __name__ == "__main__":
    main()
