"""AI vs human marks. CSV columns: session_id,ai_total,human_total. Usage: python scripts/compare.py marks.csv"""
import csv
import math
import sys

rows = list(csv.DictReader(open(sys.argv[1])))
ai = [float(r["ai_total"]) for r in rows]
hu = [float(r["human_total"]) for r in rows]
n = len(rows)
gap = sum(abs(a - h) for a, h in zip(ai, hu)) / n
bias = sum(a - h for a, h in zip(ai, hu)) / n
ma, mh = sum(ai) / n, sum(hu) / n
den = math.sqrt(sum((a - ma) ** 2 for a in ai) * sum((h - mh) ** 2 for h in hu))
r = sum((a - ma) * (h - mh) for a, h in zip(ai, hu)) / den if den else float("nan")
print(f"n={n} mean_abs_gap={gap:.2f} bias(AI-human)={bias:+.2f} pearson_r={r:.3f}")
if n < 10:
    print("WARNING: spec requires >=10 vivas")
