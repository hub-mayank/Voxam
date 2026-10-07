"""Shared paths and helpers for the voice spike. Scripts run from the worktree root with the venv active."""
import csv
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.results_meta import write_meta  # noqa: E402,F401  (the repo's sidecar writer: provider mock|stub|live, model, date, git_sha, n)

SPIKE = ROOT / "spikes" / "voice"
DATA = SPIKE / "data"
CLIPS = DATA / "clips"        # Mayank's recordings (c01..c07), never in git
SYNTH = DATA / "synth"        # synthetic turns made with macOS `say`, never in git
MODELS = DATA / "models"
RESULTS = ROOT / "results" / "voice_spike"
SAMPLE_RATE = 16000


def now() -> float:
    return time.perf_counter()


def write_csv(path: Path, header: list, rows: list):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


def percentile(values, q):
    """Linear-interpolated percentile (q in 0..100) of a non-empty list."""
    v = sorted(values)
    if len(v) == 1:
        return v[0]
    k = (len(v) - 1) * q / 100
    lo = int(k)
    hi = min(lo + 1, len(v) - 1)
    return v[lo] + (v[hi] - v[lo]) * (k - lo)
