"""SQLite-backed cache for arxiv tool results."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import sqlite3
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

logger = logging.getLogger("gpd.arxiv_bridge.cache")

_CACHE_DIR = Path.home() / ".arxiv-mcp-server"
_CACHE_DB = _CACHE_DIR / "cache.sqlite"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS arxiv_cache (
    tool TEXT NOT NULL,
    args_hash TEXT NOT NULL,
    payload TEXT NOT NULL,
    expires_at REAL NOT NULL,
    PRIMARY KEY (tool, args_hash)
)
"""


def _canonicalize_args(args: dict[str, object]) -> str:
    return json.dumps(args, sort_keys=True, separators=(",", ":"), default=str)


def _hash_args(args: dict[str, object]) -> str:
    return hashlib.sha256(_canonicalize_args(args).encode("utf-8")).hexdigest()


@contextmanager
def _connect() -> Iterator[sqlite3.Connection]:
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(_CACHE_DB), timeout=5.0, isolation_level=None)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute(_SCHEMA)
        yield conn
    finally:
        conn.close()


def _get_sync(tool: str, args: dict[str, object]) -> str | None:
    key = _hash_args(args)
    now = time.time()
    try:
        with _connect() as conn:
            row = conn.execute(
                "SELECT payload FROM arxiv_cache "
                "WHERE tool = ? AND args_hash = ? AND expires_at > ?",
                (tool, key, now),
            ).fetchone()
            if row is None:
                return None
            return row[0]
    except sqlite3.Error as exc:
        logger.info("cache get failed for %s/%s: %s", tool, key[:12], exc)
        return None


def _set_sync(
    tool: str, args: dict[str, object], payload: str, ttl_seconds: float
) -> None:
    key = _hash_args(args)
    expires_at = time.time() + ttl_seconds
    try:
        with _connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO arxiv_cache (tool, args_hash, payload, expires_at) "
                "VALUES (?, ?, ?, ?)",
                (tool, key, payload, expires_at),
            )
    except sqlite3.Error as exc:
        logger.info("cache set failed for %s/%s: %s", tool, key[:12], exc)


async def get(tool: str, args: dict[str, object]) -> str | None:
    return await asyncio.to_thread(_get_sync, tool, args)


async def set(
    tool: str, args: dict[str, object], payload: str, ttl_days: int = 30
) -> None:
    ttl_seconds = float(ttl_days) * 86400.0
    await asyncio.to_thread(_set_sync, tool, args, payload, ttl_seconds)


async def purge_expired() -> int:
    def _purge() -> int:
        try:
            with _connect() as conn:
                cur = conn.execute(
                    "DELETE FROM arxiv_cache WHERE expires_at <= ?", (time.time(),)
                )
                return cur.rowcount
        except sqlite3.Error as exc:
            logger.info("cache purge failed: %s", exc)
            return 0
    return await asyncio.to_thread(_purge)


def _cache_db_path() -> Path:
    return _CACHE_DB
