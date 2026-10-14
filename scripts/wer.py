"""TJ-6: --refs clip,kind,reference[,audio_path,language_setting,speaker_id]; kind=english|hinglish.
Use --hypotheses (clip,text) --model LABEL, or --local (whisper.cpp; mono PCM16 16-kHz WAV).
Existing prerequisites: jiwer + indic-transliteration. Offline defaults to stub; skeleton WER can hide errors.
"""
import argparse
import csv
import hashlib
import importlib.util
import io
import re
import sys
import tempfile
import time
import wave
from dataclasses import replace
from functools import lru_cache
from pathlib import Path
from subprocess import SubprocessError

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.results_meta import meta_path, write_meta  # noqa: E402

NORMALIZER = ROOT / "spikes" / "voice" / "wer.py"


@lru_cache(maxsize=1)
def normalization():
    spec = importlib.util.spec_from_file_location("_voxam_spike_wer", NORMALIZER)
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except ImportError as error:
        raise ValueError("WER needs the existing spike libraries: pip install 'jiwer>=3' 'indic-transliteration>=2.3'") from error
    return module


def read_csv(path: Path, required: set, data=None) -> list[dict]:
    reader = csv.DictReader(io.StringIO((data or path.read_bytes()).decode("utf-8-sig")), strict=True)
    header = reader.fieldnames or []
    if not required <= set(header) or len(set(header)) != len(header) or any(not k.strip() for k in header):
        raise ValueError(f"{path}: missing or duplicate CSV columns; required: {sorted(required)}")
    rows = list(reader)
    if not rows or any(None in row or any(v is None for v in row.values()) for row in rows):
        raise ValueError(f"{path}: empty or malformed CSV rows")
    ids = [r["clip"].strip() for r in rows]
    if len(set(ids)) != len(ids) or any(not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}", k) for k in ids):
        raise ValueError(f"{path}: clip IDs must be unique nonempty identifiers")
    return [{k: v.strip() for k, v in r.items()} for r in rows]


def read_refs(path: Path, data=None) -> list[dict]:
    refs = read_csv(path, {"clip", "kind", "reference"}, data)
    for ref in refs:
        if ref["kind"] not in ("english", "hinglish") or ref.get("language_setting", "en") not in ("", "en", "hi", "auto"):
            raise ValueError("reference kind must be english/hinglish; language_setting must be en/hi/auto")
        if not ref["reference"] or not normalization().normalize(ref["reference"]):
            raise ValueError(f"{ref['clip']}: empty reference after normalization")
    return refs


def read_hypotheses(path: Path, data=None) -> dict[str, str]:
    return {r["clip"]: r["text"] for r in read_csv(path, {"clip", "text"}, data)}


def compare(refs: list[dict], hypotheses: dict[str, str]) -> list[dict]:
    expected = {r["clip"] for r in refs}
    if set(hypotheses) != expected:
        raise ValueError(f"hypothesis coverage differs: missing={sorted(expected-set(hypotheses))}, unknown={sorted(set(hypotheses)-expected)}")
    helper, rows = normalization(), []
    for ref in refs:
        text = hypotheses[ref["clip"]]
        s, d, i, n = helper.counts(ref["reference"], text)
        if not n:
            raise ValueError(f"{ref['clip']}: empty normalized reference")
        rows.append({"clip": ref["clip"], "kind": ref["kind"], "language_setting": ref.get("language_setting") or "en",
                     "wer_strict": (s+d+i)/n, "wer_skeleton": helper.wer(ref["reference"], text, "skeleton"),
                     "substitutions": s, "deletions": d, "insertions": i, "ref_words": n,
                     "reference": ref["reference"], "text": text})
    return rows


