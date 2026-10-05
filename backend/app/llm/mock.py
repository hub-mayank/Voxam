import re


class MockLLM:
    """Deterministic offline provider for tests and dev. Not a quality benchmark."""
    name = "mock"

    def complete_json(self, system, user):
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

    def complete_text(self, system, user, max_tokens=120):
        action = re.search(r"ACTION:\s*(\w+)", user).group(1)
        return {
            "deeper": "Good. What edge cases or trade-offs would you worry about here?",
            "nudge": "You're partway there. Think about what happens as the input grows.",
            "redirect": "Let's bring it back to the question. Could you answer that directly?",
        }.get(action, "Okay, let's move on.")
