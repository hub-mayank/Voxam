"""T8 follow-up quality: three scripted students (strong, weak, "I don't know") go through the real interviewer on a real model.
The answers are scripted from the question bank's own key points, so every answer is specific to the question asked; the model
only sees what a student would say. Each turn is written to one CSV (full text), with whether the AI's reply leaked a key point.
A virtual clock moves 45 s per answer, so the phases change as in a real viva.
Usage: python scripts/followup_personas.py --llm ollama:llama3.2:3b [--tag ollama_llama3.2_3b] [--bank config/question_bank.dsa.json]
       --llm mock is a plumbing dry run (provider=mock)."""
import argparse
import csv
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.clock import VivaClock  # noqa: E402
from app.config import load_bank, load_config  # noqa: E402
from app.envfile import load_env  # noqa: E402
from app.interviewer import Interviewer  # noqa: E402
from app.llm.factory import make_llm  # noqa: E402
from app.results_meta import write_meta  # noqa: E402

PERSONAS = ("strong", "weak", "idk")
SECONDS_PER_ANSWER = 45
MAX_ANSWERS = 40

OPENERS = {
    "strong": "I built a library management system with a REST API in Node and a PostgreSQL database. I designed the schema, added "
              "indexes for the search queries and wrote the tests.",
    "weak": "I made a small website for my college, it was a group project and I did some of the pages.",
    "idk": "I don't know, I have not really built anything yet.",
}
FOLLOW_STRONG = ("It depends on the input size. I would also think about edge cases like empty input and very large input, and the "
                 "trade-off between speed and memory.")
FALLBACK_STRONG = "I would pick the data structure from how the data is accessed, and measure before optimising."


def sentence(text: str) -> str:
    return text[0].upper() + text[1:] + "."


def answer_for(persona: str, question: dict, repeat: int) -> str:
    """What this persona says to this question. `repeat` counts the follow-ups already asked on the same question."""
    points = question.get("key_points") or []
    if question["id"] == "opener":
        return OPENERS[persona]
    if persona == "idk":
        return "I don't know."
    if not points:  # a fallback question outside the bank
        return FALLBACK_STRONG if persona == "strong" else "I am not sure, maybe it depends."
    if persona == "strong":
        if repeat:  # a follow-up: say it again in the other order and add the trade-off, still about this question
            return " ".join(sentence(p) for p in reversed(points)) + " " + FOLLOW_STRONG
        return " ".join(sentence(p) for p in points)
    half = points[: max(1, len(points) // 2)]  # about half of the key points, hedged: a partial answer
    return f"I think it is something like {' and '.join(half)}, but I am not sure about the rest."


def leaked(text: str, question: dict, student: str = "") -> int:
    """How many of the question's key points the AI's reply gives away: a key point that appears word for word in the reply but
    not in the question itself and not in what the student just said (an echo of the student is not a leak)."""
    low, asked, said = text.lower(), question["text"].lower(), student.lower()
    return sum(1 for p in question.get("key_points") or []
               if p.lower() in low and p.lower() not in asked and p.lower() not in said)


class VirtualClock:
    def __init__(self):
        self.t = 0.0

    def now(self) -> float:
        return self.t


def run(persona: str, llm, cfg, bank) -> list[dict]:
    virtual = VirtualClock()
    iv = Interviewer(llm, bank, VivaClock(cfg, now=virtual.now), cfg, seed=f"t8-{persona}")
    iv.start()
    rows, repeat, last_q = [], 0, None
    for n in range(1, MAX_ANSWERS + 1):
        q = iv.q
        repeat = repeat + 1 if q["id"] == last_q else 0
        last_q = q["id"]
        text = answer_for(persona, q, repeat)
        virtual.t += SECONDS_PER_ANSWER
        before = len(iv.log)
        reply = iv.respond(text)
        events = iv.log[before:]
        quality = next((e.get("quality") for e in events if e.get("role") == "system" and e.get("quality")), "")
        action = next((e["action"] for e in events if e.get("role") == "ai"), "")
        rows.append({"persona": persona, "n": n, "phase": iv.phase_name, "question_id": q["id"], "question": q["text"],
                     "student": text, "quality": quality, "action": action, "ai": reply, "leaked_key_points": leaked(reply, q, text),
                     "model": llm.name})
        if action == "close":
            break
    return rows


def summarise(rows: list[dict]) -> dict:
    by = {}
    for p in PERSONAS:
        mine = [r for r in rows if r["persona"] == p]
        acts = [r["action"] for r in mine]
        by[p] = {"answers": len(mine), **{a: acts.count(a) for a in ("deeper", "nudge", "redirect", "move_on", "new_question")},
                 "classed_strong": sum(r["quality"] == "strong" for r in mine), "classed_none": sum(r["quality"] == "none" for r in mine),
                 "leaks": sum(r["leaked_key_points"] for r in mine)}
    return by


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--llm", default="mock")
    ap.add_argument("--tag", default=None)
    ap.add_argument("--bank", default=str(ROOT / "config" / "question_bank.dsa.json"))
    ap.add_argument("--recompute", help="recount the leak column of an existing results CSV with the current rule (no model calls)")
    ap.add_argument("--personas", default=",".join(PERSONAS), help="comma list, to run only some (a small token budget)")
    a = ap.parse_args()
    load_env()
    cfg = load_config(ROOT / "config" / "viva.config.json")
    bank = load_bank(Path(a.bank))
    if a.recompute:
        by_id = {q["id"]: q for q in bank}
        path = Path(a.recompute)
        old = list(csv.DictReader(open(path)))
        for r in old:
            q = by_id.get(r["question_id"], {"text": r["question"], "key_points": []})
            r["leaked_key_points"] = leaked(r["ai"], q, r["student"])
        with open(path, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(old[0]))
            w.writeheader()
            w.writerows(old)
        meta = path.with_name(path.name + ".meta.json")
        import json
        m = json.loads(meta.read_text())
        m["note"] += "; leaked_key_points recounted with the current rule (echo of the question or of the student is not a leak)"
        meta.write_text(json.dumps(m, indent=2) + "\n")
        print("recomputed", path, sum(int(r["leaked_key_points"]) for r in old), "leaks")
        return
    llm = make_llm(a.llm, retries=1)
    rows = []
    chosen = [p for p in a.personas.split(",") if p in PERSONAS]
    for p in chosen:
        rows += run(p, llm, cfg, bank)
    tag = a.tag or a.llm.replace("/", "_").replace(":", "_")
    out = ROOT / "results" / f"followup_{tag}.csv"
    with open(out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    provider = "mock" if a.llm == "mock" else "live"
    write_meta(out, provider=provider, model=llm.name, n=len(rows), n_unit="scripted answers", personas=chosen,
               bank=Path(a.bank).name, seconds_per_answer=SECONDS_PER_ANSWER, scripted_from="question bank key_points",
               note="the AI side is a real model; the student side is scripted from the bank's key points, so this shows how the "
                    "interviewer adapts, not how real students answer")
    for p, s in summarise(rows).items():
        if s["answers"]:
            print(p, s)
    print(f"wrote {out.relative_to(ROOT)} ({provider}, median answer length {int(statistics.median(len(r['student']) for r in rows))} chars)")


if __name__ == "__main__":
    main()
