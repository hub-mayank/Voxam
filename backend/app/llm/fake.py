"""Failure-injecting stand-in provider (mode=stub). For tests and the load harness: proves plumbing, NOT quality."""
import json
from .base import Reply
from .errors import ProviderError, from_status


class FakeProvider:
    """script: one step per call; the last step repeats forever.
    Steps: "ok", "timeout", or an HTTP status code (429, 503, 404, ...)."""
    provider = "fake"
    mode = "stub"

    def __init__(self, script=("ok",), model="flaky", text="Okay, let's move on.", data=None, retry_after=None):
        self.script = list(script)
        self.model = model
        self.name = f"fake:{model}"
        self.text = text
        self.data = data if data is not None else {"quality": "partial"}
        self.retry_after = retry_after
        self.calls = 0

    def generate(self, system, user, max_tokens, json_mode):
        step = self.script[min(self.calls, len(self.script) - 1)]
        self.calls += 1
        if step == "timeout":
            raise ProviderError("timed out", "timeout", True)
        if step != "ok":
            raise from_status(step, self.retry_after)
        text = json.dumps(self.data) if json_mode else self.text
        return Reply(text, len(user.split()), len(text.split()))
