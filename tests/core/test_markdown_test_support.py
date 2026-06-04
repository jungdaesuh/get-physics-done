"""Tests for semantic markdown assertion helpers."""

from __future__ import annotations

import pytest

from tests.assertion_taxonomy_support import assert_prompt_contracts, machine_exact
from tests.markdown_test_support import (
    MarkdownSection,
    assert_contract_finding,
    assert_contract_relation_finding,
    assert_forbidden_fragments,
    assert_markdown_link,
    assert_no_contract_finding,
    assert_no_contract_relation_finding,
    assert_ordered_fragments,
    assert_required_fragments,
    extract_markdown_section,
    extract_marker_range,
    iter_markdown_sections,
    markdown_fence_bodies,
    markdown_section,
    markdown_sections,
    normalize_text,
    parse_contract_findings,
    parse_frontmatter_mapping,
    parse_markdown_links,
    parse_markdown_table,
    parse_yaml_fences,
    require_mapping,
)


def test_normalize_text_collapses_incidental_whitespace() -> None:
    assert normalize_text(" alpha\n\n  beta\tgamma ") == "alpha beta gamma"


def test_extract_markdown_section_ignores_fenced_headings_and_stops_at_peer_heading() -> None:
    markdown = """# Prompt

```markdown
## Contract
inside fence
```

## Contract

Required claim.

### Nested

Nested detail.

## Next

Outside.
"""

    section = extract_markdown_section(markdown, "## Contract", context="prompt")

    assert "Required claim." in section
    assert "### Nested" in section
    assert "Nested detail." in section
    assert "## Next" not in section
    assert "inside fence" not in section


def test_markdown_sections_expose_metadata_and_heading_inclusion() -> None:
    markdown = """# Prompt

Intro.

## Contract

Required claim.

### Nested

Nested detail.

## Next

Outside.
"""

    sections = iter_markdown_sections(markdown, context="prompt")
    contract = markdown_section(markdown, "Contract", context="prompt")

    assert isinstance(contract, MarkdownSection)
    assert contract in sections
    assert contract.heading == "Contract"
    assert contract.level == 2
    assert contract.atx_heading == "## Contract"
    assert contract.start_line == 5
    assert contract.end_line == 12
    assert contract.text.startswith("## Contract\n")
    assert contract.body.startswith("\nRequired claim.")
    assert extract_markdown_section(markdown, "## Contract", context="prompt") == contract.body.strip("\n")
    assert extract_markdown_section(
        markdown, "Contract", context="prompt", include_heading=True
    ) == contract.text.strip("\n")


def test_markdown_section_infers_atx_level_and_reports_ambiguous_plain_headings() -> None:
    markdown = """# Prompt

## Contract
Level two.

### Contract
Level three.
"""

    with pytest.raises(AssertionError, match=r"multiple markdown sections in prompt: 'Contract' matched lines 3, 6"):
        markdown_section(markdown, "Contract", context="prompt")

    level_two = markdown_section(markdown, "## Contract", context="prompt")
    assert level_two.body.strip().startswith("Level two.")
    assert "### Contract" in level_two.body
    assert markdown_section(markdown, "## Contract", level=3, context="prompt").body.strip() == "Level three."
    assert markdown_sections(markdown, "Contract", level=2, context="prompt")[0].heading == "Contract"


def test_extract_markdown_section_missing_heading_has_contextual_failure() -> None:
    with pytest.raises(AssertionError, match=r"missing markdown section in prompt: '## Missing'"):
        extract_markdown_section("# Prompt\n\nBody.\n", "## Missing", context="prompt")


def test_extract_marker_range_scopes_unique_markers_and_can_include_them() -> None:
    text = "before\nBEGIN\ninside\nEND\nafter\n"

    assert extract_marker_range(text, "BEGIN", "END", context="prompt") == "\ninside\n"
    assert extract_marker_range(text, "BEGIN", "END", context="prompt", include_markers=True) == "BEGIN\ninside\nEND"
    assert extract_marker_range(text, "END", context="prompt") == "\nafter\n"


