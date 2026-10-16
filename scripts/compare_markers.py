"""AI marks against one or two human markers (the "scoring accuracy" row of the test report).
Reads the markers' sheets (columns of docs/marking_sheet.csv, `session_id` holding the packet label P01...), the coordinator's
`_private/mapping.csv` from scripts/marking_packet.py, and the AI marks from the database (the median of the scorer runs, BEFORE any
faculty override). Checks each human total against the weighted formula, then reports, with n:
  - for each marker: mean absolute gap to the AI, signed bias (AI minus human) and Pearson correlation;
  - for the AI against the markers' average (when there are two);
  - the two markers against each other (their agreement is the ceiling for any AI);
  - per dimension: how often AI and human are within one point.
Writes results/accuracy_vs_human.csv with a sidecar. Names and session ids never appear in the output (labels only).
Usage: python scripts/compare_markers.py --mapping <_private/mapping.csv> --sheet vikas.csv --sheet devesh.csv [--out results/accuracy_vs_human.csv]"""
import argparse
import csv
import math
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app.db import models as m  # noqa: E402
from app.db.engine import make_engine  # noqa: E402
from app.envfile import load_env  # noqa: E402
from app.results_meta import write_meta  # noqa: E402
from app.services import core  # noqa: E402

KEYS = ["conceptual", "depth", "problem", "practical", "communication"]
WEIGHTS = [30, 25, 20, 15, 10]


def human_total(row) -> float:
    return sum(w * int(row[f"{k}_0_5"]) / 5 for k, w in zip(KEYS, WEIGHTS))


def read_sheet(path) -> dict:
    """label -> {dimension: int, total: float}. Rejects a missing or out-of-range rating and a total that disagrees with the formula."""
    rows, problems = {}, []
    for r in csv.DictReader(open(path, newline="")):
        label = r["session_id"].strip()
        if not label or not any((r[f"{k}_0_5"] or "").strip() for k in KEYS):
            continue  # an unrated row of the template
        try:
            ratings = {k: int(r[f"{k}_0_5"]) for k in KEYS}
        except ValueError:
            problems.append(f"{label}: every dimension needs a whole number")
            continue
        if any(not 0 <= v <= 5 for v in ratings.values()):
            problems.append(f"{label}: ratings must be 0 to 5")
            continue
        total = human_total(r)
        if (r.get("total_100") or "").strip() and abs(float(r["total_100"]) - total) > 0.51:
            problems.append(f"{label}: total_100 {r['total_100']} does not match the weighted formula ({total:g})")
        if label in rows:
            problems.append(f"{label}: rated twice in {path}")
        rows[label] = {**ratings, "total": total}
    if problems:
        sys.exit(f"{path}: " + "; ".join(problems))
    return rows


def pearson(a, b):
    if len(a) < 3:
        return float("nan")
    ma, mb = statistics.mean(a), statistics.mean(b)
    den = math.sqrt(sum((x - ma) ** 2 for x in a) * sum((y - mb) ** 2 for y in b))
    return sum((x - ma) * (y - mb) for x, y in zip(a, b)) / den if den else float("nan")


def stats(name, left, right, labels, what):
    a, b = [left[k] for k in labels], [right[k] for k in labels]
    n = len(labels)
    return {"comparison": name, "n": n, "mean_abs_gap": round(sum(abs(x - y) for x, y in zip(a, b)) / n, 2) if n else "",
            "bias_first_minus_second": round(sum(x - y for x, y in zip(a, b)) / n, 2) if n else "",
            "pearson_r": "" if n < 3 or math.isnan(pearson(a, b)) else round(pearson(a, b), 3), "note": what}


def ai_marks(mapping) -> tuple:
    load_env()
    with sessionmaker(make_engine())() as db:
        marks, dims, models = {}, {}, set()
        for label, sid in mapping.items():
            sess = db.get(m.Session, sid)
            viva = db.get(m.Viva, sess.viva_id)
            rows = list(db.scalars(select(m.Score).where(m.Score.session_id == sess.id)))
            scoring, _, _ = core.aggregate_scores(rows, viva.config["rubric"]["dimensions"])
            if scoring is None:
                continue
            models |= {r.model for r in rows}
            marks[label] = scoring.median_total
            dims[label] = {d.key: d.score for d in scoring.dimensions}
        return marks, dims, models


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--mapping", required=True, type=Path)
    ap.add_argument("--sheet", action="append", required=True, type=Path, help="one marker's sheet; give it twice for two markers")
    ap.add_argument("--out", type=Path, default=ROOT / "results" / "accuracy_vs_human.csv")
    a = ap.parse_args()
    mapping = {r["label"]: r["session_id"] for r in csv.DictReader(open(a.mapping))}
    sheets = [read_sheet(p) for p in a.sheet]
    unknown = {k for s in sheets for k in s} - set(mapping)
    if unknown:
        sys.exit(f"labels not in the mapping: {sorted(unknown)}")
    import uuid
    ai_total, ai_dims, models = ai_marks({k: uuid.UUID(v) for k, v in mapping.items()})
    rows = []
    for i, sheet in enumerate(sheets, start=1):
        labels = sorted(set(sheet) & set(ai_total))
        rows.append(stats(f"AI vs marker {i}", ai_total, {k: v["total"] for k, v in sheet.items()}, labels, "AI before any override"))
    if len(sheets) == 2:
        both = sorted(set(sheets[0]) & set(sheets[1]))
        mean = {k: (sheets[0][k]["total"] + sheets[1][k]["total"]) / 2 for k in both}
        rows.append(stats("AI vs mean of the two markers", ai_total, mean, sorted(set(both) & set(ai_total)), "the fairest single human reference"))
        rows.append(stats("marker 1 vs marker 2", {k: sheets[0][k]["total"] for k in both}, {k: sheets[1][k]["total"] for k in both}, both,
                          "inter-marker agreement: the practical ceiling for the AI"))
    for k in KEYS:
        for i, sheet in enumerate(sheets, start=1):
            labels = sorted(set(sheet) & set(ai_dims))
            within = sum(abs(ai_dims[x][k] - sheet[x][k]) <= 1 for x in labels)
            rows.append({"comparison": f"{k}: AI within 1 point of marker {i}", "n": len(labels),
                         "mean_abs_gap": round(sum(abs(ai_dims[x][k] - sheet[x][k]) for x in labels) / len(labels), 2) if labels else "",
                         "bias_first_minus_second": "", "pearson_r": "", "note": f"{within} of {len(labels)} within one point"})
    a.out.parent.mkdir(parents=True, exist_ok=True)
    with open(a.out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    provider = "mock" if models <= {"mock"} else "live"
    write_meta(a.out, provider=provider, model=sorted(models) or ["none"], n=len(ai_total), n_unit="sessions marked by humans", markers=len(sheets),
               note="AI marks are the scorer's median before faculty overrides; human totals follow the rubric weights; labels only, no names")
    for r in rows[: len(sheets) + (2 if len(sheets) == 2 else 0)]:
        print(f"{r['comparison']:34} n={r['n']:<3} gap={r['mean_abs_gap']} bias={r['bias_first_minus_second']} r={r['pearson_r']}")
    print(f"wrote {a.out} ({provider}); {len(ai_total)} AI-scored of {len(mapping)} packets")


if __name__ == "__main__":
    main()
