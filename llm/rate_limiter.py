import time
import asyncio
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Optional
from loguru import logger

from config import config


@dataclass
class RateLimitResult:
    allowed: bool
    retry_after_seconds: Optional[int]
    limit_type: Optional[str]


class RateLimiter:

    def __init__(self):
        self.rpm: int = config.RATE_LIMIT_RPM
        self.rph: int = config.RATE_LIMIT_RPH
        self.burst: int = config.RATE_LIMIT_BURST

        self._windows: dict[int, deque] = defaultdict(deque)
        self._lock = asyncio.Lock()

    async def check(self, user_id: int) -> RateLimitResult:
        async with self._lock:
            return self._check_internal(user_id)

    async def acquire(self, user_id: int) -> RateLimitResult:
        async with self._lock:
            result = self._check_internal(user_id)
            if result.allowed:
                self._windows[user_id].append(time.time())
                self._cleanup(user_id)
            return result

    def _check_internal(self, user_id: int) -> RateLimitResult:
        now = time.time()
        timestamps = self._windows[user_id]

        burst_window = [t for t in timestamps if now - t < 10]
        if len(burst_window) >= self.burst:
            oldest = min(burst_window)
            retry_after = int(10 - (now - oldest)) + 1
            return RateLimitResult(
                allowed=False,
                retry_after_seconds=retry_after,
                limit_type="burst",
            )

        rpm_window = [t for t in timestamps if now - t < 60]
        if len(rpm_window) >= self.rpm:
            oldest = min(rpm_window)
            retry_after = int(60 - (now - oldest)) + 1
            return RateLimitResult(
                allowed=False,
                retry_after_seconds=retry_after,
                limit_type="rpm",
            )

        rph_window = [t for t in timestamps if now - t < 3600]
        if len(rph_window) >= self.rph:
            oldest = min(rph_window)
            retry_after = int(3600 - (now - oldest)) + 1
            return RateLimitResult(
                allowed=False,
                retry_after_seconds=retry_after,
                limit_type="rph",
            )

        return RateLimitResult(allowed=True, retry_after_seconds=None, limit_type=None)

    def _cleanup(self, user_id: int) -> None:
        now = time.time()
        d = self._windows[user_id]
        while d and now - d[0] > 3600:
            d.popleft()

    def get_stats(self, user_id: int) -> dict:
        now = time.time()
        timestamps = self._windows.get(user_id, deque())
        return {
            "requests_last_10s": sum(1 for t in timestamps if now - t < 10),
            "requests_last_minute": sum(1 for t in timestamps if now - t < 60),
            "requests_last_hour": sum(1 for t in timestamps if now - t < 3600),
            "limits": {
                "burst_per_10s": self.burst,
                "rpm": self.rpm,
                "rph": self.rph,
            },
        }
