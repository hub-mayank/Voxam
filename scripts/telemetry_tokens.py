"""Per-call tokens and latency from telemetry logs (the JSONL that app.telemetry writes), for the calls of one provider and model.
Writes a CSV (kind, tokens_in, tokens_out, tokens_total, latency_ms) and a .meta.json sidecar, and prints mean/max tokens per kind.
Usage: python scripts/telemetry_tokens.py LOG.jsonl [LOG2.jsonl ...] --provider groq --out results/groq_interview_tokens.csv"""
import argparse
import csv
import json
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.results_meta import write_meta  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("logs", nargs="+")
ap.add_argument("--provider", required=True)
ap.add_argument("--out", required=True)
a = ap.parse_args()

rows = []
for log in a.logs:
    for line in Path(log).read_text().splitlines():
        r = json.loads(line)
        if r["provider"] == a.provider and r["status"] == "ok" and r.get("tokens_in") is not None and r.get("tokens_out") is not None:
            rows.append({"kind": r["kind"], "model": r["model"], "tokens_in": r["tokens_in"], "tokens_out": r["tokens_out"],
                         "tokens_total": r["tokens_in"] + r["tokens_out"], "latency_ms": round(r["latency_ms"])})
if not rows:
    sys.exit("no matching calls with token counts")
out = Path(a.out)
out.parent.mkdir(parents=True, exist_ok=True)
with open(out, "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0]))
    w.writeheader()
    w.writerows(rows)
write_meta(out, provider="live", model=sorted({r["model"] for r in rows}), n=len(rows), n_unit="calls", source_logs=[Path(p).name for p in a.logs],
           note="tokens as reported by the provider's usage field for live-interview calls (classify, phrase) of the voice end-to-end runs")
for kind in sorted({r["kind"] for r in rows}):
    t = [r["tokens_total"] for r in rows if r["kind"] == kind]
    print(f"{kind}: n={len(t)} mean tokens/call={statistics.mean(t):.0f} max={max(t)}")
print(f"all: n={len(rows)} mean tokens/call={statistics.mean(r['tokens_total'] for r in rows):.0f}")
