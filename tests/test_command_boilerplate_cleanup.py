"""Assert command prompts stay free of cross-runtime boilerplate."""

from __future__ import annotations

import re
from pathlib import Path

from gpd.adapters.install_utils import parse_at_include_path
from tests.assertion_taxonomy_support import assert_prompt_contracts, semantic_concept
from tests.markdown_test_support import has_line_with_terms

REPO_ROOT = Path(__file__).resolve().parents[1]
COMMANDS_DIR = REPO_ROOT / "src" / "gpd" / "commands"
AGENTS_DIR = REPO_ROOT / "src" / "gpd" / "agents"
SPECS_DIR = REPO_ROOT / "src" / "gpd" / "specs"
WORKFLOWS_DIR = SPECS_DIR / "workflows"
PUBLICATION_REFERENCES_DIR = SPECS_DIR / "references" / "publication"
RESEARCH_REFERENCES_DIR = SPECS_DIR / "references" / "research"
TEMPLATES_DIR = SPECS_DIR / "templates"

LEGACY_COMMENT_FRAGMENTS = (
    "Tool names and @ includes are platform-specific.",
    "Allowed-tools are runtime-specific.",
    "Tool names and @ includes are runtime-specific.",
    "installer rewrites paths for your runtime.",
)

MODEL_FACING_DIRS = (COMMANDS_DIR, AGENTS_DIR)
FRESH_CONTEXT_MODEL_DIRS = (COMMANDS_DIR, AGENTS_DIR, SPECS_DIR)

UNRESOLVED_PLACEHOLDER_RE = re.compile(r"(?:^|\n)\s*(?:<!--\s*)?(?:TODO|FIXME|PLACEHOLDER)(?:\b|:)")

LEGACY_BACKCOMPAT_WORDING = (
    "backcompat",
    "back-compat",
    "backward compatibility",
    "backwards compatibility",
)
STALE_MODEL_FACING_WORDING = (
    "runtime-installer",
    "test alignment",
    "regression guardrail",
)


def _eager_include_paths(text: str) -> set[str]:
    return {include_path for line in text.splitlines() if (include_path := parse_at_include_path(line)) is not None}


WORKFLOW_DELEGATING_COMMANDS = (
    "compare-experiment.md",
    "dimensional-analysis.md",
    "export.md",
    "new-milestone.md",
    "undo.md",
    "explain.md",
    "parameter-sweep.md",
    "error-propagation.md",
)


def _success_criteria_items(text: str) -> list[str]:
    match = re.search(r"<success_criteria>(.*?)</success_criteria>", text, re.DOTALL)
    if not match:
        return []

    items: list[str] = []
    for line in match.group(1).splitlines():
        stripped = line.strip()
        if stripped.startswith("- [ ] "):
            items.append(stripped.removeprefix("- [ ] ").strip())
        elif stripped.startswith("- "):
            items.append(stripped.removeprefix("- ").strip())
    return items


def _assert_prompt_concept(
    text: str,
    label: str,
    *,
    required: tuple[str, ...] = (),
    forbidden: tuple[str, ...] = (),
) -> None:
    assert_prompt_contracts(
        text,
        *semantic_concept(
            label,
            required=required or None,
            forbidden=forbidden or None,
        ),
    )


def _assert_line_concept(text: str, label: str, *terms: str) -> None:
    assert has_line_with_terms(text, *terms, casefold=True), f"missing {label}: {terms}"


