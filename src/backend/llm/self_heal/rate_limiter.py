"""Rate limiter for named self-healing operations."""

import threading
import time
from collections import defaultdict


class RateLimiter:
    """Limits how often a named operation can be triggered.

    Each operation name has its own sliding window counter so that,
    for example, a heavy repair strategy cannot be invoked more than
    ``max_per_window`` times within ``window_seconds`` seconds.
    """

    def __init__(self, max_per_window: int = 5, window_seconds: float = 300):
        self._max = max_per_window
        self._window = window_seconds
        self._timestamps: dict = defaultdict(list)
        self._lock = threading.Lock()

    def allow(self, name: str) -> bool:
        """Return True if the operation is allowed, False if rate-limited."""
        now = time.time()
        with self._lock:
            self._timestamps[name] = [
                t for t in self._timestamps[name]
                if now - t < self._window
            ]
            if len(self._timestamps[name]) < self._max:
                self._timestamps[name].append(now)
                return True
            return False

    def reset(self, name: str) -> None:
        """Reset the counter for the given operation name."""
        with self._lock:
            self._timestamps[name] = []
