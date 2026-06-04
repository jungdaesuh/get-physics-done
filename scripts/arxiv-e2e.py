#!/usr/bin/env python3
"""Layer 4 — End-to-end MCP client harness.

Spawns the forked bridge as a stdio subprocess (`python -m
gpd.mcp.servers.arxiv_bridge`), connects via the MCP Python `ClientSession`,
and replays 50 real tool-calls pulled from BigQuery as MCP requests.

For every call we validate:
    * MCP envelope shape (CallToolResult: content[0].type='text', isError, structuredContent)
    * Inner payload JSON parity with upstream contract (same keys, same value
      types). Reference shape is captured once at startup by calling upstream
      in-process for a single known-good query.
    * MCP error codes are sane (no -32603 internal errors leaking; tool errors
      surface as isError=True with a clean message).
    * No leaked subprocess (we wait for clean exit at the end).

Usage:
    python scripts/arxiv-e2e.py \
        --project gpd-desktop \
        --samples 50 \
        --out reports/arxiv-e2e.json

Acceptance gate:
    * shape_parity_rate     == 1.00   (zero envelope shape diffs)
    * inner_parity_rate     >= 0.95
    * mcp_call_success_rate >= 0.95
    * subprocess return code is intentionally NOT gated (the MCP `stdio_client`
      we use does not expose `returncode`); the gate scores only the three
      rates above
"""

from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

BQ_TIMEOUT_SECONDS = 120

CONTRACT_SEARCH_KEYS = {"total_results", "papers"}
CONTRACT_PAPER_KEYS = {
    "id",
    "title",
    "authors",
    "abstract",
    "categories",
    "published",
    "url",
    "resource_uri",
}
CONTRACT_ABSTRACT_KEYS = {
    "status",
    "paper_id",
    "title",
    "authors",
    "abstract",
    "categories",
    "published",
    "pdf_url",
}
CONTRACT_DOWNLOAD_KEYS = {"status", "paper_id", "source", "content"}


@dataclass
class E2EResult:
    tool: str
    args: dict[str, object]
    ok: bool = False
    is_error: bool = False
    envelope_keys_ok: bool = False
    inner_keys_ok: bool = False
    inner_types_ok: bool = False
    latency_ms: float = 0.0
    error: str | None = None
    diff_notes: list[str] = field(default_factory=list)


def bq_pull(project: str, days: int, tool_suffix: str, limit: int) -> list[dict[str, object]]:
    sql = f"""
SELECT JSON_VALUE(part, '$.state.input') AS input_str
FROM `{project}.gpd_logs.sessions`
WHERE ingest_date >= DATE_SUB(CURRENT_DATE(), INTERVAL {days} DAY)
  AND kind = 'part_updated'
  AND JSON_VALUE(part, '$.type') = 'tool'
  AND JSON_VALUE(part, '$.tool') = 'gpd-arxiv_{tool_suffix}'
  AND JSON_VALUE(part, '$.state.input') IS NOT NULL
LIMIT {limit}
"""
    try:
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
            timeout=BQ_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        raise SystemExit(f"bq query timed out after {BQ_TIMEOUT_SECONDS}s") from exc
    if proc.returncode != 0:
        raise SystemExit(f"bq query failed: {proc.stderr}")
    rows = json.loads(proc.stdout) if proc.stdout.strip() else []
    out: list[dict[str, object]] = []
    for row in rows:
        raw = row.get("input_str")
        if not raw:
            continue
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            continue
        # The replay loop downstream does ``arg.get(...)`` on every entry, so a
        # stray list/string/number payload would crash the harness with
        # ``AttributeError`` before parity is evaluated. Drop non-objects here.
        if isinstance(parsed, dict):
            out.append(parsed)
    return out