def test_command_sources_do_not_keep_runtime_boilerplate_html_comments() -> None:
    for path in sorted(COMMANDS_DIR.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        for fragment in LEGACY_COMMENT_FRAGMENTS:
            assert fragment not in text, f"{path.relative_to(REPO_ROOT)} still contains: {fragment}"


def test_command_sources_use_runtime_neutral_fresh_context_wording() -> None:
    for directory in FRESH_CONTEXT_MODEL_DIRS:
        for path in sorted(directory.rglob("*.md")):
            text = path.read_text(encoding="utf-8")
            assert "/clear" not in text, f"{path.relative_to(REPO_ROOT)} still hardcodes runtime reset wording"


def test_shared_prompt_surfaces_use_runtime_installed_command_wording_not_raw_skill_calls() -> None:
    for directory in FRESH_CONTEXT_MODEL_DIRS:
        for path in sorted(directory.rglob("*.md")):
            text = path.read_text(encoding="utf-8")
            assert "Skill(" not in text, f"{path.relative_to(REPO_ROOT)} still uses raw Skill(...) syntax"


def test_model_facing_prompts_do_not_ship_unresolved_placeholders() -> None:
    for directory in MODEL_FACING_DIRS:
        for path in sorted(directory.glob("*.md")):
            text = path.read_text(encoding="utf-8")
            assert not UNRESOLVED_PLACEHOLDER_RE.search(text), (
                f"{path.relative_to(REPO_ROOT)} still contains an unresolved placeholder marker"
            )


def test_model_facing_prompts_do_not_use_informal_gap_markers() -> None:
    for directory in MODEL_FACING_DIRS:
        for path in sorted(directory.glob("*.md")):
            text = path.read_text(encoding="utf-8")
            assert "???" not in text, f"{path.relative_to(REPO_ROOT)} still contains an informal ??? marker"


def test_model_facing_prompts_do_not_use_legacy_backcompat_wording() -> None:
    for directory in MODEL_FACING_DIRS:
        for path in sorted(directory.glob("*.md")):
            text = path.read_text(encoding="utf-8").lower()
            for phrase in LEGACY_BACKCOMPAT_WORDING:
                assert phrase not in text, f"{path.relative_to(REPO_ROOT)} still contains {phrase}"


def test_model_facing_prompts_do_not_explain_test_or_installer_scaffolding() -> None:
    for directory in MODEL_FACING_DIRS:
        for path in sorted(directory.glob("*.md")):
            text = path.read_text(encoding="utf-8").lower()
            for phrase in STALE_MODEL_FACING_WORDING:
                assert phrase not in text, f"{path.relative_to(REPO_ROOT)} still contains {phrase}"


def test_researcher_shared_does_not_label_arxiv_as_peer_reviewed() -> None:
    text = (RESEARCH_REFERENCES_DIR / "researcher-shared.md").read_text(encoding="utf-8")
    arxiv_search_rows = [line for line in text.splitlines() if "web_search (arXiv)" in line]

    assert len(arxiv_search_rows) == 1
    _assert_line_concept(
        arxiv_search_rows[0],
        "arxiv discovery confidence without peer-review claim",
        "HIGH",
        "discovery",
        "publication status",
    )
    assert all("peer-reviewed" not in line.lower() for line in arxiv_search_rows)


def test_learned_pattern_template_uses_install_dir_reference_not_legacy_alias() -> None:
    text = (TEMPLATES_DIR / "learned-pattern.md").read_text(encoding="utf-8")

    legacy_alias = "@" + "get-physics-done"
    assert legacy_alias not in text
    assert "{GPD_INSTALL_DIR}/references/verification/core/verification-core.md" in text


def test_workflow_delegating_command_wrappers_do_not_copy_workflow_checklists() -> None:
    for filename in WORKFLOW_DELEGATING_COMMANDS:
        command_text = (COMMANDS_DIR / filename).read_text(encoding="utf-8")
        workflow_text = (WORKFLOWS_DIR / filename).read_text(encoding="utf-8")

        command_items = set(_success_criteria_items(command_text))
        workflow_items = set(_success_criteria_items(workflow_text))

        assert command_items, f"{filename} must keep wrapper-level success criteria"
        assert not command_items & workflow_items, (
            f"{filename} wrapper duplicates workflow-owned checklist items: {sorted(command_items & workflow_items)}"
        )
        _assert_line_concept(command_text, f"{filename} workflow authority delegation", "workflow", "authority")


def test_command_child_invocations_do_not_use_raw_skill_or_shell_shaped_args() -> None:
    shell_shaped_child_invocation = re.compile(
        r"invok(?:e|es|ing)\s+`gpd:[^`]+`[^\n.]*--[a-z][a-z0-9-]*",
        re.IGNORECASE,
    )

    for path in sorted(COMMANDS_DIR.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        assert "via Skill" not in text, f"{path.relative_to(REPO_ROOT)} still describes a raw Skill child call"
        assert not shell_shaped_child_invocation.search(text), (
            f"{path.relative_to(REPO_ROOT)} describes a child command with shell-shaped flags"
        )

    undo_text = (COMMANDS_DIR / "undo.md").read_text(encoding="utf-8")
    assert "structured runtime arguments" in undo_text
    assert "--reverted-commit" not in undo_text
    assert "--trigger" not in undo_text
    assert "--phase" not in undo_text


def test_parameter_sweep_command_wrapper_delegates_mechanics_to_workflow() -> None:
    text = (COMMANDS_DIR / "parameter-sweep.md").read_text(encoding="utf-8")

    assert "gpd --raw validate command-context parameter-sweep" in text
    assert "@{GPD_INSTALL_DIR}/workflows/parameter-sweep.md" in text
    _assert_line_concept(text, "parameter-sweep workflow ownership", "workflow", "sweep design")
    assert "GPD/sweeps/" in text
    assert "GPD/phases/XX-sweep" in text
    assert "artifacts/" in text
    assert "np.linspace" not in text
    assert "adaptive_sweep" not in text
    assert "Grid Type" not in text


def test_thin_command_wrappers_do_not_duplicate_workflow_owned_mechanics() -> None:
    explain = (COMMANDS_DIR / "explain.md").read_text(encoding="utf-8")
    assert (
        explain.count(
            "GPD-authored explanation artifacts stay under `GPD/explanations/` rooted at the current workspace."
        )
        == 1
    )
    assert "Keep any GPD-authored explanation artifacts under `GPD/explanations/`" not in explain

    workflow_owned_fragments = {
        "explain.md": (
            "Check for prior explanation artifacts:",
            "Show the explanation summary",
        ),
        "limiting-cases.md": (
            "Interpretation:",
            "Known Limiting Cases",
            "Every new result must reduce to known results",
            "For comprehensive verification",
        ),
        "parameter-sweep.md": (
            "Accepted targets:",
            "one explicit current-workspace computation anchor",
            "Preserve its workspace-locked bootstrap",
            "Phase-backed outputs and standalone/current-workspace",
        ),
        "reapply-patches.md": (
            "All backed-up patches processed",
            "User modifications merged into new version",
            "Physics-specific content (conventions, signs, units)",
            "Conflicts resolved with user input",
        ),
    }

    for filename, stale_fragments in workflow_owned_fragments.items():
        text = (COMMANDS_DIR / filename).read_text(encoding="utf-8")
        assert f"@{{GPD_INSTALL_DIR}}/workflows/{filename}" in text
        _assert_prompt_concept(
            text,
            f"{filename} delegates implementation mechanics",
            required=("workflow-owned implementation", "workflow owns"),
        )
        for fragment in stale_fragments:
            assert fragment not in text, f"{filename} still duplicates workflow mechanics: {fragment}"


def test_digest_knowledge_command_wrapper_delegates_mechanics_to_workflow() -> None:
    text = (COMMANDS_DIR / "digest-knowledge.md").read_text(encoding="utf-8")

    assert "gpd --raw validate command-context digest-knowledge" in text
    assert "@{GPD_INSTALL_DIR}/workflows/digest-knowledge.md" in text
    _assert_line_concept(text, "digest-knowledge workflow ownership", "workflow", "classification")
    assert "current workspace's `GPD/knowledge/` tree" in text
    _assert_line_concept(text, "digest-knowledge external source boundary", "external source material", "anywhere")
    assert "gpd validate artifact-text <path> --output <txt-path>" in text
    assert "INIT=$(gpd --raw init progress" not in text
    assert "ls GPD/knowledge/*.md" not in text


def test_error_propagation_command_wrapper_delegates_mechanics_to_workflow() -> None:
    text = (COMMANDS_DIR / "error-propagation.md").read_text(encoding="utf-8")

    assert "@{GPD_INSTALL_DIR}/workflows/error-propagation.md" in text
    _assert_line_concept(
        text,
        "error-propagation workflow ownership",
        "workflow",
        "project bootstrap",
        "context validation",
        "dependency tracing",
    )
    assert "S_i = (x_i / f)" not in text
    assert "np.random.normal" not in text
    assert "Error Budget Table" not in text


def test_error_patterns_command_wrapper_delegates_category_vocabulary_to_workflow() -> None:
    text = (COMMANDS_DIR / "error-patterns.md").read_text(encoding="utf-8")

    assert "@{GPD_INSTALL_DIR}/workflows/error-patterns.md" in text
    _assert_line_concept(text, "error-patterns workflow vocabulary ownership", "workflow", "category validation")
    assert "Categories:" not in text
    for stale_category in ("`sign`", "`factor`", "`convention`", "`numerical`", "`approximation`"):
        assert stale_category not in text
    for removed_category in ("`boundary`", "`gauge`", "`combinatorial`"):
        assert removed_category not in text


def test_debug_command_wrapper_delegates_mechanics_to_workflow() -> None:
    text = (COMMANDS_DIR / "debug.md").read_text(encoding="utf-8")

    assert "@{GPD_INSTALL_DIR}/workflows/debug.md" in text
    _assert_line_concept(
        text,
        "debug workflow ownership",
        "workflow",
        "workspace bootstrap",
        "active-session",
        "symptom",
    )
    assert 'subagent_type="gpd-debugger"' in text
    assert "gpd_return.status" in text
    assert not has_line_with_terms(text, "ask_user", "each", casefold=True)
    assert "Spawn Fresh Continuation agent" not in text
    assert "Check Active Sessions" not in text


def test_discuss_phase_command_wrapper_late_reads_context_template() -> None:
    text = (COMMANDS_DIR / "discuss-phase.md").read_text(encoding="utf-8")
    eager_includes = _eager_include_paths(text)

    assert "@{GPD_INSTALL_DIR}/workflows/discuss-phase.md" in text
    assert "{GPD_INSTALL_DIR}/templates/context.md" in text
    assert "{GPD_INSTALL_DIR}/workflows/discuss-phase.md" in eager_includes
    assert "{GPD_INSTALL_DIR}/templates/context.md" not in eager_includes
    assert "only when writing or updating `{phase}-CONTEXT.md`" in text


def test_complete_milestone_command_wrapper_delegates_mechanics_to_workflow() -> None:
    text = (COMMANDS_DIR / "complete-milestone.md").read_text(encoding="utf-8")
    eager_includes = _eager_include_paths(text)

    assert "@{GPD_INSTALL_DIR}/workflows/complete-milestone.md" in text
    assert "{GPD_INSTALL_DIR}/templates/milestone.md" in text
    assert "{GPD_INSTALL_DIR}/templates/milestone-archive.md" in text
    assert "{GPD_INSTALL_DIR}/workflows/complete-milestone.md" in eager_includes
    assert "{GPD_INSTALL_DIR}/templates/milestone.md" not in eager_includes
    assert "{GPD_INSTALL_DIR}/templates/milestone-archive.md" not in eager_includes
    _assert_line_concept(text, "complete-milestone workflow ownership", "workflow", "audit/readiness")
    _assert_line_concept(
        text,
        "complete-milestone wrapper responsibility",
        "wrapper",
        "public command surface",
        "version argument",
    )
    assert not has_line_with_terms(text, "audit status", "gaps_found", casefold=True)
    assert "Stage: MILESTONES.md" not in text
    assert "Ask about pushing tag" not in text


def test_autonomous_surfaces_use_installed_command_wording_not_raw_skill_calls() -> None:
    for path in (COMMANDS_DIR / "autonomous.md", WORKFLOWS_DIR / "autonomous.md"):
        text = path.read_text(encoding="utf-8")
        assert "Skill(" not in text, path.relative_to(REPO_ROOT)

    workflow = (WORKFLOWS_DIR / "autonomous.md").read_text(encoding="utf-8")
    for command_name in (
        "gpd:write-paper",
        "gpd:plan-phase",
        "gpd:execute-phase",
        "gpd:verify-work",
        "gpd:audit-milestone",
        "gpd:complete-milestone",
    ):
        assert (
            f"runtime-installed `{command_name}` command" in workflow
            or f"runtime-installed `{command_name}` child command" in workflow
        )


def test_review_knowledge_command_delegates_schema_surfaces_to_workflow() -> None:
    text = (COMMANDS_DIR / "review-knowledge.md").read_text(encoding="utf-8")
    workflow = (WORKFLOWS_DIR / "review-knowledge.md").read_text(encoding="utf-8")

    assert "@{GPD_INSTALL_DIR}/workflows/review-knowledge.md" in text
    _assert_line_concept(text, "review-knowledge workflow ownership", "workflow", "schema loading")
    assert "@{GPD_INSTALL_DIR}/templates/knowledge-schema.md" not in text
    assert "@{GPD_INSTALL_DIR}/templates/knowledge.md" not in text
    assert "@{GPD_INSTALL_DIR}/references/shared/canonical-schema-discipline.md" not in text
    assert "{GPD_INSTALL_DIR}/templates/knowledge-schema.md" in workflow
    assert "{GPD_INSTALL_DIR}/templates/knowledge.md" in workflow
    assert "{GPD_INSTALL_DIR}/references/shared/canonical-schema-discipline.md" in workflow


def test_legacy_publication_contract_stubs_are_removed_in_favor_of_canonical_files() -> None:
    canonical_files = (
        "publication-review-round-artifacts.md",
        "publication-response-artifacts.md",
    )
    removed_files = (
        "review-round-artifact-contract.md",
        "response-artifact-contract.md",
    )

    for filename in canonical_files:
        assert (PUBLICATION_REFERENCES_DIR / filename).is_file()

    for filename in removed_files:
        assert not (PUBLICATION_REFERENCES_DIR / filename).exists()
