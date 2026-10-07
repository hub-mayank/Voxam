import re


class MockLLM:
    """Deterministic offline provider for tests and dev. Proves plumbing, NOT quality."""
    name = "mock"

    def complete_json(self, system, user, max_tokens=200, kind="classify"):
        if system.startswith("SCORE"):
            return self._score(user)
        m = re.search(r"ANSWER:\s*(.*)", user, re.S)
        a = (m.group(1) if m else "").lower()
        if "don't know" in a or "dont know" in a or "no idea" in a:
            q = "none"
        elif any(w in a for w in ("cricket", "weather", "movie")):
            q = "offtopic"
        elif len(a.split()) >= 25:
            q = "strong"
        else:
            q = "partial"
        return {"quality": q}

    def _score(self, user):
        turns = [(int(i), t) for i, t in re.findall(r"^\[(\d+)\][^\n]*? STUDENT: (.*)$", user, re.M)]
        if not turns:
            s, ev = 0, []
        else:
            idk = sum(1 for _, t in turns if re.search(r"don'?t know|no idea", t.lower()))
            avg = sum(len(t.split()) for _, t in turns) / len(turns)
            s = 0 if idk / len(turns) > 0.5 else min(5, round(avg / 6))
            ev = [i for i, _ in sorted(turns, key=lambda x: -len(x[1].split()))[:2]]
        keys = re.findall(r"^- (\w+) \(weight", user, re.M) or ["conceptual", "depth", "problem", "practical", "communication"]
        dims = {k: {"score": s, "reason": f"mock score {s} from answer length", "evidence": ev if s else []} for k in keys}
        fb = [{"text": f"mock feedback {n}", "evidence": ev} for n in range(3)] if ev else \
             [{"text": f"mock feedback {n}", "evidence": []} for n in range(3)]
        return {"dimensions": dims, "feedback": fb}

    def complete_text(self, system, user, max_tokens=120, kind="phrase"):
        action = re.search(r"ACTION:\s*(\w+)", user).group(1)
        return {
            "deeper": "Good. What edge cases or trade-offs would you worry about here?",
            "nudge": "You're partway there. Think about what happens as the input grows.",
            "redirect": "Let's bring it back to the question. Could you answer that directly?",
        }.get(action, "Okay, let's move on.")
