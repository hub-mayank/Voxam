import time
from .config import VivaConfig, Phase


class VivaClock:
    """Code owns the clock. The LLM never decides phase or time."""

    def __init__(self, cfg: VivaConfig, now=time.monotonic):
        self.cfg, self._now, self._t0 = cfg, now, None

    def start(self):
        self._t0 = self._now()

    def elapsed(self) -> float:
        if self._t0 is None:
            raise RuntimeError("clock not started")
        return self._now() - self._t0

    def remaining(self) -> float:
        return max(0.0, self.cfg.hard_limit - self.elapsed())

    def expired(self) -> bool:
        return self.elapsed() >= self.cfg.hard_limit

    def phase(self) -> Phase:
        e = self.elapsed()
        for p in self.cfg.phases:
            if p.start <= e < p.end:
                return p
        return self.cfg.phases[-1]