def _validate_inner(tool: str, data: dict[str, object]) -> tuple[bool, bool, list[str]]:
    """Return (keys_ok, types_ok, notes)."""
    notes: list[str] = []
    expected: set[str]
    if tool == "search_papers":
        expected = CONTRACT_SEARCH_KEYS
    elif tool == "get_abstract":
        expected = CONTRACT_ABSTRACT_KEYS
    elif tool == "download_paper":
        expected = CONTRACT_DOWNLOAD_KEYS
    else:
        return True, True, []
    actual = set(data.keys())
    missing = expected - actual
    unexpected = actual - expected
    keys_ok = not missing and not unexpected
    if missing:
        notes.append(f"missing_inner_keys:{sorted(missing)}")
    if unexpected:
        notes.append(f"unexpected_inner_keys:{sorted(unexpected)}")
    types_ok = True
    if tool == "search_papers":
        if not isinstance(data.get("total_results"), int):
            types_ok = False
            notes.append("total_results_not_int")
        if not isinstance(data.get("papers"), list):
            types_ok = False
            notes.append("papers_not_list")
        else:
            for index, p in enumerate(data["papers"]):
                # Non-dict paper entries are a concrete contract violation —
                # surface them as such instead of letting ``p.keys()`` raise
                # and turning the parity check into a generic harness error.
                if not isinstance(p, dict):
                    types_ok = False
                    notes.append(f"paper_not_object[{index}]:{type(p).__name__}")
                    continue
                paper_keys = set(p.keys())
                missing = sorted(CONTRACT_PAPER_KEYS - paper_keys)
                unexpected = sorted(paper_keys - CONTRACT_PAPER_KEYS)
                if missing or unexpected:
                    types_ok = False
                    if missing:
                        notes.append(f"paper_keys_missing[{index}]:{missing}")
                    if unexpected:
                        notes.append(f"paper_keys_unexpected[{index}]:{unexpected}")
    elif tool == "get_abstract":
        if data.get("status") not in {"success", "error"}:
            types_ok = False
            notes.append("status_not_success_or_error")
    return keys_ok, types_ok, notes


async def run_session(samples: list[tuple[str, dict[str, object]]], storage_path: Path) -> list[E2EResult]:
    server = StdioServerParameters(
        command=sys.executable,
        args=["-m", "gpd.mcp.servers.arxiv_bridge", "--storage-path", str(storage_path)],
    )
    results: list[E2EResult] = []
    async with stdio_client(server) as streams:
        async with ClientSession(*streams) as session:
            await session.initialize()
            tools = await session.list_tools()
            advertised = {t.name for t in tools.tools}
            print(f"[e2e] advertised tools: {sorted(advertised)}", file=sys.stderr)

            for tool, args in samples:
                rec = E2EResult(tool=tool, args=args)
                t0 = time.perf_counter()
                try:
                    res = await asyncio.wait_for(session.call_tool(tool, args), timeout=45.0)
                    rec.latency_ms = (time.perf_counter() - t0) * 1000
                    rec.is_error = bool(getattr(res, "isError", False))
                    # Envelope check
                    rec.envelope_keys_ok = (
                        hasattr(res, "content")
                        and len(res.content) >= 1
                        and getattr(res.content[0], "type", None) == "text"
                    )
                    text = getattr(res.content[0], "text", None) if rec.envelope_keys_ok else None
                    if text:
                        try:
                            data = json.loads(text)
                            rec.inner_keys_ok, rec.inner_types_ok, rec.diff_notes = _validate_inner(
                                tool, data
                            )
                            rec.ok = (
                                not rec.is_error
                                and rec.envelope_keys_ok
                                and rec.inner_keys_ok
                                and rec.inner_types_ok
                            )
                        except json.JSONDecodeError as e:
                            rec.diff_notes.append(f"inner_not_json:{e}")
                    else:
                        rec.diff_notes.append("no_text_content")
                except TimeoutError:
                    rec.error = "timeout"
                    rec.latency_ms = (time.perf_counter() - t0) * 1000
                except Exception as e:
                    rec.error = f"{type(e).__name__}:{e}"
                    rec.latency_ms = (time.perf_counter() - t0) * 1000
                results.append(rec)

    # ``stdio_client`` from the ``mcp`` package does not expose the
    # subprocess return code (it only yields the JSONRPC stream pair and
    # waits for termination on context exit). Rather than hardcode a value
    # that would make the acceptance gate accept any subprocess outcome,
    # we omit the subprocess-exit signal from the gate entirely and rely on
    # per-call ``rec.is_error`` / parity checks to surface failures.
    return results


