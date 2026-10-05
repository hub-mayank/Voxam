import json
from pathlib import Path
import pytest
from app.config import load_config
from app.llm.mock import MockLLM
from app.scorer import (score_session, build_transcript, validate, ScoreError, total_of, score_once)

ROOT = Path(__file__).resolve().parents[2]
CFG = load_config(ROOT / "config/viva.config.json")
P = Path(__file__).parent / "personas"


def ev(name): return [json.loads(l) for l in open(P / f"{name}.jsonl")]


def score(name, llm=None, runs=3): return score_session(llm or MockLLM(), CFG, ev(name), runs=runs)


def test_persona_ordering():
    assert score("strong")["total"] > score("weak")["total"] > score("idk")["total"]


def test_idk_scores_zero_and_no_penalty_spiral_flags():
    r = score("idk")
    assert r["total"] == 0


def test_total_math():
    dims = {k["key"]: {"score": 5} for k in CFG.rubric["dimensions"]}
    assert total_of(dims, CFG) == 100
    dims = {k["key"]: {"score": 0} for k in CFG.rubric["dimensions"]}
    assert total_of(dims, CFG) == 0


def test_audit_fields_present():
    r = score("strong")
    assert r["scorer_prompt_version"] == "scorer-v1" and r["rubric_version"] == "rubric-v1"
    assert r["model"] == "mock" and r["runs"] == 3 and len(r["run_totals"]) == 3
    assert all(d["evidence"] for d in r["dimensions"].values())
    assert set(r["evidence_timestamps"]) >= {i for d in r["dimensions"].values() for i in d["evidence"]}


def test_short_session_is_low_confidence():
    r = score("strong")  # only ~7 student turns of long answers
    short = ev("strong")[:5]
    r2 = score_session(MockLLM(), CFG, short, runs=3)
    assert r2["low_confidence"] and r2["faculty_review_required"]


def test_hallucinated_citation_rejected_then_retried():
    class Flaky(MockLLM):
        n = 0
        def complete_json(self, system, user, max_tokens=200):
            Flaky.n += 1
            out = super().complete_json(system, user, max_tokens)
            if Flaky.n == 1:
                out["dimensions"]["conceptual"]["evidence"] = [999]
            return out
    tr = build_transcript(ev("strong"))
    raw, errs = score_once(Flaky(), CFG, tr)
    assert len(errs) == 1 and "999" in errs[0]


def test_ai_turn_citation_rejected():
    tr = build_transcript(ev("strong"))
    raw = MockLLM()._score("\n".join(f"[{t['idx']}] x {t['speaker']}: {t['text']}" for t in tr))
    raw["dimensions"]["depth"]["evidence"] = [0]  # turn 0 is the AI opener
    with pytest.raises(ScoreError):
        validate(raw, CFG, tr)


def test_score_gt0_requires_evidence():
    tr = build_transcript(ev("strong"))
    raw = MockLLM()._score("\n".join(f"[{t['idx']}] x {t['speaker']}: {t['text']}" for t in tr))
    raw["dimensions"]["depth"]["evidence"] = []
    with pytest.raises(ScoreError):
        validate(raw, CFG, tr)


def test_run_disagreement_flags_low_confidence():
    class Wobbly(MockLLM):
        n = 0
        def complete_json(self, system, user, max_tokens=200):
            out = super().complete_json(system, user, max_tokens)
            Wobbly.n += 1
            if Wobbly.n % 2 == 0:
                for d in out["dimensions"].values(): d["score"] = 1
            return out
    r = score_session(Wobbly(), CFG, ev("strong"), runs=3)
    assert r["total_spread"] > 10 and r["low_confidence"]


def test_provider_failure_raises_not_silent():
    class Dead(MockLLM):
        def complete_json(self, *a, **k): raise RuntimeError("429")
    with pytest.raises(ScoreError):
        score_session(Dead(), CFG, ev("strong"), runs=1)
