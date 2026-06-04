"""Regression coverage for visible ``gpd_return`` YAML examples."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from gpd.core.return_contract import RETURN_STATUS_ORDER
from gpd.core.return_skeleton import GPD_RETURN_ROLE_PROFILES, build_gpd_return_skeleton
from tests.return_example_support import extract_gpd_return_examples, validate_gpd_return_examples

REPO_ROOT = Path(__file__).resolve().parents[2]
PROMPT_EXAMPLE_ROOTS = (
    REPO_ROOT / "src" / "gpd" / "agents",
    REPO_ROOT / "src" / "gpd" / "specs" / "workflows",
)
REFERENCE_EXAMPLE_PATHS = (
    REPO_ROOT / "src" / "gpd" / "specs" / "references" / "execution" / "executor-completion.md",
    REPO_ROOT / "src" / "gpd" / "specs" / "references" / "orchestration" / "agent-infrastructure.md",
    REPO_ROOT / "src" / "gpd" / "specs" / "references" / "verification" / "plan-checker" / "checker-return-protocol.md",
)
AGENTS_DIR = REPO_ROOT / "src" / "gpd" / "agents"


def _candidate_markdown_files() -> Iterable[Path]:
    for root in PROMPT_EXAMPLE_ROOTS:
        yield from sorted(root.rglob("*.md"))
    yield from REFERENCE_EXAMPLE_PATHS


def test_visible_gpd_return_yaml_examples_match_return_contract() -> None:
    failures: list[str] = []
    checked_examples = 0

    for path in _candidate_markdown_files():
        relative_path = path.relative_to(REPO_ROOT).as_posix()
        examples = extract_gpd_return_examples(path, source_name=relative_path)
        checked_examples += len(examples)
        _, path_failures = validate_gpd_return_examples(examples)
        failures.extend(path_failures)

    assert checked_examples > 0
    assert not failures, "Invalid gpd_return YAML examples:\n" + "\n".join(failures)


def test_agent_return_examples_use_canonical_status_profile_reference() -> None:
    infra = (REFERENCE_EXAMPLE_PATHS[1]).read_text(encoding="utf-8")
    assert "Status vocabulary is owned by `gpd.core.return_contract`" in infra
    assert "`gpd --raw return profiles`" in infra
    assert "`gpd return skeleton --role <role> --status <status>`" in infra
    assert ", ".join(RETURN_STATUS_ORDER) not in infra

    offenders = []
    for path in sorted(AGENTS_DIR.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        if "Use only status names:" in text:
            offenders.append(path.relative_to(REPO_ROOT).as_posix())

    assert offenders == []


def test_prompt_visible_role_extensions_are_profile_visible() -> None:
    expected_extensions = (
        (REPO_ROOT / "src" / "gpd" / "agents" / "gpd-roadmapper.md", "roadmapper", "phases_created"),
        (REPO_ROOT / "src" / "gpd" / "agents" / "gpd-bibliographer.md", "bibliographer", "entries_added"),
        (REPO_ROOT / "src" / "gpd" / "agents" / "gpd-debugger.md", "debugger", "session_file"),
    )

    for path, role, field_name in expected_extensions:
        relative_path = path.relative_to(REPO_ROOT).as_posix()
        examples = extract_gpd_return_examples(path, source_name=relative_path)
        envelopes, failures = validate_gpd_return_examples(examples, require_required_fields=True)

        assert not failures, "Invalid gpd_return YAML examples:\n" + "\n".join(failures)
        assert any(field_name in envelope for envelope in envelopes), f"{relative_path} does not show {field_name}"
        assert field_name in GPD_RETURN_ROLE_PROFILES[role].role_fields_by_status["completed"]
        assert field_name in build_gpd_return_skeleton(role=role, status="completed").role_fields
