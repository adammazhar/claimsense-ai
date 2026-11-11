"""A token bucket per acting identity, so one seat can't starve the systems of record (D-037)."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field


@dataclass
class RateLimiter:
    capacity: float = 120.0  # burst
    refill_per_second: float = 30.0
    clock: object = time.monotonic
    _buckets: dict[str, tuple[float, float]] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def take(self, key: str) -> float | None:
        """Spend one token. Returns None if allowed, else the seconds to wait before retrying."""
        with self._lock:
            now = self.clock()
            tokens, last = self._buckets.get(key, (self.capacity, now))
            tokens = min(self.capacity, tokens + (now - last) * self.refill_per_second)
            if tokens >= 1:
                self._buckets[key] = (tokens - 1, now)
                return None
            self._buckets[key] = (tokens, now)
            return round((1 - tokens) / self.refill_per_second, 3)
