"""Download the model weights the spike needs (Hugging Face and GitHub releases only; ~2.5 GB in total).
Everything lands in spikes/voice/data/models/ (gitignored). Writes results/voice_spike/models_manifest.csv.
Usage: python spikes/voice/fetch_models.py [--skip-medium]"""
import csv
import hashlib
import sys
from pathlib import Path

import httpx
from huggingface_hub import hf_hub_download, snapshot_download

from common import MODELS, RESULTS, write_meta

KOKORO_BASE = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/"
PIPER_REPO = "rhasspy/piper-voices"
PIPER_VOICES = ["en/en_US/lessac/medium/en_US-lessac-medium", "en/en_GB/alba/medium/en_GB-alba-medium", "hi/hi_IN/rohan/medium/hi_IN-rohan-medium"]


def size_of(path: Path) -> int:
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file()) if path.is_dir() else path.stat().st_size


def main():
    MODELS.mkdir(parents=True, exist_ok=True)
    rows = []
    whisper = ["small"] + ([] if "--skip-medium" in sys.argv else ["medium"])
    for name in whisper:
        path = Path(snapshot_download(f"Systran/faster-whisper-{name}", local_dir=MODELS / f"faster-whisper-{name}"))
        rows.append((f"faster-whisper-{name}", f"https://huggingface.co/Systran/faster-whisper-{name}", size_of(path)))
    for voice in PIPER_VOICES:
        for ext in (".onnx", ".onnx.json"):
            p = Path(hf_hub_download(PIPER_REPO, voice + ext, local_dir=MODELS / "piper"))
            rows.append((p.name, f"https://huggingface.co/{PIPER_REPO}/blob/main/{voice}{ext}", size_of(p)))
    for fname in ("kokoro-v1.0.onnx", "voices-v1.0.bin"):
        dest = MODELS / "kokoro" / fname
        dest.parent.mkdir(exist_ok=True)
        if not dest.exists():
            with httpx.stream("GET", KOKORO_BASE + fname, follow_redirects=True, timeout=120) as r:
                r.raise_for_status()
                with open(dest, "wb") as f:
                    for chunk in r.iter_bytes(1 << 20):
                        f.write(chunk)
        rows.append((fname, KOKORO_BASE + fname, size_of(dest)))
    RESULTS.mkdir(parents=True, exist_ok=True)
    out = RESULTS / "models_manifest.csv"
    with open(out, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["model", "source_url", "size_bytes"])
        w.writerows(rows)
    write_meta(out, provider="live", model="n/a (download manifest)", n=len(rows), n_unit="files")
    total = sum(r[2] for r in rows)
    for r in rows:
        print(f"{r[2] / 1e6:9.1f} MB  {r[0]}")
    print(f"total {total / 1e9:.2f} GB")
    assert total < 3e9, "over the 3 GB download budget"


if __name__ == "__main__":
    main()
