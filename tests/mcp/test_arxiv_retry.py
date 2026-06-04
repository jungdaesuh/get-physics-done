"""Unit tests for the retry-gating predicate."""

from __future__ import annotations

import time

from gpd.mcp.servers import _arxiv_retry


def test_empty_log_is_transient() -> None:
    log = _arxiv_retry.make_failure_log()
    assert _arxiv_retry.is_likely_transient(log) is True


def test_old_failure_is_transient() -> None:
    log = _arxiv_retry.make_failure_log()
    # Pretend the last failure was 60 s ago (outside the burst window).
    log.append(time.monotonic() - 60.0)
    assert _arxiv_retry.is_likely_transient(log) is True


def test_recent_failure_is_not_transient() -> None:
    log = _arxiv_retry.make_failure_log()
    # 5 s ago: well inside the 30 s burst window.
    log.append(time.monotonic() - 5.0)
    assert _arxiv_retry.is_likely_transient(log) is False


def test_record_failure_makes_next_failure_part_of_burst() -> None:
    log = _arxiv_retry.make_failure_log()
    _arxiv_retry.record_failure(log)
    assert _arxiv_retry.is_likely_transient(log) is False


def test_log_is_bounded() -> None:
    log = _arxiv_retry.make_failure_log()
    for _ in range(1000):
        _arxiv_retry.record_failure(log)
    # The deque maxlen caps growth so a long-lived bridge doesn't leak memory.
    assert len(log) <= _arxiv_retry._MAX_LOG
