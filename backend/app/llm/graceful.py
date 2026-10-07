from ..interviewer import DEFAULT_REPLY, FALLBACK_REPLIES
import re


class GracefulLLM:
    """Wraps the provider chain for the live interview. If every provider fails to phrase a reply, answer with a canned
    line instead of raising, and remember what happened so it can be written to the audit log."""

    def __init__(self, inner):
        self.inner, self.calls, self.errors, self.served = inner, 0, [], None

    @property
    def name(self):
        return getattr(self.inner, "name", "unknown")

    def complete_json(self, system, user, max_tokens=200, kind="classify"):
        self.calls += 1
        try:
            out = self.inner.complete_json(system, user, max_tokens, kind)
        except Exception as e:  # the interviewer treats a failed classification as "partial"
            self.errors.append(f"{kind}: {type(e).__name__}: {e}"[:200])
            raise
        self.served = self.name
        return out

    def complete_text(self, system, user, max_tokens=120, kind="phrase"):
        self.calls += 1
        try:
            out = self.inner.complete_text(system, user, max_tokens, kind)
        except Exception as e:
            self.errors.append(f"{kind}: {type(e).__name__}: {e}"[:200])
            action = re.search(r"ACTION:\s*(\w+)", user)
            return FALLBACK_REPLIES.get(action.group(1) if action else "", DEFAULT_REPLY)
        self.served = self.name
        return out
