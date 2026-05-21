#!/usr/bin/env python3
"""Layer 1 — Upstream probes for the arXiv-MCP replacement.

Hits each candidate replacement upstream (OpenAlex, ar5iv, gs://arxiv-dataset)
with real queries pulled from BigQuery and reports per-endpoint reachability,
latency p50/p95, payload size, and whether arxiv IDs can be extracted.

This script does NOT touch the bridge or the upstream arxiv_mcp_server. It is
the cheapest layer: ~30 HTTP requests, runs in under a minute, validates that
each replacement is reachable and fast enough before any code is written.

Usage:
    python scripts/arxiv-probe.py \
        --project gpd-desktop \
        --days 14 \
        --search-samples 15 \
        --abstract-samples 15 \
        --download-samples 10 \
        --out reports/arxiv-probe.json

Pass criteria (per endpoint):
    - >= 95% success across samples
    - p95 latency < 5000 ms
    - >= 95% of search responses produce at least 1 extractable arxiv ID
    - GCS HEAD on gs://arxiv-dataset/arxiv/arxiv/pdf/<yymm>/<id>vN.pdf returns
      object exists for >= 90% of sampled paper IDs
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from urllib.parse import quote_plus

import httpx

BQ_TIMEOUT_SECONDS = 120

OPENALEX_WORKS = "https://api.openalex.org/works"
AR5IV_BASE = "https://ar5iv.labs.arxiv.org/html"
GCS_API = "https://storage.googleapis.com/storage/v1/b/arxiv-dataset/o"

ARXIV_ID_RE = re.compile(
    r"\b(?:(?:arxiv:)?(\d{4}\.\d{4,5})(?:v\d+)?|([a-z\-]+(?:\.[A-Z]{2})?/\d{7})(?:v\d+)?)\b",
    re.IGNORECASE,
)

USER_AGENT = "gpd-arxiv-probe/0.1 (mailto:cameron@psi.inc)"


@dataclass
class ProbeResult:
    label: str
    upstream: str
    ok: bool
    status: int | None
    latency_ms: float
    bytes_in: int
    extracted_ids: list[str] = field(default_factory=list)
    error: str | None = None


@dataclass
class EndpointReport:
    upstream: str
    samples: int = 0
    successes: int = 0
    latencies_ms: list[float] = field(default_factory=list)
    bytes_in_total: int = 0
    id_extract_successes: int = 0
    errors: list[str] = field(default_factory=list)

    def add(self, r: ProbeResult) -> None:
        self.samples += 1
        if r.ok:
            self.successes += 1
            self.latencies_ms.append(r.latency_ms)
            self.bytes_in_total += r.bytes_in
            if r.extracted_ids:
                self.id_extract_successes += 1
        else:
            self.errors.append(r.error or f"status={r.status}")

    def summary(self) -> dict[str, object]:
        lat = sorted(self.latencies_ms)
        p50 = statistics.median(lat) if lat else None
        p95 = lat[int(len(lat) * 0.95) - 1] if len(lat) >= 20 else (lat[-1] if lat else None)
        return {
            "upstream": self.upstream,
            "samples": self.samples,
            "success_rate": self.successes / self.samples if self.samples else 0.0,
            "p50_ms": p50,
            "p95_ms": p95,
            "mean_bytes": (self.bytes_in_total / self.successes) if self.successes else 0,
            "id_extract_rate": (
                self.id_extract_successes / self.successes if self.successes else 0.0
            ),
            "error_sample": self.errors[:5],
        }


def bq_pull(project: str, days: int, tool_suffix: str, limit: int) -> list[dict[str, object]]:
    """Pull recent tool-call args from BigQuery via the `bq` CLI."""
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
    parsed: list[dict[str, object]] = []
    for row in rows:
        raw = row.get("input_str")
        if not raw:
            continue
        try:
            item = json.loads(raw)
        except json.JSONDecodeError:
            continue
        # Downstream consumers call ``.get(...)`` on every entry, so a stray
        # list/string/number payload would abort the probe with
        # ``AttributeError``. Treat non-objects as bad input and skip.
        if isinstance(item, dict):
            parsed.append(item)
    return parsed


def extract_arxiv_ids(text: str, limit: int = 50) -> list[str]:
    seen: list[str] = []
    for m in ARXIV_ID_RE.finditer(text or ""):
        pid = (m.group(1) or m.group(2) or "").lower()
        if pid and pid not in seen:
            seen.append(pid)
            if len(seen) >= limit:
                break
    return seen


def probe_openalex_search(client: httpx.Client, query: str) -> ProbeResult:
    # Match the live translator's filter exactly — see
    # OPENALEX_ARXIV_SOURCE_ID in arxiv_translators.py for the canonical
    # source id and the live verification trail. Anything else and the
    # probe measures a different cohort than production hits.
    from gpd.mcp.servers.arxiv_translators import OPENALEX_ARXIV_SOURCE_ID

    url = (
        f"{OPENALEX_WORKS}?search={quote_plus(query)}&per-page=10"
        f"&filter=primary_location.source.id:{OPENALEX_ARXIV_SOURCE_ID}"
    )
    t0 = time.perf_counter()
    try:
        r = client.get(url, timeout=15.0)
        latency = (time.perf_counter() - t0) * 1000
        body = r.content
        ids: list[str] = []
        if r.status_code == 200:
            data = r.json()
            for w in data.get("results", []):
                for loc in (w.get("locations") or []) + [w.get("primary_location") or {}]:
                    pdf_url = (loc or {}).get("pdf_url") or ""
                    landing = (loc or {}).get("landing_page_url") or ""
                    for src in (pdf_url, landing):
                        ids.extend(extract_arxiv_ids(src))
                if w.get("doi"):
                    ids.extend(extract_arxiv_ids(w["doi"]))
        return ProbeResult(
            label=f"search:{query[:40]}",
            upstream="openalex.search",
            ok=r.status_code == 200,
            status=r.status_code,
            latency_ms=latency,
            bytes_in=len(body),
            extracted_ids=list(dict.fromkeys(ids))[:20],
        )
    except Exception as e:
        return ProbeResult(
            label=f"search:{query[:40]}",
            upstream="openalex.search",
            ok=False,
            status=None,
            latency_ms=(time.perf_counter() - t0) * 1000,
            bytes_in=0,
            error=repr(e),
        )


def probe_openalex_abstract(client: httpx.Client, paper_id: str) -> ProbeResult:
    # OpenAlex supports filter=ids.arxiv:<id>
    url = f"{OPENALEX_WORKS}?filter=ids.arxiv:{paper_id}&per-page=1"
    t0 = time.perf_counter()
    try:
        r = client.get(url, timeout=15.0)
        latency = (time.perf_counter() - t0) * 1000
        body = r.content
        has_abstract = False
        if r.status_code == 200:
            data = r.json()
            results = data.get("results") or []
            if results:
                inv = results[0].get("abstract_inverted_index")
                has_abstract = bool(inv)
        return ProbeResult(
            label=f"abstract:{paper_id}",
            upstream="openalex.abstract",
            ok=r.status_code == 200 and has_abstract,
            status=r.status_code,
            latency_ms=latency,
            bytes_in=len(body),
            extracted_ids=[paper_id] if has_abstract else [],
            error=None if has_abstract else "no_abstract_inverted_index",
        )
    except Exception as e:
        return ProbeResult(
            label=f"abstract:{paper_id}",
            upstream="openalex.abstract",
            ok=False,
            status=None,
            latency_ms=(time.perf_counter() - t0) * 1000,
            bytes_in=0,
            error=repr(e),
        )


def probe_ar5iv(client: httpx.Client, paper_id: str) -> ProbeResult:
    url = f"{AR5IV_BASE}/{paper_id}"
    t0 = time.perf_counter()
    try:
        r = client.get(url, timeout=20.0, follow_redirects=True)
        latency = (time.perf_counter() - t0) * 1000
        body = r.content
        # ar5iv returns 200 even for fallbacks; check Content-Type + size
        looks_like_paper = (
            r.status_code == 200
            and "text/html" in r.headers.get("content-type", "")
            and len(body) > 5000
        )
        return ProbeResult(
            label=f"ar5iv:{paper_id}",
            upstream="ar5iv.html",
            ok=looks_like_paper,
            status=r.status_code,
            latency_ms=latency,
            bytes_in=len(body),
            extracted_ids=[paper_id] if looks_like_paper else [],
            error=None if looks_like_paper else f"thin_or_non_html:{len(body)}b",
        )
    except Exception as e:
        return ProbeResult(
            label=f"ar5iv:{paper_id}",
            upstream="ar5iv.html",
            ok=False,
            status=None,
            latency_ms=(time.perf_counter() - t0) * 1000,
            bytes_in=0,
            error=repr(e),
        )


def gcs_pdf_object_path(paper_id: str) -> str:
    """Map an arXiv ID to its canonical gs://arxiv-dataset object path.

    For new-format IDs YYMM.NNNNN -> arxiv/arxiv/pdf/YYMM/<id>v<latest>.pdf
    For old-format IDs cat.NN/YYMMNNN -> arxiv/<cat>/pdf/YYMM/<id>v<latest>.pdf

    We don't know the version up front; the probe checks for v1..v9.
    """
    pid = paper_id.lower().split("v")[0]
    if "/" in pid:
        cat, num = pid.split("/", 1)
        yymm = num[:4]
        return f"arxiv/{cat}/pdf/{yymm}/{num.replace('/', '')}"
    yymm = pid.split(".")[0]
    return f"arxiv/arxiv/pdf/{yymm}/{pid}"


def probe_gcs_pdf(client: httpx.Client, paper_id: str) -> ProbeResult:
    """HEAD-equivalent: query the JSON metadata endpoint (no egress cost)."""
    base = gcs_pdf_object_path(paper_id)
    t0 = time.perf_counter()
    last_err: str | None = None
    last_status: int | None = None
    bytes_in = 0
    for v in range(1, 10):
        obj_name = quote_plus(f"{base}v{v}.pdf")
        url = f"{GCS_API}/{obj_name}"
        try:
            r = client.get(url, timeout=10.0)
            bytes_in += len(r.content)
            last_status = r.status_code
            if r.status_code == 200:
                latency = (time.perf_counter() - t0) * 1000
                return ProbeResult(
                    label=f"gcs:{paper_id}v{v}",
                    upstream="gcs.arxiv-dataset",
                    ok=True,
                    status=200,
                    latency_ms=latency,
                    bytes_in=bytes_in,
                    extracted_ids=[paper_id],
                )
        except Exception as e:
            last_err = repr(e)
            break
    return ProbeResult(
        label=f"gcs:{paper_id}",
        upstream="gcs.arxiv-dataset",
        ok=False,
        status=last_status,
        latency_ms=(time.perf_counter() - t0) * 1000,
        bytes_in=bytes_in,
        error=last_err or f"not_found_v1..v9 last={last_status}",
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", default="gpd-desktop")
    ap.add_argument("--days", type=int, default=14)
    ap.add_argument("--search-samples", type=int, default=15)
    ap.add_argument("--abstract-samples", type=int, default=15)
    ap.add_argument("--download-samples", type=int, default=10)
    ap.add_argument("--out", default="reports/arxiv-probe.json")
    args = ap.parse_args()

    print("[probe] pulling search args from BQ ...", file=sys.stderr)
    search_args = bq_pull(args.project, args.days, "search_papers", args.search_samples * 3)
    print("[probe] pulling abstract args from BQ ...", file=sys.stderr)
    abstract_args = bq_pull(args.project, args.days, "get_abstract", args.abstract_samples * 3)
    print("[probe] pulling download args from BQ ...", file=sys.stderr)
    download_args = bq_pull(args.project, args.days, "download_paper", args.download_samples * 3)

    queries = [a.get("query") for a in search_args if isinstance(a.get("query"), str)][
        : args.search_samples
    ]
    abstract_ids = [a.get("paper_id") for a in abstract_args if isinstance(a.get("paper_id"), str)][
        : args.abstract_samples
    ]
    download_ids = [a.get("paper_id") for a in download_args if isinstance(a.get("paper_id"), str)][
        : args.download_samples
    ]

    reports: dict[str, EndpointReport] = {
        "openalex.search": EndpointReport("openalex.search"),
        "openalex.abstract": EndpointReport("openalex.abstract"),
        "ar5iv.html": EndpointReport("ar5iv.html"),
        "gcs.arxiv-dataset": EndpointReport("gcs.arxiv-dataset"),
    }
    raw: list[ProbeResult] = []

    headers = {"User-Agent": USER_AGENT, "Accept": "application/json,text/html;q=0.9"}
    with httpx.Client(headers=headers) as client:
        for q in queries:
            r = probe_openalex_search(client, q)
            reports["openalex.search"].add(r)
            raw.append(r)
        for pid in abstract_ids:
            r = probe_openalex_abstract(client, pid)
            reports["openalex.abstract"].add(r)
            raw.append(r)
        for pid in download_ids:
            r1 = probe_ar5iv(client, pid)
            reports["ar5iv.html"].add(r1)
            raw.append(r1)
            r2 = probe_gcs_pdf(client, pid)
            reports["gcs.arxiv-dataset"].add(r2)
            raw.append(r2)

    summary = {
        "config": vars(args),
        "endpoints": {k: v.summary() for k, v in reports.items()},
        "raw": [asdict(r) for r in raw],
    }
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(summary, indent=2))

    # human readable to stderr; machine readable to file
    for k, v in summary["endpoints"].items():
        # ``p50_ms`` / ``p95_ms`` are ``None`` when there are no samples or
        # too few for a percentile. Coerce defensively so the human summary
        # never aborts the probe before the gate block below can run.
        print(
            f"[probe] {k:24} success={v['success_rate']:.0%} "
            f"p50={(v['p50_ms'] or 0):.0f}ms p95={(v['p95_ms'] or 0):.0f}ms "
            f"id_extract={v['id_extract_rate']:.0%} mean_bytes={v['mean_bytes']:.0f}",
            file=sys.stderr,
        )
    print(f"[probe] wrote {out_path}", file=sys.stderr)

    gate_fail = False
    for k, v in summary["endpoints"].items():
        # Missing evidence must fail the gate — silently skipping zero-sample
        # endpoints would let the script exit 0 even when an endpoint never
        # actually ran.
        if v["samples"] == 0:
            print(f"[probe] GATE FAIL: {k} has no samples", file=sys.stderr)
            gate_fail = True
            continue
        # The pass criteria in the module docstring carve out a 90% floor for
        # GCS object-existence (HEAD on gs://arxiv-dataset/...). Every other
        # endpoint stays at the generic 95% gate.
        min_success_rate = 0.90 if k == "gcs.arxiv-dataset" else 0.95
        if v["success_rate"] < min_success_rate:
            print(
                f"[probe] GATE FAIL: {k} success {v['success_rate']:.0%} < {min_success_rate:.0%}",
                file=sys.stderr,
            )
            gate_fail = True
        if (v["p95_ms"] or 0) > 5000:
            print(
                f"[probe] GATE FAIL: {k} p95 {(v['p95_ms'] or 0):.0f}ms > 5000ms",
                file=sys.stderr,
            )
            gate_fail = True
        # ``openalex.search`` exists specifically to prove the translator can
        # recover arxiv IDs from OpenAlex payloads. If id_extract_rate drops
        # below 95%, downstream search results lose their arxiv-id contract.
        if k == "openalex.search" and v["id_extract_rate"] < 0.95:
            print(
                f"[probe] GATE FAIL: {k} id_extract {v['id_extract_rate']:.0%} < 95%",
                file=sys.stderr,
            )
            gate_fail = True
    return 1 if gate_fail else 0


if __name__ == "__main__":
    sys.exit(main())
