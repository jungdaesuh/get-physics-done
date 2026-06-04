"""Unit tests for the per-process arxiv token bucket."""

from __future__ import annotations

import pytest

from gpd.mcp.servers import _arxiv_token_bucket


@pytest.fixture(autouse=True)
def reset_bucket() -> None:
    _arxiv_token_bucket._reset_for_tests()
    yield
    _arxiv_token_bucket._reset_for_tests()


@pytest.mark.asyncio
async def test_first_acquire_does_not_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    slept: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        slept.append(seconds)

    monkeypatch.setattr(_arxiv_token_bucket.asyncio, "sleep", fake_sleep)
    async with _arxiv_token_bucket.acquire():
        pass
    # Initial _last_request_time=0; monotonic() is huge; wait is hugely negative,
    # so no sleep should fire.
    assert slept == []


@pytest.mark.asyncio
async def test_burst_within_capacity_does_not_sleep(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    slept: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        slept.append(seconds)

    monkeypatch.setattr(_arxiv_token_bucket.asyncio, "sleep", fake_sleep)

    # `_CAPACITY` back-to-back acquires must drain the bucket without ever
    # sleeping — this is the whole point of bursting: a short flurry of
    # parallel downloads serves immediately and only spaces out once the
    # bucket empties.
    for _ in range(int(_arxiv_token_bucket._CAPACITY)):
        async with _arxiv_token_bucket.acquire():
            pass

    assert slept == [], (
        f"first {int(_arxiv_token_bucket._CAPACITY)} acquires must not sleep "
        f"(burst capacity); got slept={slept}"
    )


@pytest.mark.asyncio
async def test_acquire_after_burst_sleeps_for_min_interval(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    slept: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        slept.append(seconds)

    monkeypatch.setattr(_arxiv_token_bucket.asyncio, "sleep", fake_sleep)

    # Drain the bucket.
    for _ in range(int(_arxiv_token_bucket._CAPACITY)):
        async with _arxiv_token_bucket.acquire():
            pass

    # The (CAPACITY+1)th call has to wait for one refill cycle.
    async with _arxiv_token_bucket.acquire():
        pass

    assert len(slept) == 1, f"expected exactly one sleep after draining; got {slept}"
    assert 2.0 <= slept[0] <= 3.5


@pytest.mark.asyncio
async def test_concurrent_post_burst_waiters_serialize_at_min_interval(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When ``N`` waiters race the bucket past its capacity, they must wake at
    ``_MIN_INTERVAL`` spacing — not all converge on the same ``+_MIN_INTERVAL``
    deadline and stampede arxiv.org on a single wake.

    Regression test for the lock-and-overwrite-_last_refill_time bug CodeRabbit
    flagged on PR #233: each waiter independently computed `wait = 3.0` from
    its own ``now`` and the next slot was overwritten relative to the latest
    arrival, so two contending waiters slept the same ~3 s and fired in
    parallel — exactly the behaviour the docstring promises to avoid."""

    import asyncio
    import time as _time

    slept: list[float] = []
    real_sleep = asyncio.sleep

    async def fake_sleep(seconds: float) -> None:
        slept.append(seconds)
        # Advance the monotonic clock so the next waiter's `now - _last_refill`
        # math reflects the elapsed wait, matching real-world behaviour.
        return None

    monkeypatch.setattr(_arxiv_token_bucket.asyncio, "sleep", fake_sleep)

    # Drain the bucket synchronously so the burst credits are gone.
    for _ in range(int(_arxiv_token_bucket._CAPACITY)):
        async with _arxiv_token_bucket.acquire():
            pass
    slept.clear()

    # Three contenders enter the lock back-to-back with no real wall-clock
    # advance between them. With the bug, all three see the same `now` snapshot
    # of `_tokens=0` / a fresh-ish `_last_refill_time` and each computes
    # `wait = 3.0`. With the fix, `_next_available` anchors the second waiter
    # to ~6 s and the third to ~9 s.
    async def claim() -> None:
        async with _arxiv_token_bucket.acquire():
            await real_sleep(0)

    # Schedule them onto the same loop concurrently.
    await asyncio.gather(claim(), claim(), claim())

    assert len(slept) == 3, f"expected one sleep per waiter; got {slept}"
    sorted_waits = sorted(slept)
    # Slots should be spaced by _MIN_INTERVAL: ~3, ~6, ~9.
    expected = [_arxiv_token_bucket._MIN_INTERVAL * k for k in (1, 2, 3)]
    for actual, want in zip(sorted_waits, expected, strict=True):
        assert abs(actual - want) <= 0.6, (
            f"post-burst waiters must serialize at {_arxiv_token_bucket._MIN_INTERVAL}s "
            f"spacing; got slept={sorted_waits}, expected near {expected}"
        )
    # Defensive: at least one waiter must sleep meaningfully longer than the others
    # so we catch the all-converge-on-3s regression even if spacing assertions are loose.
    assert max(sorted_waits) - min(sorted_waits) >= _arxiv_token_bucket._MIN_INTERVAL * 1.5, (
        f"post-burst sleeps converged ({sorted_waits}) — token bucket is letting "
        f"contending waiters stampede the upstream rate-limit budget"
    )

    # Silence the unused-import warning for monotonic — kept here for clarity in
    # the assertion narrative above.
    _ = _time.monotonic
