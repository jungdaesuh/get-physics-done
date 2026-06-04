"""Tests for todo frontmatter parsing helpers."""

from __future__ import annotations

from gpd.core import context as context_module
from gpd.core.context_todos import _extract_frontmatter_field, _read_todo_frontmatter


def test_context_reexports_todo_frontmatter_helpers() -> None:
    assert context_module._extract_frontmatter_field is _extract_frontmatter_field
    assert context_module._read_todo_frontmatter is _read_todo_frontmatter


def test_todo_frontmatter_parsing_handles_blank_lines_before_frontmatter() -> None:
    content = '\n\n---\ntitle: Todo task\ncreated: "2026-01-01"\n---\nBody.\n'

    meta = _read_todo_frontmatter(content)

    assert meta == {"title": "Todo task", "created": "2026-01-01"}
    assert _extract_frontmatter_field(content, "title") == "Todo task"
    assert _extract_frontmatter_field(content, "created") == "2026-01-01"


class TestExtractFrontmatterField:
    """Assert \\s* in the field regex does not match newlines."""

    def test_empty_value_does_not_bleed_into_next_line(self) -> None:
        """When a field has an empty value, the regex must not capture the next line."""
        content = "title:\narea: numerical\ncreated: 2026-03-01"

        assert _extract_frontmatter_field(content, "title") is None

    def test_field_with_value_still_works(self) -> None:
        content = "title: Check convergence\narea: numerical"

        assert _extract_frontmatter_field(content, "title") == "Check convergence"
        assert _extract_frontmatter_field(content, "area") == "numerical"

    def test_field_with_leading_spaces(self) -> None:
        content = "title:   spaced value  \narea: numerical"

        assert _extract_frontmatter_field(content, "title") == "spaced value"

    def test_field_with_quoted_value(self) -> None:
        content = 'title: "Quoted Title"\narea: theory'

        assert _extract_frontmatter_field(content, "title") == "Quoted Title"

    def test_body_lines_do_not_override_leading_metadata_block(self) -> None:
        content = 'title: "Check convergence"\n\narea: numerical\ncreated: 2026-03-01\n'

        assert _extract_frontmatter_field(content, "title") == "Check convergence"
        assert _extract_frontmatter_field(content, "area") is None
        assert _extract_frontmatter_field(content, "created") is None
