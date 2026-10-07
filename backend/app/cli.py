"""Text-mode viva. Usage: python -m app.cli [--llm mock|gemini|ollama]"""
import argparse
from pathlib import Path
from .clock import VivaClock
from .llm.factory import make_llm
from .config import load_config, load_bank
from .interviewer import Interviewer

ROOT = Path(__file__).resolve().parents[2]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--llm", default="mock", help="mock, gemini, ollama, or a fallback list like gemini,ollama")
    ap.add_argument("--out", default="session.jsonl")
    a = ap.parse_args()
    cfg = load_config(ROOT / "config/viva.config.json")
    bank = load_bank(ROOT / "config/question_bank.sample.json")
    llm = make_llm(a.llm)
    clock = VivaClock(cfg)
    iv = Interviewer(llm, bank, clock, cfg)
    print("AI:", iv.start())
    try:
        while not clock.expired():
            reply = iv.respond(input("You: "))
            print(f"AI [{iv.phase_name}, {int(clock.remaining())}s left]:", reply)
            if iv.log[-1].get("action") == "close":
                break
    except (EOFError, KeyboardInterrupt):
        pass
    finally:
        iv.dump(a.out)


if __name__ == "__main__":
    main()
