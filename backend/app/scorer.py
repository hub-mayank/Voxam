"""Post-session scorer. Runs on the full transcript, never live. Code validates; LLM only proposes."""
import re
import statistics
from pathlib import Path

from .config import VivaConfig
from .llm.budget import CallCapExceeded
from .llm.errors import ProviderError

PROMPT_DIR = Path(__file__).parent / "prompts"
SCORER_PROMPT_VERSION = "scorer-v3"


def load_prompt(version: str) -> str:
    """The scorer prompt text lives in prompts/<version>.txt. Change the text, bump the version (a test pins each file's hash)."""
    return (PROMPT_DIR / f"{version}.txt").read_text().rstrip("\n")


RULES = load_prompt(SCORER_PROMPT_VERSION)


def build_transcript(events):
    """Spoken turns only, indexed. Returns list of {idx,t,phase,speaker,text,question_id}."""
    out = []
    for e in events:
        if e.get("role") in ("ai", "student") and e.get("text"):
            out.append({"idx": len(out), "t": e["t"], "phase": e.get("phase"),
                        "speaker": "AI" if e["role"] == "ai" else "STUDENT",
                        "text": e["text"], "question_id": e.get("question_id"),
                        "t_start_ms": e.get("t_start_ms"), "stt_confidence": e.get("stt_confidence")})
    return out


def _system(cfg: VivaConfig):
    dims = "\n".join(f"- {d['key']} (weight {d['weight']}%): 5/5 means: {d['five_means']}"
                     for d in cfg.rubric["dimensions"])
    return f"{RULES}\nDIMENSIONS:\n{dims}"


def _user(transcript):
    lines = [f"[{t['idx']}] (t={t['t']}s, {t['phase']}) {t['speaker']}: {t['text']}" for t in transcript]
    return "TRANSCRIPT:\n" + "\n".join(lines)


class ScoreError(ValueError):
    pass


def validate(raw, cfg: VivaConfig, transcript):
    """Reject anything malformed or any citation that doesn't exist / isn't a student turn."""
    student = {t["idx"] for t in transcript if t["speaker"] == "STUDENT"}
    if not isinstance(raw, dict) or "dimensions" not in raw or "feedback" not in raw:
        raise ScoreError("missing dimensions/feedback")
    keys = [d["key"] for d in cfg.rubric["dimensions"]]
    dims = raw["dimensions"]
    if set(dims) != set(keys):
        raise ScoreError(f"dimension keys {sorted(dims)} != {sorted(keys)}")
    for k, d in dims.items():
        s = d.get("score")
        if not isinstance(s, (int, float)) or isinstance(s, bool) or not 0 <= s <= 5:
            raise ScoreError(f"{k}: bad score {s!r}")
        ev = d.get("evidence", [])
        if not isinstance(d.get("reason"), str) or not d["reason"].strip():
            raise ScoreError(f"{k}: empty reason")
        if s > 0 and not ev:
            raise ScoreError(f"{k}: score>0 needs evidence")
        bad = [i for i in ev if i not in student]
        if bad:
            raise ScoreError(f"{k}: evidence turns not student turns/nonexistent: {bad}")
    fb = raw["feedback"]
    if not isinstance(fb, list) or not 3 <= len(fb) <= 5:
        raise ScoreError("feedback must be 3-5 items")
    for f in fb:
        if not f.get("text") or any(i not in student for i in f.get("evidence", [])):
            raise ScoreError("feedback item invalid/citation not a student turn")
    return raw


def total_of(dims, cfg: VivaConfig) -> float:
    w = {d["key"]: d["weight"] for d in cfg.rubric["dimensions"]}
    return round(sum(w[k] * dims[k]["score"] / 5 for k in w), 2)


def tidy(raw):
    """Live models sometimes pad "feedback" with empty strings (seen on gpt-oss-20b). Blank entries carry no content, so drop them
    before validation; anything else that is wrong is still rejected."""
    if isinstance(raw, dict) and isinstance(raw.get("feedback"), list):
        raw["feedback"] = [f for f in raw["feedback"] if not (isinstance(f, str) and not f.strip())]
    return raw


def score_once(llm, cfg, transcript, max_retries=2):
    system, user, errors = _system(cfg), _user(transcript), []
    for _ in range(max_retries + 1):
        try:
            raw = tidy(llm.complete_json(system, user, max_tokens=3000, kind="score"))
            validate(raw, cfg, transcript)
            return raw, errors
        except (ProviderError, CallCapExceeded) as e:  # the llm layer already retried and fell back
            raise ScoreError(f"provider failed: {e}"[:200]) from e
        except Exception as e:  # malformed JSON, bad citations, provider errors -> retry
            errors.append(str(e)[:200])
    raise ScoreError(f"scorer failed after retries: {errors}")


