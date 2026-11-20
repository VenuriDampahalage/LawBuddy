"""Small in-memory sliding-window limiter for auth endpoints.

Kept per server process, which is enough for a single API instance. If the API is ever
scaled out to several processes, move this to Redis or Postgres.
"""

from __future__ import annotations

import math
import threading
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request, status


class SlidingWindow:
    def __init__(self, window_seconds: int) -> None:
        self.window = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def _prune(self, q: deque[float], now: float) -> None:
        while q and q[0] <= now - self.window:
            q.popleft()

    def retry_after(self, key: str, limit: int) -> int | None:
        """Seconds until `key` may try again, or None if it is under the limit."""
        now = time.monotonic()
        with self._lock:
            q = self._hits.get(key)
            if not q:
                return None
            self._prune(q, now)
            if len(q) < limit:
                return None
            return max(1, math.ceil(q[0] + self.window - now))

    def hit(self, key: str) -> None:
        now = time.monotonic()
        with self._lock:
            q = self._hits[key]
            self._prune(q, now)
            q.append(now)

    def reset(self, key: str | None = None) -> None:
        with self._lock:
            if key is None:
                self._hits.clear()
            else:
                self._hits.pop(key, None)


login_failures = SlidingWindow(15 * 60)
registrations = SlidingWindow(60 * 60)


def client_ip(request: Request) -> str:
    # Behind a reverse proxy, configure uvicorn --proxy-headers so this is the real client.
    return request.client.host if request.client else "unknown"


def enforce(limiter: SlidingWindow, key: str, limit: int, message: str) -> None:
    wait = limiter.retry_after(key, limit)
    if wait is not None:
        minutes = max(1, math.ceil(wait / 60))
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            f"{message} Please try again in about {minutes} minute{'s' if minutes > 1 else ''}.",
            headers={"Retry-After": str(wait)},
        )


def reset_all() -> None:
    """For tests."""
    login_failures.reset()
    registrations.reset()
