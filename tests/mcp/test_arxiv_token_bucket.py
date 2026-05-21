"""Unit tests for the per-process arxiv token bucket."""

from __future__ import annotations

import asyncio

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