DONT_KNOW = re.compile(r"\b(i\s*)?(don'?t|do not) know\b|\bno idea\b", re.I)
# phrases a student might use to talk to the scorer instead of answering; matching only raises a flag, it never changes a mark
INJECTION = re.compile(r"ignore (all |any )?(the )?(previous|prior|above|earlier) (instructions|prompts?|rules)|full marks|"
                       r"(give|award|grant) me (a )?(full|top|maximum|max|100|five|5)|(score|mark|grade|rate) me (as )?(full|100|5|five|top)|"
                       r"you (must|should|have to) (give|score|mark|award)|system prompt|as the (scorer|examiner|grader)", re.I)
STT_LOW, STT_SHARE = 0.6, 0.25  # an answer with speech-recognition confidence below STT_LOW is shaky; flag when STT_SHARE of answers are
IDK_REPEATS = 3


def confidence_flags(events, transcript, run_totals, audio_missing=False):
    """Reasons a human should check this result. Signals: too little to judge, repeated 'I don't know', shaky speech recognition,
    a missing recording, live LLM trouble, an exhausted bank, runs that disagree, and answers that talk to the scorer."""
    flags = []
    st = [t for t in transcript if t["speaker"] == "STUDENT"]
    if len(st) < 6:
        flags.append(f"few student turns ({len(st)})")
    if st and sum(len(t["text"].split()) for t in st) / len(st) < 12:
        flags.append("very short answers on average")
    idk = sum(1 for t in st if DONT_KNOW.search(t["text"]))
    if idk >= IDK_REPEATS:
        flags.append(f"repeated \"I don't know\" ({idk} of {len(st)} answers)")
    shaky = [t["idx"] for t in st if t.get("stt_confidence") is not None and t["stt_confidence"] < STT_LOW]
    if shaky and len(shaky) / len(st) >= STT_SHARE:
        flags.append(f"low speech-recognition confidence on {len(shaky)} of {len(st)} answers (turns {shaky})")
    if audio_missing:
        flags.append("audio recording missing")
    pushy = [t["idx"] for t in st if INJECTION.search(t["text"])]
    if pushy:
        flags.append(f"answers try to instruct the scorer (turns {pushy}); marks are unchanged, check the transcript")
    if any(e.get("action") == "classify_error" for e in events):
        flags.append("LLM errors during live session")
    if any(e.get("action") == "bank_exhausted" for e in events):
        flags.append("question bank exhausted")
    if run_totals and max(run_totals) - min(run_totals) > 10:
        flags.append(f"scorer runs disagree (spread {max(run_totals) - min(run_totals):.1f})")
    return flags


def score_session(llm, cfg: VivaConfig, events, runs=3, audio_missing=False):
    transcript = build_transcript(events)
    if not any(t["speaker"] == "STUDENT" for t in transcript):
        raise ScoreError("no student turns to score")
    results = []
    for _ in range(runs):
        raw, errs = score_once(llm, cfg, transcript)
        results.append({"raw": raw, "total": total_of(raw["dimensions"], cfg), "retries": len(errs), "model": llm.name})
    totals = [r["total"] for r in results]
    keys = [d["key"] for d in cfg.rubric["dimensions"]]
    dims = {}
    rep = sorted(results, key=lambda r: r["total"])[len(results) // 2]  # run holding the median total
    offsets = {t["idx"]: t["t_start_ms"] for t in transcript if t["speaker"] == "STUDENT"}  # where to seek the audio; None in text mode
    for k in keys:
        scores = [r["raw"]["dimensions"][k]["score"] for r in results]
        evidence = rep["raw"]["dimensions"][k].get("evidence", [])
        dims[k] = {"score": statistics.median(scores), "range": [min(scores), max(scores)],
                   "reason": rep["raw"]["dimensions"][k]["reason"], "evidence": evidence,
                   "evidence_ms": [offsets.get(i) for i in evidence]}
    flags = confidence_flags(events, transcript, totals, audio_missing)
    return {
        "scorer_prompt_version": SCORER_PROMPT_VERSION, "rubric_version": cfg.rubric["version"],
        "model": llm.name, "runs": runs, "run_totals": totals,
        "total": total_of(dims, cfg), "total_spread": round(max(totals) - min(totals), 2),
        "dimensions": dims, "feedback": rep["raw"]["feedback"],
        "low_confidence": bool(flags), "low_confidence_reasons": flags,
        "evidence_timestamps": {t["idx"]: t["t"] for t in transcript if t["speaker"] == "STUDENT"},
        "evidence_offsets_ms": offsets,
        "run_details": [{"total": r["total"], "dimensions": r["raw"]["dimensions"], "feedback": r["raw"]["feedback"],
                         "model": r["model"], "retries": r["retries"]} for r in results],
        "faculty_review_required": bool(flags),
    }