def recognize(refs: list[dict], language: str) -> tuple[dict, dict]:
    from app.voice.config import VoiceConfig
    from app.voice.local import WhisperCppSTT
    clips = []
    for ref in refs:
        if not ref.get("audio_path"):
            raise ValueError(f"{ref['clip']}: audio_path is required for local recognition")
        path = Path(ref["audio_path"])
        data = path.read_bytes()
        with wave.open(io.BytesIO(data), "rb") as source:
            if (source.getnchannels(), source.getsampwidth(), source.getframerate(), source.getcomptype()) != (1, 2, 16000, "NONE") or not source.getnframes():
                raise ValueError(f"{path}: expected nonempty mono PCM16 16-kHz WAV")
            pcm = source.readframes(source.getnframes())
            if len(pcm) != source.getnframes()*2:
                raise ValueError(f"{path}: truncated WAV payload")
            clips.append((ref, pcm, hashlib.sha256(data).hexdigest()))
    hypotheses, extra, adapters = {}, {}, {}
    cfg = VoiceConfig.from_env()
    for ref, pcm, digest in clips:
        lang = ref.get("language_setting") or language
        if lang not in adapters:
            adapters[lang] = WhisperCppSTT(replace(cfg, whisper_lang=lang))
        started = time.perf_counter()
        text, confidence = adapters[lang].transcribe(pcm)
        extra[ref["clip"]] = {"model": adapters[lang].name, "decode_s": time.perf_counter()-started,
                              "audio_s": len(pcm)/32000, "stt_confidence": confidence, "audio_sha256": digest}
        hypotheses[ref["clip"]] = text
    return hypotheses, extra


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--refs", type=Path, default=ROOT / "evidence" / "wer" / "refs.csv")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--hypotheses", type=Path)
    mode.add_argument("--local", action="store_true")
    parser.add_argument("--model", help="required recognizer label for saved hypotheses; not a new live run")
    parser.add_argument("--provider", choices=("mock", "stub"), help="offline input provenance, default stub")
    parser.add_argument("--language", choices=("en", "hi", "auto"), default="en")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    try:
        if args.hypotheses and not (args.model and args.model.strip()):
            raise ValueError("--model is required for saved hypotheses")
        if args.local and (args.model or args.provider):
            raise ValueError("local recognition uses the actual adapter model and provider=live")
        out = (args.out or ROOT / "results" / ("wer_local.csv" if args.local else "wer_offline.csv")).resolve()
        inputs = [args.refs.resolve(), NORMALIZER.resolve()] + ([args.hypotheses.resolve()] if args.hypotheses else [])
        if out.suffix != ".csv" or out in inputs or meta_path(out) in inputs:
            raise ValueError("output must be a CSV distinct from inputs")
        if any(p.exists() and not p.is_file() for p in (out, meta_path(out))):
            raise ValueError("output CSV and sidecar must be regular files")
        refs_data = args.refs.read_bytes()
        refs = read_refs(args.refs, refs_data)
        for ref in refs:
            ref["language_setting"] = ref.get("language_setting") or args.language
            if ref.get("audio_path") and not Path(ref["audio_path"]).is_absolute():
                ref["audio_path"] = str(args.refs.parent / ref["audio_path"])
        meta = {"mode": "local" if args.local else "offline", "refs_sha256": hashlib.sha256(refs_data).hexdigest(),
                "normalization": "spike-v1", "normalization_sha256": hashlib.sha256(NORMALIZER.read_bytes()).hexdigest(),
                "audio": "input type and volunteer consent not verified",
                "note": "Strict WER is primary; skeleton WER forgives spelling and can hide errors. " + ("Local recognition was run; consent and input type need verification." if args.local else "Offline comparison, not a new recognition run.")}
        if args.local:
            hypotheses, extra = recognize(refs, args.language)
            provider, model = "live", sorted({v["model"] for v in extra.values()})
            meta["audio_sha256"] = {clip: v.pop("audio_sha256") for clip, v in extra.items()}
        else:
            data = args.hypotheses.read_bytes()
            hypotheses, extra = read_hypotheses(args.hypotheses, data), {}
            provider, model = args.provider or "stub", args.model.strip()
            meta["hypotheses_sha256"] = hashlib.sha256(data).hexdigest()
        rows = [{"model": model if isinstance(model, str) else extra[r["clip"]]["model"], **r, **extra.get(r["clip"], {})} for r in compare(refs, hypotheses)]
        out.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=out.parent) as directory:
            temporary = Path(directory) / out.name
            with temporary.open("w", encoding="utf-8", newline="") as target:
                writer = csv.DictWriter(target, fieldnames=list(rows[0]))
                writer.writeheader()
                writer.writerows(rows)
            write_meta(temporary, provider=provider, model=model, n=len(refs), n_unit="unique clips", **meta)
            destinations = [(temporary, out), (meta_path(temporary), meta_path(out))]
            previous = [(p, p.read_bytes() if p.exists() else None) for _, p in destinations]
            try:
                for source, target in destinations:
                    source.replace(target)
            except OSError:
                for target, data in previous:
                    if data is None:
                        target.unlink(missing_ok=True)
                    else:
                        target.write_bytes(data)
                raise
        for kind, lang in sorted({(r["kind"], r["language_setting"]) for r in rows}):
            selected = [r for r in rows if (r["kind"], r["language_setting"]) == (kind, lang)]
            if selected:
                rate = sum(r["substitutions"]+r["deletions"]+r["insertions"] for r in selected)/sum(r["ref_words"] for r in selected)
                print(f"{kind}/{lang}: {len(selected)} unique clips; word-weighted strict WER={rate:.4f}")
        print(f"Wrote {out} and {meta_path(out)} (provider={provider}); TJ-3 requires at least 10 English and 10 Hinglish consented clips.")
    except (OSError, ValueError, TypeError, csv.Error, wave.Error, EOFError, SubprocessError, RuntimeError) as error:
        parser.exit(1, f"Cannot evaluate WER: {str(error) or 'invalid or truncated input'}\n")


if __name__ == "__main__":
    main()
