"""Sliding-window rate limiter, keyed by user id."""
import os
import time
from collections import defaultdict


class RateLimiter:
    def __init__(self, max_calls: int | None = None, window_seconds: int | None = None) -> None:
        self.max_calls = max_calls if max_calls is not None else int(os.getenv("RATE_LIMIT_MAX", "10"))
        self.window = window_seconds if window_seconds is not None else int(os.getenv("RATE_LIMIT_WINDOW", "60"))
        self._timestamps: dict[str, list[float]] = defaultdict(list)

    def exceeded(self, uid: str) -> bool:
        now = time.time()
        window_start = now - self.window
        self._timestamps[uid] = [t for t in self._timestamps[uid] if t > window_start]
        if len(self._timestamps[uid]) >= self.max_calls:
            return True
        self._timestamps[uid].append(now)
        return False
