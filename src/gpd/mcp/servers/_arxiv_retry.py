"""Failure-rate telemetry hook for arxiv tool calls — circuit-breaker scaffolding.

This module is intentionally inert at the decision layer today: the bridge
calls :func:`record_failure` to append a monotonic timestamp every time it
coerces an upstream rate-limit/timeout into an MCP error, but no code branches
on :func:`is_likely_transient` yet. The predicate is the documented hook a
future circuit-breaker will read to decide whether the upstream is "currently
in a failure burst" (within ``_BURST_WINDOW`` of the last failure) versus
"isolated failure that we can attempt again next call." Until that breaker is
wired the per-call behaviour stays "fail fast and let the model route around
via OpenAlex / ar5iv / GCS" — which is what the PR description promised, and
what every existing call site already does.

Keeping the predicate live + tested (rather than deleting it) buys two things:
(a) the rolling log is observable for ad-hoc inspection / scripted probes
without re-instrumenting, and (b) the breaker can land as a one-call diff at
the bridge instead of a multi-file resurrection."""

from __future__ import annotations

import time
from collections import deque

_BURST_WINDOW: float = 30.0
_MAX_LOG: int = 32


def make_failure_log() -> deque[float]:
    return deque(maxlen=_MAX_LOG)


def record_failure(log: deque[float]) -> None:
    log.append(time.monotonic())


def is_likely_transient(log: deque[float]) -> bool:
    """Return True when the last failure is older than the burst window.

    Currently unused by the bridge — see module docstring. Kept live for the
    future circuit-breaker hookup."""

    if not log:
        return True
    return (time.monotonic() - log[-1]) > _BURST_WINDOW
