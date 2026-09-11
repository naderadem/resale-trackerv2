"""A minimal, thread-safe rate limiter shared across source adapters.

The goal isn't to maximize throughput -- it's the opposite: keep outbound
request volume against every marketplace low and predictable. Each
ListingSource gets its own RateLimiter instance (so eBay and Grailed don't
throttle each other), but if a single source makes multiple kinds of calls
(e.g. eBay's OAuth token endpoint and its search endpoint), they should
share one RateLimiter instance so total request volume to that source stays
capped.
"""
import threading
import time


class RateLimiter:
    """Enforces a minimum interval between successive requests."""

    def __init__(self, min_interval_seconds: float = 1.0):
        if min_interval_seconds < 0:
            raise ValueError("min_interval_seconds must be >= 0")
        self.min_interval_seconds = min_interval_seconds
        self._lock = threading.Lock()
        self._last_request_at: float | None = None

    def wait(self) -> None:
        """Block, if necessary, until it's been long enough since the last call."""
        with self._lock:
            now = time.monotonic()
            if self._last_request_at is not None:
                elapsed = now - self._last_request_at
                remaining = self.min_interval_seconds - elapsed
                if remaining > 0:
                    time.sleep(remaining)
            self._last_request_at = time.monotonic()
