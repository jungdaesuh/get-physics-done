"""Unit tests for the SQLite arxiv cache."""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path

import pytest

from gpd.mcp.servers import _arxiv_cache


@pytest.fixture
def isolated_cache_db(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    db = tmp_path / "arxiv_cache.sqlite"
    monkeypatch.setattr(_arxiv_cache, "_CACHE_DIR", tmp_path)
    monkeypatch.setattr(_arxiv_cache, "_CACHE_DB", db)
    return db


@pytest.mark.asyncio
async def test_cache_miss_returns_none(isolated_cache_db: Path) -> None:
    assert await _arxiv_cache.get("get_abstract", {"paper_id": "2401.0001"}) is None


@pytest.mark.asyncio
async def test_cache_hit_returns_payload(isolated_cache_db: Path) -> None:
    args = {"paper_id": "2401.0001"}
    payload = json.dumps({"status": "success", "abstract": "..."})
    await _arxiv_cache.set("get_abstract", args, payload, ttl_days=1)
    result = await _arxiv_cache.get("get_abstract", args)
    assert result == payload


@pytest.mark.asyncio
async def test_cache_args_are_canonicalized(isolated_cache_db: Path) -> None:
    payload = json.dumps({"status": "success"})
    await _arxiv_cache.set("get_abstract", {"a": 1, "b": 2}, payload)
    assert await _arxiv_cache.get("get_abstract", {"b": 2, "a": 1}) == payload


@pytest.mark.asyncio
async def test_cache_distinguishes_tools(isolated_cache_db: Path) -> None:
    payload = json.dumps({"status": "success"})
    args = {"paper_id": "2401.0001"}
    await _arxiv_cache.set("get_abstract", args, payload)
    # Same args, different tool → different slot, cache miss.
    assert await _arxiv_cache.get("download_paper", args) is None


@pytest.mark.asyncio
async def test_cache_distinguishes_args(isolated_cache_db: Path) -> None:
    payload = json.dumps({"status": "success"})
    await _arxiv_cache.set("get_abstract", {"paper_id": "A"}, payload)
    assert await _arxiv_cache.get("get_abstract", {"paper_id": "B"}) is None


@pytest.mark.asyncio
async def test_cache_respects_ttl(isolated_cache_db: Path, monkeypatch) -> None:
    args = {"paper_id": "2401.0001"}
    payload = json.dumps({"status": "success"})
    # Set with TTL=0 days then bump the clock forward 1 second by manipulating
    # the stored expires_at directly (faster than sleeping).
    await _arxiv_cache.set("get_abstract", args, payload, ttl_days=0)
    # ttl_days=0 means expires_at = now + 0 = now; one second later it's expired.
    await asyncio.sleep(0.05)  # let SQLite commit
    # Patch time so the expiry check sees a future timestamp.
    real_time = time.time
    monkeypatch.setattr(_arxiv_cache.time, "time", lambda: real_time() + 5.0)
    assert await _arxiv_cache.get("get_abstract", args) is None


@pytest.mark.asyncio
async def test_purge_deletes_expired(isolated_cache_db: Path, monkeypatch) -> None:
    args = {"paper_id": "2401.0001"}
    payload = json.dumps({"status": "success"})
    await _arxiv_cache.set("get_abstract", args, payload, ttl_days=0)
    await asyncio.sleep(0.05)
    real_time = time.time
    monkeypatch.setattr(_arxiv_cache.time, "time", lambda: real_time() + 5.0)
    purged = await _arxiv_cache.purge_expired()
    assert purged >= 1


@pytest.mark.asyncio
async def test_overwrite_existing_entry(isolated_cache_db: Path) -> None:
    args = {"paper_id": "2401.0001"}
    await _arxiv_cache.set("get_abstract", args, "v1", ttl_days=1)
    await _arxiv_cache.set("get_abstract", args, "v2", ttl_days=1)
    assert await _arxiv_cache.get("get_abstract", args) == "v2"
