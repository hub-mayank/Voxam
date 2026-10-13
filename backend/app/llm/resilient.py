"""Retry with backoff, ordered fallback and telemetry around raw providers.
Per provider: up to `retries` retries on 429/5xx/timeouts (non-retryable errors go straight to the next provider).
A provider whose call budget is used up (CallCapExceeded: free-tier day budget, global ceiling, or per-minute pacing) is skipped for
this call and the chain moves on; it is never retried. If every provider is out of budget the CallCapExceeded is raised.
`name` is the model that served the last call (for audit logs); share one instance per session, not across concurrent sessions."""
import json
import random
import time
from .budget import CallCapExceeded
from .errors import AllProvidersFailed, ProviderError
from .. import telemetry


class ResilientLLM:
    def __init__(self, providers, retries=2, backoff=0.5, max_delay=20.0, jitter=0.25, sleep=time.sleep):
        if not providers:
            raise ValueError("need at least one provider")
        self.providers = list(providers)
        self.retries, self.backoff, self.max_delay, self.jitter, self.sleep = retries, backoff, max_delay, jitter, sleep
        self._served = self.providers[0]

    @property
    def name(self):
        return self._served.name

    def complete_json(self, system, user, max_tokens=200, kind="classify"):
        return self._run(system, user, max_tokens, kind, True)

    def complete_text(self, system, user, max_tokens=120, kind="phrase", on_delta=None):
        """on_delta(piece) is called as text arrives from a provider that can stream (others deliver the whole text once at the end).
        Retries and fallback work as usual until the first piece has been delivered; after that a failure is raised (the caller has
        already shown or spoken part of the reply)."""
        return self._run(system, user, max_tokens, kind, False, on_delta)

    def _delay(self, attempt, err):
        delay = min(self.max_delay, self.backoff * 2 ** attempt)
        if err.retry_after:
            delay = max(delay, min(err.retry_after, self.max_delay))
        return delay * (1 + random.uniform(-self.jitter, self.jitter))

    def _log(self, p, kind, ms, status, attempt, reply=None):
        telemetry.log_call(p.provider, p.model, p.mode, kind, ms, status, attempt,
                           reply.tokens_in if reply else None, reply.tokens_out if reply else None)

    def _run(self, system, user, max_tokens, kind, json_mode, on_delta=None):
        if kind not in telemetry.KINDS:
            raise ValueError(f"unknown kind {kind!r}")
        errors, capped = [], []
        for p in self.providers:
            for attempt in range(self.retries + 1):
                t = time.perf_counter()
                started = []
                try:
                    if on_delta is not None and not json_mode and hasattr(p, "generate_stream"):
                        def forward(piece, _started=started):
                            _started.append(1)
                            on_delta(piece)
                        reply = p.generate_stream(system, user, max_tokens, forward)
                    else:
                        reply = p.generate(system, user, max_tokens, json_mode)
                        if on_delta is not None and not json_mode:
                            started.append(1)
                            on_delta(reply.text)
                except CallCapExceeded as e:
                    self._log(p, kind, (time.perf_counter() - t) * 1000, "cap_exceeded", attempt)
                    capped.append(e)
                    break
                except ProviderError as e:
                    self._log(p, kind, (time.perf_counter() - t) * 1000, e.status, attempt)
                    errors.append(e)
                    if started:  # part of the reply is already out: a retry would repeat it
                        raise
                    if not e.retryable or attempt == self.retries:
                        break
                    self.sleep(self._delay(attempt, e))
                    continue
                ms = (time.perf_counter() - t) * 1000
                try:
                    out = json.loads(reply.text) if json_mode else reply.text.strip()
                except json.JSONDecodeError:
                    self._log(p, kind, ms, "bad_output", attempt, reply)
                    raise
                self._log(p, kind, ms, "ok", attempt, reply)
                self._served = p
                return out
        if not errors:  # nobody was even tried: every provider is out of budget
            raise capped[-1]
        last = errors[-1]
        raise AllProvidersFailed(f"all providers failed, last: {last}", last.status,
                                 any(e.retryable for e in errors), last.status_code, None, last.body)
