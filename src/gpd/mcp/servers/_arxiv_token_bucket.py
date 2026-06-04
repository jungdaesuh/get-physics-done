"""Process-local token bucket for arxiv-domain HTTP traffic.

Token bucket with a small burst capacity. The previous implementation was a
leaky-bucket-of-1: every acquire serialized at ``_MIN_INTERVAL`` seconds, so a
burst of N concurrent callers waited ``(N-1) * _MIN_INTERVAL`` seconds at the
tail — N=20 would push the tail past 60 s and trip the MCP client's default
request timeout the whole bridge is built to avoid. The bucket below absorbs
bursts up to ``_CAPACITY`` immediately and falls back to the ``_MIN_INTERVAL``
spacing only when the bucket is empty, keeping arxiv.org's 3-second crawl
etiquette intact under steady load while letting short bursts of parallel
downloads avoid the 60-second cliff.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

# Steady-state interval between refilled tokens. Matches arXiv's 3-second
# crawl etiquette; OpenAlex / GCS calls share the bucket because they hit
# the same upstream-rate-limit budget when paths spill over.
_MIN_INTERVAL: float = 3.0

# Burst capacity. Small enough that arXiv's rate-limit never sees more
# than a short pulse; large enough that the worst-case serialized tail of
# N concurrent download_paper / search_papers calls stays well below the
# MCP client's 60-second request timeout for typical research bursts.
_CAPACITY: float = 4.0

_lock: asyncio.Lock | None = None
_tokens: float = _CAPACITY
_last_refill_time: float = 0.0
# Monotonically-advancing deadline for the next available slot once the
# bucket has drained. Each waiter past the burst claims a slot at
# `max(_next_available, now + needed*_MIN_INTERVAL)` then pushes the
# deadline forward by `_MIN_INTERVAL` so subsequent waiters queue in
# order instead of all sleeping the same 3 s and stampeding on wakeup.
_next_available: float = 0.0


def _get_lock() -> asyncio.Lock:
    global _lock
    if _lock is None:
        _lock = asyncio.Lock()
    return _lock


@asynccontextmanager
async def acquire() -> AsyncIterator[None]:
    global _tokens, _last_refill_time, _next_available

    lock = _get_lock()
    wait_seconds = 0.0
    async with lock:
        now = time.monotonic()
        if _last_refill_time == 0.0:
            _last_refill_time = now

        # Refill at 1 token per _MIN_INTERVAL seconds, capped at _CAPACITY.
        elapsed = now - _last_refill_time
        refill = elapsed / _MIN_INTERVAL
        if refill > 0:
            _tokens = min(_CAPACITY, _tokens + refill)
            _last_refill_time = now

        if _tokens >= 1.0:
            _tokens -= 1.0
        else:
            # Anchor to the latest scheduled slot so concurrent post-burst
            # waiters queue at _MIN_INTERVAL spacing instead of converging
            # on the same wake time. Without this, two waiters that enter
            # the critical section a few microseconds apart each compute
            # `wait = _MIN_INTERVAL` from their own `now` and wake almost
            # simultaneously — the exact stampede the bucket exists to
            # prevent. See PR #233 / CodeRabbit thread for the walkthrough.
            needed = 1.0 - _tokens
            target = max(_next_available, now + needed * _MIN_INTERVAL)
            wait_seconds = target - now
            _next_available = target + _MIN_INTERVAL
            _tokens = 0.0
            _last_refill_time = target

    if wait_seconds > 0:
        await asyncio.sleep(wait_seconds)

    yield


def _reset_for_tests() -> None:
    global _lock, _tokens, _last_refill_time, _next_available
    _lock = None
    _tokens = _CAPACITY
    _last_refill_time = 0.0
    _next_available = 0.0
