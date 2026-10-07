"""WER on the 7 real clips (Mayank's voice) for each faster-whisper size, plus the Hinglish language-setting question.
English clips: language forced to en. Hinglish clips: tried with language=en (Roman output expected), language=hi (Devanagari output expected) and auto.
Reports `strict` WER and, for Hinglish, `skeleton` WER (see wer.py for what each means). Skips quietly if the clips are not there yet.
Usage: python spikes/voice/bench_wer.py [--models base,small,medium]"""
import argparse
import statistics
import subprocess

import soundfile as sf

from clip_refs import HINGLISH, REFS
from common import CLIPS, RESULTS, write_csv, write_meta
from stt_fw import FasterWhisper
from wer import DEVANAGARI, counts, wer


def wav_for(clip_id):
    src = next((CLIPS / f"{clip_id}{ext}" for ext in (".m4a", ".wav", ".mp3", ".aac", ".caf") if (CLIPS / f"{clip_id}{ext}").exists()), None)
    if src is None:
        return None
    wav = CLIPS / f"{clip_id}.16k.wav"
    if not wav.exists() or wav.stat().st_mtime < src.stat().st_mtime:
        subprocess.run(["afconvert", "-f", "WAVE", "-d", "LEI16@16000", "-c", "1", str(src), str(wav)], check=True)
    audio, _ = sf.read(wav, dtype="float32")
    return audio


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", default="base,small,medium")
    args = ap.parse_args()
    clips = {c: wav_for(c) for c in REFS}
    present = {c: a for c, a in clips.items() if a is not None}
    if not present:
        raise SystemExit(f"no clips in {CLIPS}; see spikes/voice/RECORDING.md")
    print(f"{len(present)}/7 clips found: {sorted(present)}")
    rows = []
    for size in args.models.split(","):
        stt = FasterWhisper(size)
        stt.transcribe(next(iter(present.values()))[:16000 * 3])
        for cid, audio in sorted(present.items()):
            langs = ["en", "hi", None] if cid in HINGLISH else ["en"]
            for lang in langs:
                text, secs = stt.transcribe(audio, language=lang) if lang else stt.transcribe_auto(audio)
                s, d, i, n = counts(REFS[cid], text)
                rows.append([stt.name, cid, "hinglish" if cid in HINGLISH else "english", lang or "auto", round(len(audio) / 16000, 1), round(secs, 2),
                             round(wer(REFS[cid], text), 4), round(wer(REFS[cid], text, "skeleton"), 4), s, d, i, n, int(bool(DEVANAGARI.search(text))), text])
    out = RESULTS / "wer_real_clips.csv"
    write_csv(out, ["model", "clip", "kind", "language_setting", "audio_s", "decode_s", "wer_strict", "wer_skeleton", "substitutions", "deletions",
                    "insertions", "ref_words", "output_has_devanagari", "text"], rows)
    write_meta(out, provider="live", model=[f"faster-whisper-{m}-int8" for m in args.models.split(",")], n=len(present), n_unit="real clips (Mayank, read aloud)",
               audio="real, read aloud, one speaker", note="one speaker, 5 English + 2 Hinglish: indicative only, not a sample of MSOT students")
    for model in sorted({r[0] for r in rows}):
        eng = [r[6] for r in rows if r[0] == model and r[2] == "english"]
        print(f"{model}: English WER mean {statistics.mean(eng):.3f} over {len(eng)} clips" if eng else f"{model}: no English clips")
        for lang in ("en", "hi", "auto"):
            hi = [r for r in rows if r[0] == model and r[2] == "hinglish" and r[3] == lang]
            if hi:
                print(f"   Hinglish language={lang}: strict {statistics.mean(r[6] for r in hi):.3f} skeleton {statistics.mean(r[7] for r in hi):.3f} Devanagari output in {sum(r[12] for r in hi)}/{len(hi)}")


if __name__ == "__main__":
    main()