def test_extract_marker_range_reports_missing_and_duplicate_markers() -> None:
    with pytest.raises(AssertionError, match=r"missing marker range in prompt: start marker 'BEGIN'"):
        extract_marker_range("body", "BEGIN", context="prompt")

    with pytest.raises(AssertionError, match=r"multiple marker ranges in prompt: start marker 'BEGIN' found 2 times"):
        extract_marker_range("BEGIN one BEGIN two", "BEGIN", context="prompt")


def test_parse_markdown_table_normalizes_code_spans_and_reports_malformed_rows() -> None:
    markdown = """Intro.

| Label | Command |
| --- | --- |
| Alpha | `gpd:start` |
| Beta | plain text |
"""

    table = parse_markdown_table(markdown, context="example matrix")

    assert table.headers == ("Label", "Command")
    assert table.rows == (
        {"Label": "Alpha", "Command": "gpd:start"},
        {"Label": "Beta", "Command": "plain text"},
    )

    malformed = "| Label | Command |\n| --- | --- |\n| Alpha |\n"
    with pytest.raises(
        AssertionError,
        match=r"malformed markdown table in example matrix: row has 1 cells, expected 2",
    ):
        parse_markdown_table(malformed, context="example matrix")


def test_parse_markdown_links_and_assert_link_ignore_images() -> None:
    markdown = "Use [Docs](./docs.md), not ![Logo](./logo.png)."

    links = parse_markdown_links(markdown)

    assert links[0].label == "Docs"
    assert links[0].href == "./docs.md"
    assert_markdown_link(markdown, "Docs", "./docs.md", context="README")
    with pytest.raises(AssertionError, match=r"missing markdown link in README"):
        assert_markdown_link(markdown, "Logo", "./logo.png", context="README")


def test_markdown_fence_bodies_filters_by_exact_info() -> None:
    markdown = """```text
new-project
```

```bash
gpd --help
```
"""

    assert markdown_fence_bodies(markdown, info="text") == ("new-project",)
    assert markdown_fence_bodies(markdown) == ("new-project", "gpd --help")


def test_required_and_forbidden_fragments_accept_normalized_prose() -> None:
    section = "The contract\nmust include `plan_contract_ref` and\n`contract_results`."

    assert_required_fragments(
        section,
        (
            "contract must include",
            "`plan_contract_ref`",
            "`contract_results`",
        ),
        context="contract section",
    )
    assert_forbidden_fragments(section, ("must_haves", "verification_inputs"), context="contract section")


def test_required_fragments_failure_lists_missing_fragments() -> None:
    with pytest.raises(AssertionError) as excinfo:
        assert_required_fragments("alpha beta", ("alpha", "gamma"), context="sample")

    message = str(excinfo.value)
    assert_prompt_contracts(
        message,
        machine_exact("required fragment failure context", "missing required fragments in sample"),
    )
    assert "- 'gamma'" in message
    assert "alpha" not in message


def test_forbidden_fragments_failure_lists_present_fragments() -> None:
    with pytest.raises(AssertionError) as excinfo:
        assert_forbidden_fragments("alpha stale_alias beta", ("stale_alias", "other"), context="sample")

    message = str(excinfo.value)
    assert_prompt_contracts(
        message,
        machine_exact("forbidden fragment failure context", "forbidden fragments present in sample"),
    )
    assert "- 'stale_alias'" in message
    assert "other" not in message


def test_parse_contract_findings_extracts_path_prefixed_issues_only() -> None:
    findings = parse_contract_findings(
        (
            "context_intake.must_read_refs must be a list, not str",
            "Invalid contract payload: scope.in_scope must include at least one non-empty string",
            "references.0.notes: Extra inputs are not permitted",
            "claim claim-benchmark references unknown observable obs-missing",
            "no references recorded yet",
        )
    )

    assert [(finding.path, finding.reason) for finding in findings] == [
        ("context_intake.must_read_refs", "must be a list, not str"),
        ("scope.in_scope", "must include at least one non-empty string"),
        ("references.0.notes", "Extra inputs are not permitted"),
    ]


