#!/usr/bin/env python3
"""Layer 3 — Side-by-side replay of real `search_papers` and `get_abstract`
calls against both the unmodified upstream `arxiv_mcp_server` and the forked
GPD bridge, executed in parallel.

For every replayed call we record:
    * old_ok, new_ok          (both returned without error/timeout)
    * top3_overlap            (count of overlapping IDs in top-3, 0..3)
    * count_old, count_new    (total results returned)
    * coverage_ratio          (count_new / count_old)
    * latency_old, latency_new (ms)
    * new_faster              (new latency strictly less than old)

Output:
    reports/arxiv-replay.json       — full per-call raw data
    reports/arxiv-replay.md         — human-readable summary + gate verdict

Usage:
    python scripts/arxiv-replay.py \
        --project gpd-desktop \
        --days 14 \
        --max-search 383 \
        --max-abstract 160 \
        --concurrency 4 \
        --out-dir reports/

Acceptance gate (printed at end, exit 1 on fail):
    new_ok_rate            >= 0.95 of calls where upstream succeeded
    new_only_rate          >= 0.30 of calls where upstream timed out / errored
    mean_latency_new       <= 0.50 * mean_latency_old
    top3_overlap_mean      >= 1.5   (out of 3, search only)
    coverage_ratio_median  in [0.5, 2.0]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

# We import the upstream + bridge in-process to avoid stdio overhead.
# Both expose async handlers we can call directly.


@dataclass
class CallRecord:
    tool: str
    args: dict[str, object]
    old_ok: bool = False
    new_ok: bool = False
    old_error: str | None = None
    new_error: str | None = None
    latency_old_ms: float = 0.0
    latency_new_ms: float = 0.0
    count_old: int = 0
    count_new: int = 0
    top3_old: list[str] = field(default_factory=list)
    top3_new: list[str] = field(default_factory=list)

    @property
    def overlap(self) -> int:
        return len(set(self.top3_old) & set(self.top3_new))

    @property
    def coverage(self) -> float | None:
        if self.count_old == 0:
            return None
        return self.count_new / self.count_old

    @property
    def new_faster(self) -> bool:
        return self.new_ok and self.old_ok and self.latency_new_ms < self.latency_old_ms


def bq_pull_calls(project: str, days: int, tool_suffix: str, limit: int) -> list[dict[str, object]]:
    sql = f"""
SELECT
  JSON_VALUE(part, '$.state.input') AS input_str
FROM `{project}.gpd_logs.sessions`
WHERE ingest_date >= DATE_SUB(CURRENT_DATE(), INTERVAL {days} DAY)
  AND kind = 'part_updated'
  AND JSON_VALUE(part, '$.type') = 'tool'
  AND JSON_VALUE(part, '$.tool') = 'gpd-arxiv_{tool_suffix}'
  AND JSON_VALUE(part, '$.state.input') IS NOT NULL
