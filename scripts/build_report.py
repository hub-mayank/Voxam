"""TJ-7: build an evidence-backed Markdown Test Report without provider calls or dependencies.

Run from any directory: python scripts/build_report.py [--results-dir results] [--out evidence/TEST_REPORT.md]
Each evidence row links its data and metadata; coverage candidates are not certified requirement passes.
"""
import argparse
import csv
import html
import json
import math
import os
import statistics
import sys
import tempfile
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.results_meta import check_meta_dict, meta_path, result_files  # noqa: E402

METRICS = "server_latency_ms client_latency_ms latency_ms e2e_s e2e_sequential_streamed_s decode_s batch_decode_s first_chunk_s first_audio_s total_s stt_ms decode_p50_s decode_p95_s e2e_p50_s e2e_p95_s wer wer_strict wer_skeleton wer_batch wer_segmented sd_total tokens_total".split()
GROUPS = "model engine kind language_setting mode hangover_ms concurrent_decodes llm_profile_assumed transcript".split()
CANDIDATES = {
    "Functional": ("voice_e2e_", "voice_bot_", "functional_"), "Follow-up quality": ("followup_", "follow_up_"),
    "Scoring accuracy": ("scoring_accuracy_", "compare_"), "Scoring consistency": ("consistency_",),
    "Speech accuracy": ("wer_",), "Latency": ("voice_e2e_", "voice_handsfree_", "e2e_", "latency_"),
    "Robustness": ("robustness_",), "Fairness and safety": ("fairness_", "safety_",), "Audit": ("audit_",),
}


def cell(value):
    if isinstance(value, (dict, list)):
        value = json.dumps(value, ensure_ascii=False, sort_keys=True)
    return html.escape(str(value), quote=False).replace("\\", "\\\\").replace("|", "\\|").replace("[", "\\[").replace("]", "\\]").replace("\n", " ").replace("\r", " ")


def link(path, out):
    return f"[{cell(path.name)}]({quote(Path(os.path.relpath(path, out.parent)).as_posix(), safe='/')})"


def read_result(path):
    meta = json.loads(meta_path(path).read_text(encoding="utf-8"))
    problems = check_meta_dict(meta)
    if problems:
        raise ValueError(f"{meta_path(path)}: {'; '.join(problems)}")
    if path.suffix.lower() != ".csv":
        raise ValueError(f"{path}: unsupported result format (expected CSV)")
    with path.open(encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source, strict=True)
        header = reader.fieldnames or []
        if not header or len(set(header)) != len(header) or any(not h.strip() for h in header):
            raise ValueError(f"{path}: empty or duplicate CSV header")
        rows = list(reader)
    if not rows or any(None in row or any(v is None for v in row.values()) for row in rows):
        raise ValueError(f"{path}: empty or malformed CSV rows")
    return meta, rows


def numbers(rows, column):
    values = [float(r[column]) for r in rows if r[column].strip() not in ("", "None")]
    if any(not math.isfinite(v) for v in values):
        raise ValueError(f"{column}: nonfinite numeric value")
    return values


def summarize(rows):
    summaries = []
    for column in METRICS:
        if column not in rows[0]:
            continue
        values = sorted(numbers(rows, column))
        if not values:
            continue
        if column.startswith("wer") or column == "sd_total" or "_p50_" in column or "_p95_" in column:
            text = f"{column}: n={len(values)} recorded range={values[0]:g}..{values[-1]:g}"
        else:
            text = f"{column}: n={len(values)} p50={statistics.median(values):g} p95={values[min(len(values)-1, int(.95*len(values)))]:g}"
        summaries.append(text)
    if {"substitutions", "deletions", "insertions", "ref_words"} <= rows[0].keys():
        counts = {k: numbers(rows, k) for k in ("substitutions", "deletions", "insertions", "ref_words")}
        if any(len(v) != len(rows) or any(x < 0 or not x.is_integer() for x in v) for v in counts.values()) or sum(counts["ref_words"]) <= 0:
            raise ValueError("WER requires nonnegative integer error counts and a positive reference word count")
        errors = sum(sum(counts[k]) for k in ("substitutions", "deletions", "insertions"))
        summaries.append(f"word-weighted strict WER={errors/sum(counts['ref_words']):g}")
    if "clip" in rows[0]:
        summaries.append(f"unique clips={len({r['clip'] for r in rows})}")
    if "error" in rows[0]:
        summaries.append(f"rows with error={sum(bool(r['error'].strip()) for r in rows)}")
    if {"transcript", "run", "total"} <= rows[0].keys():
        totals = numbers(rows, "total")
        if totals:
            summaries.append(f"total: n={len(totals)} sample variance={statistics.variance(totals) if len(totals) > 1 else 0:g}")
    if {"worker", "jobs_claimed"} <= rows[0].keys():
        for r in rows:
            if r["worker"] in ("TOTAL", "duplicate_claims", "jobs_never_claimed"):
                value = numbers([r], "jobs_claimed")
                if len(value) != 1:
                    raise ValueError("missing job-claim summary")
                summaries.append(f"{r['worker']}={value[0]:g}")
    return "; ".join(summaries) or "No recognized metric; inspect the cited CSV."


