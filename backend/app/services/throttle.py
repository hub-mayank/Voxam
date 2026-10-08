"""Sliding-window limiter, in memory. Used for wrong access codes per client IP.
One instance per process: with several server workers the effective limit is per worker."""
import threading
from collections import defaultdict, deque


class SlidingWindow:
    def __init__(self, limit: int, window_s: float = 60.0):
        self.limit, self.window_s = limit, window_s
        self._hits = defaultdict(deque)
        self._lock = threading.Lock()

    def _prune(self, key, now: float):
        q = self._hits[key]
        while q and q[0] <= now - self.window_s:
            q.popleft()
        if not q:
            self._hits.pop(key, None)
        return q

    def retry_after_s(self, key, now: float) -> float:
        """0 when the key may act; otherwise seconds until the oldest hit leaves the window."""
        with self._lock:
            q = self._prune(key, now)
            if len(q) < self.limit:
                return 0.0
            return max(0.0, q[0] + self.window_s - now)

    def record(self, key, now: float):
        with self._lock:
            self._prune(key, now)
            self._hits[key].append(now)

    def clear(self, key=None):
        with self._lock:
            self._hits.pop(key, None) if key is not None else self._hits.clear()