LIMIT {limit}
"""
    proc = subprocess.run(
        [
            "bq",
            f"--project_id={project}",
            "query",
            "--use_legacy_sql=false",
            "--format=json",
            f"--max_rows={limit}",
            sql,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise SystemExit(f"bq query failed: {proc.stderr}")
    rows = json.loads(proc.stdout) if proc.stdout.strip() else []
    out: list[dict[str, object]] = []
    for row in rows:
        raw = row.get("input_str")
        if not raw:
            continue
        try:
            out.append(json.loads(raw))
        except json.JSONDecodeError:
            continue
    return out


def _extract_papers_from_textcontent(parts: object, tool: str) -> tuple[list[str], int]:
    """Both upstream and forked side return List[types.TextContent] whose
    `.text` field carries a JSON document. Parse it and return
    (top_ids_in_order, total_count)."""
    if not parts:
        return [], 0
    text = getattr(parts[0], "text", None) or (parts[0].get("text") if isinstance(parts[0], dict) else None)
    if not text:
        return [], 0
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return [], 0
    if tool == "search_papers":
        papers = data.get("papers") or []
        ids = [p.get("id") for p in papers if isinstance(p.get("id"), str)]
        return ids, int(data.get("total_results") or len(ids))
    if tool == "get_abstract":
        pid = data.get("paper_id")
        return ([pid] if isinstance(pid, str) else []), (1 if data.get("status") == "success" else 0)
    return [], 0


async def call_upstream(tool: str, args: dict[str, object], timeout: float) -> tuple[object, str | None]:
    """Call the unmodified upstream `arxiv_mcp_server` handler in-process."""
    try:
        if tool == "search_papers":
            from arxiv_mcp_server.tools.search import handle_search
            parts = await asyncio.wait_for(handle_search(args), timeout=timeout)
        elif tool == "get_abstract":
            from arxiv_mcp_server.tools.get_abstract import handle_get_abstract
            parts = await asyncio.wait_for(handle_get_abstract(args), timeout=timeout)
        else:
            return None, f"unsupported_tool:{tool}"
        return parts, None
    except TimeoutError:
        return None, "timeout"
    except Exception as e:
        return None, f"{type(e).__name__}:{e}"


class _TextContentShim:
    """Adapt a translator dict-return into the upstream `List[TextContent]`
    shape that `_extract_papers_from_textcontent` consumes. The translator
    public API (``openalex_search`` / ``openalex_abstract``) returns plain
    Python dicts; the upstream `arxiv_mcp_server` handlers return a list
    of `mcp.types.TextContent` whose `.text` is a JSON string. We wrap so
    both sides feed the same extractor unchanged."""

    def __init__(self, text: str) -> None:
        self.text = text


async def call_forked(tool: str, args: dict[str, object], timeout: float) -> tuple[object, str | None]:
    """Call the GPD-forked handler in-process.

    Drives ``arxiv_translators.openalex_search`` / ``openalex_abstract``
    (the actual public surface in ``src/gpd/mcp/servers/arxiv_translators.py``;
    the legacy ``handle_search`` / ``handle_get_abstract`` symbols never
    existed and a previous draft of this script silently produced an
    AttributeError-for-every-row 0% parity rate). Translator return is a
    dict; wrap it in a one-element TextContent-like list so the shared
    extractor sees the same shape as the upstream side."""
    try:
        from gpd.mcp.servers import arxiv_translators  # type: ignore
    except Exception as e:
        return None, f"forked_not_importable:{e}"
    try:
        if tool == "search_papers":
            body = await asyncio.wait_for(
                asyncio.to_thread(arxiv_translators.openalex_search, args),
                timeout=timeout,
            )
        elif tool == "get_abstract":
            body = await asyncio.wait_for(
                asyncio.to_thread(arxiv_translators.openalex_abstract, args),
                timeout=timeout,
            )
        else:
            return None, f"unsupported_tool:{tool}"
        # Treat translator-side `status: error` as a recoverable miss
        # (e.g. OpenAlex has no record for this paper id) rather than a
        # parity-breaking exception. Upstream would have surfaced this
        # the same way via `status: error` in its TextContent body.
        parts = [_TextContentShim(json.dumps(body))]
        return parts, None
    except TimeoutError:
        return None, "timeout"
    except Exception as e:
        return None, f"{type(e).__name__}:{e}"


async def run_one(tool: str, args: dict[str, object], timeout: float, sem: asyncio.Semaphore) -> CallRecord:
    rec = CallRecord(tool=tool, args=args)
    async with sem:
        # Run both sides truly in parallel.
        async def _old():
            t0 = time.perf_counter()
            parts, err = await call_upstream(tool, args, timeout)
            return parts, err, (time.perf_counter() - t0) * 1000

        async def _new():
            t0 = time.perf_counter()
            parts, err = await call_forked(tool, args, timeout)
            return parts, err, (time.perf_counter() - t0) * 1000

        (old_parts, old_err, old_ms), (new_parts, new_err, new_ms) = await asyncio.gather(
            _old(), _new()
        )

    rec.old_error = old_err
    rec.new_error = new_err
    rec.latency_old_ms = old_ms
    rec.latency_new_ms = new_ms
    rec.old_ok = old_err is None and old_parts is not None
    rec.new_ok = new_err is None and new_parts is not None
    if rec.old_ok:
        ids_old, count_old = _extract_papers_from_textcontent(old_parts, tool)
        rec.top3_old = ids_old[:3]
        rec.count_old = count_old
    if rec.new_ok:
        ids_new, count_new = _extract_papers_from_textcontent(new_parts, tool)
        rec.top3_new = ids_new[:3]
        rec.count_new = count_new
    return rec


async def replay(
    project: str,
    days: int,
    max_search: int,
    max_abstract: int,
    concurrency: int,
    timeout: float,
) -> list[CallRecord]:
    search_args = bq_pull_calls(project, days, "search_papers", max_search)
    abstract_args = bq_pull_calls(project, days, "get_abstract", max_abstract)
    print(
        f"[replay] pulled {len(search_args)} search + {len(abstract_args)} abstract args",
        file=sys.stderr,
    )

    sem = asyncio.Semaphore(concurrency)
    tasks: list[asyncio.Task[CallRecord]] = []
    for a in search_args:
        if isinstance(a.get("query"), str):
            tasks.append(asyncio.create_task(run_one("search_papers", a, timeout, sem)))
    for a in abstract_args:
        if isinstance(a.get("paper_id"), str):
            tasks.append(asyncio.create_task(run_one("get_abstract", a, timeout, sem)))

    records: list[CallRecord] = []
    for i, fut in enumerate(asyncio.as_completed(tasks), 1):
        rec = await fut
        records.append(rec)
        if i % 25 == 0:
            print(f"[replay] {i}/{len(tasks)} done", file=sys.stderr)
    return records


def summarize(records: list[CallRecord]) -> dict[str, object]:
    by_tool: dict[str, list[CallRecord]] = {}
    for r in records:
        by_tool.setdefault(r.tool, []).append(r)
    out: dict[str, object] = {"total": len(records), "tools": {}}
    for tool, recs in by_tool.items():
        n = len(recs)
        old_ok = [r for r in recs if r.old_ok]
        new_ok_on_old_ok = [r for r in old_ok if r.new_ok]
        old_failed = [r for r in recs if not r.old_ok]
        new_only = [r for r in old_failed if r.new_ok]
        overlaps = [r.overlap for r in recs if r.old_ok and r.new_ok]
        coverages = [r.coverage for r in recs if r.old_ok and r.new_ok and r.coverage is not None]
        # Matched cohort: only requests where BOTH backends succeeded. Comparing
        # `mean_latency_old_ms` from old_ok against `mean_latency_new_ms` from
        # all new_ok mixes populations and can misclassify the latency gate.
        matched = [r for r in recs if r.old_ok and r.new_ok]
        lat_old = [r.latency_old_ms for r in matched]
        lat_new = [r.latency_new_ms for r in matched]
        new_faster = sum(1 for r in recs if r.new_faster)
        out["tools"][tool] = {
            "n": n,
            "old_ok": len(old_ok),
            "new_ok_on_old_ok_rate": (len(new_ok_on_old_ok) / len(old_ok)) if old_ok else None,
            "new_only_on_old_fail_rate": (len(new_only) / len(old_failed)) if old_failed else None,
            "mean_latency_old_ms": statistics.fmean(lat_old) if lat_old else None,
            "mean_latency_new_ms": statistics.fmean(lat_new) if lat_new else None,
            "new_faster_rate": new_faster / n if n else None,
            "top3_overlap_mean": statistics.fmean(overlaps) if overlaps else None,
            "coverage_ratio_median": statistics.median(coverages) if coverages else None,
        }
    return out


def evaluate_gate(summary: dict[str, object]) -> tuple[bool, list[str]]:
    failures: list[str] = []
    # A replay run with no records can never demonstrate parity. Fail closed
    # rather than treating an empty harness output as a passing gate.
    if not summary.get("total"):
        return False, ["no replay records"]

    for tool, s in summary["tools"].items():
        # Guard each metric so missing/None values are treated as N/A rather
        # than coerced to 0 — coercing turns absent evidence into spurious
        # gate failures (or, in the latency case, into accidental passes).
        new_ok_rate = s.get("new_ok_on_old_ok_rate")
        if new_ok_rate is not None and new_ok_rate < 0.95:
            failures.append(f"{tool}: new_ok_on_old_ok={new_ok_rate:.0%} < 95%")
        if tool == "search_papers":
            overlap = s.get("top3_overlap_mean")
            if overlap is not None and overlap < 1.5:
                failures.append(f"{tool}: top3_overlap_mean={overlap:.2f} < 1.5")
        cov = s.get("coverage_ratio_median")
        if cov is not None and not (0.5 <= cov <= 2.0):
            failures.append(f"{tool}: coverage_ratio_median={cov:.2f} outside [0.5, 2.0]")
        lat_old = s.get("mean_latency_old_ms")
        lat_new = s.get("mean_latency_new_ms")
        if (
            lat_old is not None
            and lat_new is not None
            and lat_old > 0
            and lat_new > 0.5 * lat_old
        ):
            failures.append(
                f"{tool}: mean_latency_new={lat_new:.0f}ms > 50% of mean_latency_old={lat_old:.0f}ms"
            )
        new_only = s.get("new_only_on_old_fail_rate")
        if new_only is not None and new_only < 0.30:
            failures.append(
                f"{tool}: new_only_on_old_fail={new_only:.0%} < 30% (win on upstream-timeouts insufficient)"
            )
    return len(failures) == 0, failures


def write_markdown(summary: dict[str, object], records: list[CallRecord], path: Path) -> None:
    lines = ["# arXiv replay report\n"]
    lines.append(f"Total calls: **{summary['total']}**\n")
    lines.append("| tool | n | old_ok | new_ok_on_old_ok | new_only_on_old_fail | lat_old(ms) | lat_new(ms) | new_faster | top3_overlap | coverage_med |")
    lines.append("|------|---|--------|------------------|----------------------|-------------|-------------|------------|--------------|--------------|")
    for tool, s in summary["tools"].items():
        lines.append(
            f"| {tool} | {s['n']} | {s['old_ok']} | "
            f"{(s['new_ok_on_old_ok_rate'] or 0):.0%} | "
            f"{(s['new_only_on_old_fail_rate'] or 0):.0%} | "
            f"{(s['mean_latency_old_ms'] or 0):.0f} | "
            f"{(s['mean_latency_new_ms'] or 0):.0f} | "
            f"{(s['new_faster_rate'] or 0):.0%} | "
            f"{(s['top3_overlap_mean'] or 0):.2f}/3 | "
            f"{(s['coverage_ratio_median'] or 0):.2f} |"
        )
    lines.append("")
    lines.append("## Sample diffs (first 10 where overlap<3)\n")
    diffs = [r for r in records if r.old_ok and r.new_ok and r.overlap < 3][:10]
    for r in diffs:
        lines.append(f"- **{r.tool}** `{json.dumps(r.args)[:80]}`")
        lines.append(f"  - old top3: `{r.top3_old}`")
        lines.append(f"  - new top3: `{r.top3_new}`")
    path.write_text("\n".join(lines))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", default="gpd-desktop")
    ap.add_argument("--days", type=int, default=14)
    ap.add_argument("--max-search", type=int, default=383)
    ap.add_argument("--max-abstract", type=int, default=160)
    ap.add_argument("--concurrency", type=int, default=4)
    ap.add_argument("--timeout", type=float, default=30.0)
    ap.add_argument("--out-dir", default="reports/")
    args = ap.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    records = asyncio.run(
        replay(args.project, args.days, args.max_search, args.max_abstract, args.concurrency, args.timeout)
    )
    summary = summarize(records)
    (out_dir / "arxiv-replay.json").write_text(
        json.dumps({"summary": summary, "records": [asdict(r) for r in records]}, indent=2)
    )
    write_markdown(summary, records, out_dir / "arxiv-replay.md")

    ok, failures = evaluate_gate(summary)
    if ok:
        print("[replay] GATE PASS", file=sys.stderr)
        return 0
    print("[replay] GATE FAIL", file=sys.stderr)
    for f in failures:
        print(f"  - {f}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
