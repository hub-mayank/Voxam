"""Follow-up policy lives in code, not in the LLM prompt (auditable + testable)."""


def decide(quality: str, followups_used: int, max_followups: int, redirects_used: int) -> str:
    if quality == "offtopic":
        return "redirect" if redirects_used == 0 else "move_on"
    if quality == "none":
        return "move_on"  # no penalty spiral: note and go
    if followups_used >= max_followups:
        return "move_on"
    if quality == "strong":
        return "deeper"
    if quality == "partial":
        return "nudge" if followups_used == 0 else "move_on"
    return "move_on"


QUALITY_POINTS = {"strong": 2, "partial": 1, "none": 0, "offtopic": 0}