def qualifiers(meta, path):
    text = json.dumps(meta).lower()
    notes = []
    if meta["provider"] in ("mock", "stub"):
        notes.append("mock/stub: plumbing or assumptions, not model-quality proof")
    elif "mock" in text or "simulated" in str(meta.get("llm_leg", "")).lower():
        notes.append("mixed components: contains mock or simulated work")
    if "synthetic" in str(meta.get("audio", "")).lower() or "/synth" in str(meta.get("speech_dir", "")).lower():
        notes.append("synthetic input; not volunteer evidence")
    if "+dirty" in meta["git_sha"]:
        notes.append("recorded with uncommitted source changes")
    if "streaming" in path.stem:
        notes.append("recorded streamed latency requires first-audio instrumentation review")
    extra = {k: v for k, v in meta.items() if k not in ("provider", "model", "date", "git_sha", "n", "n_unit")}
    if extra:
        notes.append(cell(extra))
    return "; ".join(notes) or "No additional qualifiers supplied."


def build_report(results_dir: Path, out: Path) -> str:
    results_dir, out = Path(results_dir).resolve(), Path(out).resolve()
    if not results_dir.is_dir():
        raise ValueError(f"results directory not found: {results_dir}")
    if out == results_dir or results_dir in out.parents:
        raise ValueError("report output must be outside the results directory")
    paths = result_files(results_dir)
    if not paths:
        raise ValueError("no result files found")
    loaded = []
    for path in paths:
        try:
            meta, rows = read_result(path)
            grouping = [k for k in GROUPS if k in rows[0]]
            groups = defaultdict(list)
            for row in rows:
                groups[tuple(row[k] for k in grouping)].append(row)
            summaries = [(dict(zip(grouping, key)), summarize(group)) for key, group in sorted(groups.items())]
            loaded.append((path, meta, rows, summaries))
        except (OSError, ValueError, TypeError, csv.Error) as error:
            raise ValueError(f"{path}: {error}") from error
    counts = Counter(meta["provider"] for _, meta, _, _ in loaded)
    lines = ["# Voxam Test Report", "", "Generated from validated result files and metadata. This is an evidence inventory, not certification that all submission requirements pass.", "",
             f"Files: {len(loaded)}; CSV rows: {sum(len(rows) for _, _, rows, _ in loaded)}; provider labels: {dict(sorted(counts.items()))}.", "",
             "Reported n and its unit come from sidecars and may differ from CSV row counts. A live label can include synthetic speech, a mock LLM, or derived/composed results; retain all qualifiers.", "",
             "## Evidence and provenance", "", "| Data | Sidecar | Provider | Model | Date / source commit | Rows / reported n | Qualifiers |", "|---|---|---|---|---|---|---|"]
    for path, meta, rows, _ in loaded:
        lines.append(f"| {link(path, out)} | {link(meta_path(path), out)} | {meta['provider']} | {cell(meta['model'])} | {cell(meta['date'])} / {cell(meta['git_sha'])} | rows={len(rows)}; reported n={meta['n']} {cell(meta.get('n_unit', '(unit not supplied)'))} | {qualifiers(meta, path)} |")
    lines += ["", "## Recorded metrics", "", "Columns keep their CSV units (ms, s, dimension points or WER ratio). Groups are separated by available model, engine, language, mode, concurrency and transcript fields. Blanks are excluded and metric n counts populated values.", "",
              "p50 is the median; p95 selects sorted[min(n-1, floor(0.95*n))], matching voice_bot.py. Ranges of stored percentile/variance/WER columns are not new pooled percentiles. WER from error counts is word-weighted within each group. These are historical recorded values, not fresh benchmarks or proof of browser playback latency.", "",
              "| Data | Sidecar | Provider | Group | Recorded summary |", "|---|---|---|---|---|"]
    for path, meta, _, summaries in loaded:
        for group, summary in summaries:
            lines.append(f"| {link(path, out)} | {link(meta_path(path), out)} | {meta['provider']} | {cell(group) if group else 'all stored rows'} | {cell(summary)} |")
    spec = ROOT / "docs" / "SPEC.md"
    lines += ["", "## Submission evidence and gaps requiring review", "", f"Requirements from {link(spec, out)}. Candidate files are selected by name for navigation only: their presence, thresholds, consent, and validity require human review.", "",
              "| Area | Required evidence (SPEC) | Candidate CSVs |", "|---|---|---|"]
    section = spec.read_text().split("## Test report (mandatory", 1)[1].split("## Scalability", 1)[0]
    for row in section.splitlines():
        cells = [c.strip() for c in row.strip("|").split("|")]
        if not row.startswith("| ") or len(cells) != 3 or cells[0] == "Area":
            continue
        matches = [p for p in paths if p.name.startswith(CANDIDATES.get(cells[0], ()))]
        sources = ", ".join(f"{link(p, out)} + {link(meta_path(p), out)}" for p in matches) or "Missing matching result artifact; not demonstrated by this inventory."
        lines.append(f"| {cell(cells[0])} | {cell(cells[1] + '; ' + cells[2])} | {sources} |")
    lines += ["", "Full-viva concurrency, cost, human marking, consented demo recordings and replay screenshots must be supplied separately. STT-only concurrency, queue claims and capacity arithmetic do not prove a full-viva load test. Mock consistency does not prove live consistency or fairness.", ""]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results-dir", type=Path, default=ROOT / "results")
    parser.add_argument("--out", type=Path, default=ROOT / "evidence" / "TEST_REPORT.md")
    args = parser.parse_args()
    temporary = None
    try:
        content = build_report(args.results_dir, args.out)
        out = args.out.resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=out.parent, delete=False) as target:
            temporary = Path(target.name)
            target.write(content)
        temporary.replace(out)
    except (OSError, ValueError, TypeError, IndexError, csv.Error) as error:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        parser.exit(1, f"Cannot build report: {error}\n")
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()
