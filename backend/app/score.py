"""python -m app.score session.jsonl [--llm mock|gemini|ollama] [--runs 3] [--out score.json]"""
import argparse
import json
from pathlib import Path
from .llm.factory import make_llm
from .config import load_config
from .scorer import score_session

ROOT = Path(__file__).resolve().parents[2]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("session")
    ap.add_argument("--llm", default="mock", help="mock, gemini, ollama, or a fallback list like gemini,ollama")
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--out", default="score.json")
    a = ap.parse_args()
    cfg = load_config(ROOT / "config/viva.config.json")
    llm = make_llm(a.llm)
    events = [json.loads(l) for l in open(a.session) if l.strip()]
    res = score_session(llm, cfg, events, runs=a.runs)
    Path(a.out).write_text(json.dumps(res, indent=2))
    print(f"total={res['total']}/100 spread={res['total_spread']} low_confidence={res['low_confidence']} {res['low_confidence_reasons']}")


if __name__ == "__main__":
    main()
