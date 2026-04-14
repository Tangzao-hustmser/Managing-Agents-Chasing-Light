"""In-process rate limiting for key write endpoints."""

from __future__ import annotations

import math
import time
from collections import deque
from threading import Lock
from typing import Deque, Dict

from app.config import settings


class RateLimitExceededError(ValueError):
    """Raised when one rate-limit bucket exceeds allowed capacity."""

    def __init__(self, message: str, retry_after: int):
        super().__init__(message)
        self.retry_after = max(1, int(retry_after))


_bucket_lock = Lock()
_buckets: Dict[str, Deque[float]] = {}


def clear_rate_limit_cache() -> None:
    """Clear in-memory buckets (used by tests and local reset)."""
    with _bucket_lock:
        _buckets.clear()


def enforce_write_rate_limit(*, user_id: int, endpoint_key: str) -> None:
    """Enforce runtime-configured request rate limits for critical writes."""
    if not settings.rate_limit_enabled:
        return

    window = int(settings.rate_limit_window_seconds)
    limit = int(settings.rate_limit_max_requests)
    if window <= 0 or limit <= 0:
        return

    now = time.monotonic()
    key = f"{user_id}:{endpoint_key}"
    cutoff = now - window

    with _bucket_lock:
        bucket = _buckets.setdefault(key, deque())
        while bucket and bucket[0] <= cutoff:
            bucket.popleft()
        if len(bucket) >= limit:
            retry_after = math.ceil(window - (now - bucket[0])) if bucket else window
            raise RateLimitExceededError(
                f"Rate limit exceeded for {endpoint_key}; try again later",
                retry_after=retry_after,
            )
        bucket.append(now)