def test_contract_finding_assertions_match_path_and_reason_terms() -> None:
    messages = (
        "context_intake.must_read_refs must be a list, not str",
        "references.0.notes: Extra inputs are not permitted",
    )

    finding = assert_contract_finding(messages, path="context_intake.must_read_refs", contains=("list", "str"))

    assert finding.path == "context_intake.must_read_refs"
    assert_no_contract_finding(messages, path="references.0.notes", contains="boolean")
    with pytest.raises(AssertionError, match="missing project contract finding"):
        assert_contract_finding(messages, path="references.0.notes", contains="boolean", context="project contract")


def test_contract_relation_assertions_match_typed_subjects_and_targets() -> None:
    messages = (
        "claim claim-benchmark references unknown observable obs-missing",
        "reference ref-benchmark is must_surface but missing required_actions",
    )

    assert_contract_relation_finding(
        messages,
        subject_kind="claim",
        subject_id="claim-benchmark",
        relation_terms=("unknown observable",),
        target_id="obs-missing",
    )
    assert_no_contract_relation_finding(
        messages,
        subject_kind="reference",
        subject_id="ref-benchmark",
        relation_terms="missing applies_to",
    )
    with pytest.raises(AssertionError, match="missing contract findings relation finding"):
        assert_contract_relation_finding(
            messages,
            subject_kind="claim",
            subject_id="claim-benchmark",
            relation_terms="unknown deliverable",
            target_id="deliv-missing",
        )


def test_ordered_fragments_accept_normalized_order() -> None:
    assert_ordered_fragments("first\n\nsecond   third", ("first second", "third"), context="sample")


def test_ordered_fragments_failure_distinguishes_out_of_order_fragment() -> None:
    with pytest.raises(AssertionError) as excinfo:
        assert_ordered_fragments("beta alpha", ("alpha", "beta"), context="sample")

    message = str(excinfo.value)
    assert_prompt_contracts(
        message,
        machine_exact("ordered fragment failure context", "fragment appears out of order in sample"),
    )
    assert "'beta' appears before 'alpha'" in message


def test_parse_frontmatter_mapping_returns_strict_frontmatter_mapping() -> None:
    markdown = "---\nname: prompt\nfields:\n  - plan_contract_ref\n---\n\nBody.\n"

    frontmatter = parse_frontmatter_mapping(markdown, context="prompt")

    assert frontmatter == {"name": "prompt", "fields": ["plan_contract_ref"]}


def test_parse_frontmatter_mapping_failure_includes_context() -> None:
    markdown = "---\nname: first\nname: second\n---\n\nBody.\n"

    with pytest.raises(AssertionError) as excinfo:
        parse_frontmatter_mapping(markdown, context="prompt")

    message = str(excinfo.value)
    assert "invalid frontmatter in prompt" in message
    assert "duplicate key" in message


def test_parse_yaml_fences_filters_yaml_fences_and_preserves_line_metadata() -> None:
    markdown = """Intro.

```python
value = 1
```

```yaml
schema_version: 1
fields:
  - plan_contract_ref
```

~~~yml title
status: passed
~~~
"""

    fences = parse_yaml_fences(markdown, context="prompt")

    assert len(fences) == 2
    assert fences[0].info == "yaml"
    assert fences[0].start_line == 7
    assert fences[0].end_line == 11
    assert require_mapping(fences[0].data, context="first YAML fence")["fields"] == ["plan_contract_ref"]
    assert require_mapping(fences[1].data, context="second YAML fence")["status"] == "passed"


def test_parse_yaml_fences_failure_includes_context_and_fence_lines() -> None:
    markdown = """Before.

```yaml
name: first
name: second
```
"""

    with pytest.raises(AssertionError) as excinfo:
        parse_yaml_fences(markdown, context="prompt")

    message = str(excinfo.value)
    assert_prompt_contracts(
        message,
        machine_exact("yaml fence failure context", "invalid YAML fence in prompt at lines 3-6"),
    )
    assert "duplicate key" in message


def test_require_mapping_failure_names_non_mapping_type() -> None:
    with pytest.raises(AssertionError, match="expected mapping in yaml example, got list"):
        require_mapping([], context="yaml example")
