"""WER on the 7 real clips (Mayank's voice) for each faster-whisper size, plus the Hinglish language-setting question.
English clips: language forced to en. Hinglish clips: tried with language=en (Roman output expected), language=hi (Devanagari output expected) and auto.
Reports `strict` WER and, for Hinglish, `skeleton` WER (see wer.py for what each means). Skips quietly if the clips are not there yet.
Engines: faster-whisper int8 on CPU (base, small, medium) and whisper.cpp q5_1 with Metal (base, small), plus Groq whisper-large-v3-turbo with --groq.
Usage: python spikes/voice/bench_wer.py [--models base,small,medium] [--cpp base,small] [--groq]"""
import argparse
import statistics
import subprocess

import soundfile as sf

from clip_refs import HINGLISH, REFS, TERMS
from common import CLIPS, RESULTS, write_csv, write_meta
from stt_cpp import WhisperCpp
from stt_fw import FasterWhisper
from wer import DEVANAGARI, counts, normalize, skeleton, wer


def term_recall(cid, text):
    """Share of the clip's technical terms found in the transcript (spelling-tolerant: compared by consonant skeleton, after Devanagari -> Roman)."""
    have = {skeleton(w) for w in normalize(text).split()}
    found = [t for t in TERMS[cid] if all(skeleton(w) in have for w in normalize(t).split())]
    return len(found) / len(TERMS[cid])


def max_repeat(text, n=3):
    """Most times any word n-gram repeats: a decoding loop shows up as a large number."""
    words = normalize(text).split()
    grams = [tuple(words[i:i + n]) for i in range(len(words) - n + 1)]
    return max((grams.count(g) for g in set(grams)), default=0)


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
    ap.add_argument("--cpp", default="base,small", help="whisper.cpp sizes (q5_1, Metal); empty to skip")
    ap.add_argument("--groq", action="store_true", help="also call Groq whisper-large-v3-turbo (free tier: counts against the budget)")
    args = ap.parse_args()
    clips = {c: wav_for(c) for c in REFS}
    present = {c: a for c, a in clips.items() if a is not None}
    if not present:
        raise SystemExit(f"no clips in {CLIPS}; see spikes/voice/RECORDING.md")
    print(f"{len(present)}/7 clips found: {sorted(present)}")
    rows = []
    engines = [("fw", FasterWhisper(size)) for size in args.models.split(",") if size]
    engines += [("cpp", WhisperCpp(size)) for size in args.cpp.split(",") if size]
    if args.groq:
        from stt_groq import GroqWhisper
        engines.append(("groq", GroqWhisper()))
    for kind, stt in engines:
        stt.transcribe(next(iter(present.values()))[:16000 * 3])  # warm-up, not recorded
        for cid, audio in sorted(present.items()):
            langs = ["en", "hi", None] if cid in HINGLISH else ["en"]
            for lang in langs:
                if lang:
                    text, secs = stt.transcribe(audio, language=lang)
                elif kind == "fw":
                    text, secs = stt.transcribe_auto(audio)
                else:
                    text, secs = stt.transcribe(audio, language="auto")
                s, d, i, n = counts(REFS[cid], text)
                rows.append([stt.name, cid, "hinglish" if cid in HINGLISH else "english", lang or "auto", round(len(audio) / 16000, 1), round(secs, 2),
                             round(wer(REFS[cid], text), 4), round(wer(REFS[cid], text, "skeleton"), 4), s, d, i, n, int(bool(DEVANAGARI.search(text))), round(term_recall(cid, text), 3), max_repeat(text), text])
    out = RESULTS / "wer_real_clips.csv"
    write_csv(out, ["model", "clip", "kind", "language_setting", "audio_s", "decode_s", "wer_strict", "wer_skeleton", "substitutions", "deletions",
                    "insertions", "ref_words", "output_has_devanagari", "term_recall", "max_trigram_repeat", "text"], rows)
    write_meta(out, provider="live", model=sorted({r[0] for r in rows}), n=len(present), n_unit="real clips (Mayank, read aloud)",
               audio="real, read aloud, one speaker", note="one speaker, 5 English + 2 Hinglish: indicative only, not a sample of MSOT students")
    for model in sorted({r[0] for r in rows}):
        eng = [r[6] for r in rows if r[0] == model and r[2] == "english"]
        er = [r[13] for r in rows if r[0] == model and r[2] == "english"]
        print(f"{model}: English WER mean {statistics.mean(eng):.3f}, term recall {statistics.mean(er):.2f} over {len(eng)} clips" if eng else f"{model}: no English clips")
        for lang in ("en", "hi", "auto"):
            hi = [r for r in rows if r[0] == model and r[2] == "hinglish" and r[3] == lang]
            if hi:
                print(f"   Hinglish language={lang}: strict {statistics.mean(r[6] for r in hi):.3f} skeleton {statistics.mean(r[7] for r in hi):.3f} term recall {statistics.mean(r[13] for r in hi):.2f} loops {sum(r[14] >= 5 for r in hi)}/{len(hi)} Devanagari {sum(r[12] for r in hi)}/{len(hi)}")


if __name__ == "__main__":
    main()
