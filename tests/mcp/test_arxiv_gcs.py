"""Unit tests for the GCS arxiv path parser and PDF fetch helpers."""

from __future__ import annotations

import pytest

from gpd.mcp.servers import _arxiv_gcs


def test_parse_new_format_no_version() -> None:
    assert _arxiv_gcs.parse_paper_id("2401.12345") == ("arxiv", "2401", "2401.12345")


def test_parse_new_format_with_version() -> None:
    assert _arxiv_gcs.parse_paper_id("2401.12345v3") == ("arxiv", "2401", "2401.12345")


def test_parse_new_format_four_digit_number() -> None:
    # Pre-2015 arxiv IDs sometimes have 4-digit suffixes.
    assert _arxiv_gcs.parse_paper_id("0904.1556") == ("arxiv", "0904", "0904.1556")


def test_parse_old_format() -> None:
    # Numeric-tail-only path. `hep-th9901001` etc 404 on the bucket.
    assert _arxiv_gcs.parse_paper_id("hep-th/9901001") == ("hep-th", "9901", "9901001")


def test_parse_old_format_with_version() -> None:
    assert _arxiv_gcs.parse_paper_id("hep-th/9901001v2") == ("hep-th", "9901", "9901001")


def test_parse_strips_trailing_pdf() -> None:
    assert _arxiv_gcs.parse_paper_id("2401.12345.pdf") == ("arxiv", "2401", "2401.12345")


def test_parse_lowercases_category() -> None:
    # arxiv old-style category prefixes are lowercase; some tools pass mixed case.
    assert _arxiv_gcs.parse_paper_id("HEP-TH/9901001") == ("hep-th", "9901", "9901001")


def test_parse_strips_whitespace() -> None:
    assert _arxiv_gcs.parse_paper_id("  2401.12345  ") == ("arxiv", "2401", "2401.12345")


def test_parse_rejects_bogus_input() -> None:
    with pytest.raises(ValueError):
        _arxiv_gcs.parse_paper_id("not-an-arxiv-id")


def test_parse_rejects_non_string() -> None:
    with pytest.raises(ValueError):
        _arxiv_gcs.parse_paper_id(12345)  # type: ignore[arg-type]


def test_parse_rejects_empty() -> None:
    with pytest.raises(ValueError):
        _arxiv_gcs.parse_paper_id("")


def test_pdf_bytes_to_markdown_rejects_empty_output(tmp_path, monkeypatch) -> None:
    pymupdf4llm = pytest.importorskip("pymupdf4llm")
    # Force the converter to return an empty string so we exercise the
    # empty-output guard specifically (rather than generic parse failure).
    monkeypatch.setattr(pymupdf4llm, "to_markdown", lambda *a, **kw: "")
    # Minimal valid PDF header so PyMuPDF can open the temp file before
    # the converter (now mocked) returns empty output.
    minimal_pdf = b"%PDF-1.4\n%%EOF\n"
    with pytest.raises(RuntimeError, match="empty"):
        _arxiv_gcs.pdf_bytes_to_markdown(minimal_pdf, "test/0000001", tmp_path)
