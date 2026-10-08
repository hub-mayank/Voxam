"""Scorer consistency: score each transcript N times and report how much the totals and dimensions move.
One scorer run per repeat (the same call the 3-run median is made of), so the spread here is the spread the median smooths out.
Writes results/consistency_<tag>.csv (every run) and results/consistency_<tag>_summary.csv (variance per transcript and dimension).
--llm mock (default) is plumbing only: the mock is deterministic, so its variance is 0 by construction and the result is labelled mock.
A real model needs --live, and every call goes through the free-tier budget (D18/D20): ask Mayank before a live run.
Usage: python scripts/consistency.py [--llm mock] [--runs 5] [--tag mock] [--live] [transcript.jsonl ...]   (default: backend/tests/personas/*.jsonl)"""
import argparse
import csv
import json
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.config import load_config  # noqa: E402
from app.envfile import load_env  # noqa: E402
from app.llm.factory import make_llm  # noqa: E402
from app.results_meta import write_meta  # noqa: E402
from app.scorer import SCORER_PROMPT_VERSION, build_transcript, score_once, total_of  # noqa: E402


def summarise(rows: list, keys: list) -> list:
    """Per run rows -> one summary row per transcript: n, mean/sd/min/max/range of the total, and the sd of each dimension.
    sd is the sample standard deviation (0 for a single run)."""
    out = []
    for name in dict.fromkeys(r["transcript"] for r in rows):
        mine = [r for r in rows if r["transcript"] == name]
        totals = [r["total"] for r in mine]
        sd = lambda values: round(statistics.stdev(values), 3) if len(values) > 1 else 0.0  # noqa: E731
        out.append({"transcript": name, "n_runs": len(mine), "mean_total": round(statistics.mean(totals), 2), "sd_total": sd(totals),
                    "min_total": min(totals), "max_total": max(totals), "range_total": round(max(totals) - min(totals), 2),
                    **{f"sd_{k}": sd([r[k] for r in mine]) for k in keys}})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("transcripts", nargs="*")
    ap.add_argument("--llm", default="mock")
    ap.add_argument("--runs", type=int, default=5)
    ap.add_argument("--tag", default=None, help="file name tag (default: the --llm value)")
    ap.add_argument("--live", action="store_true", help="required for anything but mock: real provider calls, counted by the budget")
    a = ap.parse_args()
    if a.llm != "mock" and not a.live:
        sys.exit("a real model makes live provider calls: pass --live (and ask Mayank first); the free-tier budget still applies")
    load_env()
    cfg = load_config(ROOT / "config" / "viva.config.json")
    keys = [d["key"] for d in cfg.rubric["dimensions"]]
    llm = make_llm(a.llm)
    paths = [Path(p) for p in a.transcripts] or sorted((ROOT / "backend" / "tests" / "personas").glob("*.jsonl"))
    rows = []
    for path in paths:
        events = [json.loads(line) for line in open(path) if line.strip()]
        transcript = build_transcript(events)
        for run in range(1, a.runs + 1):
            raw, errors = score_once(llm, cfg, transcript)
            rows.append({"transcript": path.stem, "run": run, "total": total_of(raw["dimensions"], cfg),
                         **{k: raw["dimensions"][k]["score"] for k in keys}, "retries": len(errors), "model": llm.name})
    tag = a.tag or a.llm.replace("/", "_").replace(":", "_").replace(",", "+")
    out = ROOT / "results" / f"consistency_{tag}.csv"
    summary = ROOT / "results" / f"consistency_{tag}_summary.csv"
    out.parent.mkdir(exist_ok=True)
    with open(out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    stats = summarise(rows, keys)
    with open(summary, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(stats[0]))
        w.writeheader()
        w.writerows(stats)
    provider = "mock" if a.llm == "mock" else "live"
    note = {"mock": "mock scorer is deterministic: variance 0 by construction; proves plumbing, not scorer consistency"}.get(provider, "")
    for path in (out, summary):
        write_meta(path, provider=provider, model=llm.name, n=len(rows), n_unit="scorer runs", runs_per_transcript=a.runs,
                   transcripts=[p.stem for p in paths], scorer_prompt_version=SCORER_PROMPT_VERSION, note=note)
    for s in stats:
        print(f"{s['transcript']:16} n={s['n_runs']} mean={s['mean_total']:6} sd={s['sd_total']} range={s['range_total']}")
    print(f"wrote {out.relative_to(ROOT)} and {summary.relative_to(ROOT)} (provider={provider})")


if __name__ == "__main__":
    main()