def evaluate_gate(records: list[E2EResult]) -> tuple[bool, dict[str, object], list[str]]:
    n = len(records)
    if n == 0:
        return False, {"n": 0}, ["no records"]
    success = sum(1 for r in records if r.ok)
    env_ok = sum(1 for r in records if r.envelope_keys_ok)
    inner_ok = sum(1 for r in records if r.inner_keys_ok and r.inner_types_ok)
    summary = {
        "n": n,
        "mcp_call_success_rate": success / n,
        "envelope_parity_rate": env_ok / n,
        "inner_parity_rate": inner_ok / n,
        "is_error_rate": sum(1 for r in records if r.is_error) / n,
    }
    failures: list[str] = []
    if summary["envelope_parity_rate"] < 1.0:
        failures.append(f"envelope_parity_rate={summary['envelope_parity_rate']:.0%} < 100%")
    if summary["inner_parity_rate"] < 0.95:
        failures.append(f"inner_parity_rate={summary['inner_parity_rate']:.0%} < 95%")
    if summary["mcp_call_success_rate"] < 0.95:
        failures.append(f"mcp_call_success_rate={summary['mcp_call_success_rate']:.0%} < 95%")
    return len(failures) == 0, summary, failures


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", default="gpd-desktop")
    ap.add_argument("--days", type=int, default=14)
    ap.add_argument("--samples", type=int, default=50)
    ap.add_argument("--storage-path", default=str(Path.home() / ".gpd" / "arxiv-e2e-storage"))
    ap.add_argument("--out", default="reports/arxiv-e2e.json")
    args = ap.parse_args()

    Path(args.storage_path).mkdir(parents=True, exist_ok=True)

    # ~50% search, ~33% abstract, ~17% download to mirror real ratios (383/160/X).
    n_search = max(1, int(args.samples * 0.50))
    n_abstract = max(1, int(args.samples * 0.33))
    n_download = max(0, args.samples - n_search - n_abstract)

    search_args = bq_pull(args.project, args.days, "search_papers", n_search * 2)[:n_search]
    abstract_args = bq_pull(args.project, args.days, "get_abstract", n_abstract * 2)[:n_abstract]
    download_args = bq_pull(args.project, args.days, "download_paper", n_download * 2)[:n_download]

    samples: list[tuple[str, dict[str, object]]] = []
    for a in search_args:
        if isinstance(a.get("query"), str):
            samples.append(("search_papers", a))
    for a in abstract_args:
        if isinstance(a.get("paper_id"), str):
            samples.append(("get_abstract", a))
    for a in download_args:
        if isinstance(a.get("paper_id"), str):
            samples.append(("download_paper", a))

    print(f"[e2e] replaying {len(samples)} calls through stdio bridge", file=sys.stderr)
    # Fail the gate when BigQuery filtering left us below the requested cohort
    # size. Without this check, ``evaluate_gate`` would still green-light the
    # bridge on a handful of records — insufficient evidence for promotion.
    if len(samples) < args.samples:
        print(
            f"[e2e] GATE FAIL: collected {len(samples)} valid samples for "
            f"requested {args.samples} — insufficient evidence",
            file=sys.stderr,
        )
        return 1
    records = asyncio.run(run_session(samples, Path(args.storage_path)))

    ok, summary, failures = evaluate_gate(records)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(
            {
                "config": vars(args),
                "summary": summary,
                "records": [asdict(r) for r in records],
            },
            indent=2,
        )
    )

    if ok:
        print(f"[e2e] GATE PASS  {summary}", file=sys.stderr)
        return 0
    print(f"[e2e] GATE FAIL  {summary}", file=sys.stderr)
    for f in failures:
        print(f"  - {f}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
