"""Focused prompt/command contract cleanup invariants."""

from __future__ import annotations

import re
from pathlib import Path

from gpd.adapters.install_utils import parse_at_include_path
from gpd.core.frontmatter import validate_frontmatter
from scripts.render_help_surface import help_surface_markers
from tests.core.test_spawn_contracts import _find_single_task
from tests.lifecycle_contract_test_support import (
    assert_forbidden_contract as _assert_forbidden,
)
from tests.lifecycle_contract_test_support import (
    assert_machine_contract as _assert_machine,
)
from tests.lifecycle_contract_test_support import (
    assert_semantic_contract as _assert_semantic,
)
from tests.workflow_authority_support import workflow_authority_text

REPO_ROOT = Path(__file__).resolve().parents[2]
COMMANDS_DIR = REPO_ROOT / "src/gpd/commands"
AGENTS_DIR = REPO_ROOT / "src/gpd/agents"
WORKFLOWS_DIR = REPO_ROOT / "src/gpd/specs/workflows"
REFERENCES_DIR = REPO_ROOT / "src/gpd/specs/references"
TEMPLATES_DIR = REPO_ROOT / "src/gpd/specs/templates"
PUBLIC_SURFACE_CONTRACT = REPO_ROOT / "src/gpd/core/public_surface_contract.json"
README = REPO_ROOT / "README.md"
LINUX_DOC = REPO_ROOT / "docs/linux.md"


def _read(path: Path) -> str:
    if path.parent == WORKFLOWS_DIR and path.stem in {
        "execute-phase",
        "peer-review",
        "respond-to-referees",
        "write-paper",
    }:
        return workflow_authority_text(WORKFLOWS_DIR, path.stem)
    return path.read_text(encoding="utf-8")


def _between(text: str, start_marker: str, end_marker: str) -> str:
    start = text.index(start_marker) + len(start_marker)
    end = text.index(end_marker, start)
    return text[start:end]


def _first_markdown_fence(text: str) -> str:
    match = re.search(r"```markdown\n(.*?)\n```", text, re.S)
    assert match is not None
    return match.group(1)


def _single_line_starting(text: str, prefix: str) -> str:
    matches = [line for line in text.splitlines() if line.startswith(prefix)]
    assert len(matches) == 1
    return matches[0]


def test_discover_managed_outputs_have_write_capability_and_documented_route() -> None:
    command_text = _read(COMMANDS_DIR / "discover.md")
    workflow_text = _read(WORKFLOWS_DIR / "discover.md")

    _assert_machine(
        command_text,
        "discover managed output policy",
        "output_policy:",
        "output_mode: managed",
        "managed_root_kind: gpd_managed_durable",
        "default_output_subtree: GPD/analysis",
        "  - file_write",
    )
    _assert_semantic(
        command_text,
        "discover documented write route command",
        "documented write route",
        "workflow-owned Level 2-3 discovery artifact path",
    )
    _assert_semantic(
        workflow_text,
        "discover documented write route workflow",
        "This workflow is the documented write route for `gpd:discover` managed outputs.",
    )


def test_owned_project_aware_commands_use_validated_context_instead_of_raw_gpd_includes() -> None:
    command_files = (
        "discover.md",
        "sensitivity-analysis.md",
        "derive-equation.md",
        "review-knowledge.md",
    )

    for command_file in command_files:
        text = _read(COMMANDS_DIR / command_file)
        _assert_forbidden(text, f"{command_file} no raw GPD include", "@GPD/")
        _assert_machine(text, f"{command_file} validated command context", "Validated command-context")


def test_help_reference_stays_static_and_delegates_next_action_routing() -> None:
    help_workflow = _read(WORKFLOWS_DIR / "help.md")
    success_criteria = _between(help_workflow, "<success_criteria>", "</success_criteria>")

    _assert_forbidden(
        success_criteria,
        "help reference no dynamic next action routing",
        "Next action guidance provided based on current project state",
    )
    _assert_semantic(
        success_criteria,
        "help reference static routing delegation",
        "Static reference stays project-independent",
        "current-state routing is delegated to `gpd:start`, `gpd:progress`, or `gpd:suggest-next`",
    )
    _assert_machine(
        help_workflow,
        "help workflow start and suggest-next labels",
        "Run `gpd:start` when you need the safest route for this folder",
        "Run `gpd:suggest-next` when you only need the next action",
    )


def test_help_wrapper_uses_stable_section_markers_for_extracts() -> None:
    help_command = _read(COMMANDS_DIR / "help.md")
    help_workflow = _read(WORKFLOWS_DIR / "help.md")

    marker_pairs = (
        ("quick-start", "## Quick Start"),
        ("command-index", "## Command Index"),
        ("detailed-command-reference", "## Detailed Command Reference"),
        ("default", "## Quick Start"),
    )
    for marker_name, heading in marker_pairs:
        start_marker, end_marker = help_surface_markers(marker_name)
        start_position = help_workflow.index(start_marker)
        end_position = help_workflow.index(end_marker, start_position)
        heading_position = help_workflow.index(heading, start_position)
        _assert_machine(help_workflow, f"help workflow {marker_name} markers", start_marker, end_marker)
        assert start_position < heading_position < end_position
        _assert_machine(help_command, f"help command {marker_name} markers", start_marker, end_marker)

    _assert_semantic(
        help_command,
        "help command marker extraction semantics",
        "Use the workflow-owned stable markers as the extraction boundaries",
        "never print the HTML marker comments themselves",
    )
    bridge_rule = _single_line_starting(help_command, "Bridge command rule:")
    for bridge_token in ("local CLI", "JSON", "renderer-backed"):
        assert bridge_token in bridge_rule
    for detail_token in ("`detail_markdown`", "`canonical_command`", "`allowed_tools`"):
        _assert_machine(help_command, f"help command detail token {detail_token}", detail_token)
    _assert_machine(
        help_command,
        "help command fallback marker source path",
        "`@{GPD_INSTALL_DIR}/workflows/help.md` - Fallback marker source path",
    )
    assert all(parse_at_include_path(line.strip()) is None for line in help_command.splitlines())
    _assert_forbidden(
        help_command,
        "help command stale marker extraction prose",
        "Start at the workflow-owned",
        "Stop before `## Command Index`",
        "Stop before `## Detailed Command Reference`",
    )


def test_set_profile_workflow_does_not_copy_agent_tier_tables() -> None:
    set_profile = _read(WORKFLOWS_DIR / "set-profile.md")

    copied_table = re.compile(r"^\|\s*Agent\s*\|\s*Tier\s*\|", re.MULTILINE)
    assert copied_table.search(set_profile) is None
    _assert_semantic(
        set_profile,
        "set-profile model profile assignment source",
        "Canonical per-agent tier assignments live in `MODEL_PROFILES`",
    )
    _assert_machine(set_profile, "set-profile model profile reference path", "references/orchestration/model-profiles.md")


def test_plan_checker_profile_docs_avoid_stale_dimension_counts() -> None:
    docs = (
        WORKFLOWS_DIR / "set-profile.md",
        REFERENCES_DIR / "research" / "research-modes.md",
        REFERENCES_DIR / "orchestration" / "model-profiles.md",
        REFERENCES_DIR / "orchestration" / "context-pressure-thresholds.md",
    )
    stale_phrases = ("9 core dimensions", "8 dims", "15 dims", "16 plan dimensions")

    for path in docs:
        text = _read(path)
        for phrase in stale_phrases:
            _assert_forbidden(text, f"{path.relative_to(REPO_ROOT)} stale dimension counts", phrase)


def test_peer_review_file_producing_stage_prompts_carry_stage_child_tuples() -> None:
    workflow = _read(WORKFLOWS_DIR / "peer-review.md")
    for agent_name in (
        "gpd-review-reader",
        "gpd-review-literature",
        "gpd-review-math",
        "gpd-check-proof",
        "gpd-review-physics",
        "gpd-review-significance",
    ):
        _assert_machine(workflow, f"peer-review stage role {agent_name}", f"role: {agent_name}")
    _assert_machine(workflow, "peer-review referee spawn", "Spawn `gpd-referee`")
    assert workflow.count("expected_artifacts:") >= 7
    _assert_machine(workflow, "peer-review child tuple fields", "gpd_return.files_written", "stage-recovery-gate.md")


def test_delegation_reference_requires_contract_or_tight_exemption() -> None:
    text = _read(REFERENCES_DIR / "orchestration/agent-delegation.md")

    _assert_semantic(
        text,
        "delegation reference contract exemption boundary",
        "File-producing or state-sensitive spawned prompts must include this block directly",
        "adjacent documented exemption",
        "read-only, produces no artifacts, and returns no shared-state update",
    )


def test_public_local_cli_examples_use_prefixless_command_labels() -> None:
    contract = _read(PUBLIC_SURFACE_CONTRACT)
    help_workflow = _read(WORKFLOWS_DIR / "help.md")

    _assert_machine(contract, "public surface prefixless command context example", "gpd validate command-context <name>")
    _assert_machine(help_workflow, "help workflow prefixless command context example", "gpd validate command-context <name>")
    _assert_forbidden(
        contract,
        "public surface no prefixed command context example",
        "gpd validate command-context gpd:<name>",
    )
    _assert_forbidden(
        help_workflow,
        "help workflow no prefixed command context example",
        "gpd validate command-context gpd:<name>",
    )


def test_start_workflow_routes_choices_by_stable_option_ids() -> None:
    start_workflow = _read(WORKFLOWS_DIR / "start.md")
    offer_step = _between(start_workflow, '<step name="offer_relevant_choices">', "</step>")
    route_step = _between(start_workflow, '<step name="route_choice">', "</step>")

    option_ids = {
        "resume_work",
        "sync_state",
        "progress",
        "map_research",
        "new_project_minimal",
        "new_project_full",
        "tour",
        "reopen_recent",
    }

    _assert_semantic(
        offer_step,
        "start workflow stable option routing offer",
        "Do not route directly on the mutable English label",
    )
    _assert_semantic(route_step, "start workflow stable option routing route", "Normalize the reply to one stable `option_id`")
    for option_id in option_ids:
        _assert_machine(offer_step, f"start workflow offer option {option_id}", f"`{option_id}`")
        _assert_machine(route_step, f"start workflow route option {option_id}", f"option_id `{option_id}`")


def test_readme_generic_command_surface_stays_prefixless_and_uninstall_requires_scope() -> None:
    readme = _read(README)
    key_paths = _between(readme, "## Key GPD Paths", "## System Requirements")
    uninstall = _between(readme, "## Uninstall", "## Inspiration")

    _assert_machine(key_paths, "readme write-paper prefixless label", "`write-paper` supports current-project manuscripts")
    _assert_semantic(
        key_paths,
        "readme prefixless shared examples",
        "The full in-runtime reference is runtime-specific; the shared examples here stay prefixless.",
    )
    _assert_forbidden(key_paths, "readme key paths runtime-specific labels", "gpd:write-paper", "gpd:peer-review", "gpd:pause-work", "Claude Code / Gemini CLI syntax")
    _assert_semantic(
        uninstall,
        "readme uninstall non-interactive scope",
        "For non-interactive uninstall, select both the runtime and scope explicitly",
    )
    _assert_machine(
        uninstall,
        "readme uninstall scoped commands",
        "npx -y get-physics-done --uninstall --codex --local",
        "npx -y get-physics-done --uninstall --claude --global",
    )


def test_linux_docs_warn_distro_node_packages_still_need_node_20() -> None:
    text = _read(LINUX_DOC)
    install_section = _between(text, "## Install or update missing tools", "## Linux-specific notes")

    _assert_semantic(
        install_section,
        "linux docs node 20 requirement",
        "do not continue unless `node --version` reports `v20` or newer",
        "Seeing `nodejs`, `npm`, and `npx` on your PATH is not sufficient",
    )


def test_export_logs_uses_raw_prefixless_command_context_preflight() -> None:
    command = _read(COMMANDS_DIR / "export-logs.md")
    workflow = _read(WORKFLOWS_DIR / "export-logs.md")

    for text in (command, workflow):
        _assert_machine(text, "export-logs raw command context preflight", 'CONTEXT=$(gpd --raw validate command-context export-logs "$ARGUMENTS")')
        _assert_forbidden(text, "export-logs no prefixed command context", "gpd validate command-context gpd:export-logs")
    _assert_machine(workflow, "export-logs prefixless command example", "export-logs --command execute-phase --phase 3 --category workflow")
    _assert_forbidden(workflow, "export-logs no runtime-prefixed command example", "gpd:export-logs --command gpd:execute-phase")


def test_execute_phase_routes_convention_repair_to_validate_conventions_not_inline_notation() -> None:
    workflow = _read(WORKFLOWS_DIR / "execute-phase.md")

    _assert_forbidden(workflow, "execute-phase no inline notation spawn", 'subagent_type="gpd-notation-coordinator"')
    _assert_machine(workflow, "execute-phase notation repair command route", "route through `gpd:validate-conventions`")
    _assert_semantic(
        workflow,
        "execute-phase notation repair boundary",
        "Do not spawn `gpd-notation-coordinator` from `execute-phase`",
        "fresh continuation handoff owns any notation-coordinator work",
    )
    _assert_forbidden(workflow, "execute-phase no stale convention markers", "CONVENTION UPDATE", "CONVENTION CONFLICT")


def test_response_writer_handoff_is_included_once_in_respond_to_referees() -> None:
    workflow = _read(WORKFLOWS_DIR / "respond-to-referees.md")
    staged_workflow = workflow_authority_text(WORKFLOWS_DIR, "respond-to-referees")
    raw_include = "@{GPD_INSTALL_DIR}/references/publication/publication-response-writer-handoff.md"
    literal_reference = "{GPD_INSTALL_DIR}/references/publication/publication-response-writer-handoff.md"

    _assert_forbidden(workflow, "respond-to-referees response writer raw include", raw_include)
    _assert_machine(workflow, "respond-to-referees response writer path reference", literal_reference)
    _assert_machine(
        staged_workflow,
        "respond-to-referees response writer stage handoff path",
        "Apply `{GPD_INSTALL_DIR}/references/publication/publication-response-writer-handoff.md` from this stage exactly.",
    )
    _assert_semantic(
        staged_workflow,
        "respond-to-referees response writer freshness ownership",
        "The loaded publication response-writer\nhandoff owns pair freshness and binding.",
    )


def test_write_paper_response_writer_handoff_stays_deferred_to_stage_authority() -> None:
    workflow = _read(WORKFLOWS_DIR / "write-paper.md")
    raw_include = "@{GPD_INSTALL_DIR}/references/publication/publication-response-writer-handoff.md"
    literal_reference = "{GPD_INSTALL_DIR}/references/publication/publication-response-writer-handoff.md"

    _assert_forbidden(workflow, "write-paper response writer raw include", raw_include)
    _assert_machine(workflow, "write-paper response writer path reference", literal_reference)


def test_write_paper_root_workflow_index_stays_compact_stage_map() -> None:
    workflow = (WORKFLOWS_DIR / "write-paper.md").read_text(encoding="utf-8")

    _assert_machine(
        workflow,
        "write-paper root stage map",
        "`paper_bootstrap` -> `workflows/write-paper/paper-bootstrap.md`",
        "`outline_and_scaffold` -> `workflows/write-paper/outline-scaffold.md`",
        "`figure_and_section_authoring` -> `workflows/write-paper/authoring.md`",
        "`consistency_and_references` -> `workflows/write-paper/consistency-references.md`",
        "`publication_review` -> `workflows/write-paper/publication-review-finalization.md`",
    )
    _assert_forbidden(
        workflow,
        "write-paper root no canonical reference inventory",
        "<canonical_references>",
        "references/publication/publication-bootstrap-preflight.md",
        "{GPD_INSTALL_DIR}/references/publication/publication-bootstrap-preflight.md",
        "{GPD_INSTALL_DIR}/templates/paper/paper-config-schema.md",
    )


def test_inline_install_dir_paths_do_not_use_at_include_form() -> None:
    roots = (COMMANDS_DIR, AGENTS_DIR, WORKFLOWS_DIR, TEMPLATES_DIR)
    offenders: list[str] = []

    for root in roots:
        for path in sorted(root.rglob("*.md")):
            for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
                if "@{GPD_INSTALL_DIR}" not in line:
                    continue
                stripped = line.strip()
                if stripped.startswith("@{GPD_INSTALL_DIR}/"):
                    continue
                if stripped.startswith(("- @{GPD_INSTALL_DIR}/", "* @{GPD_INSTALL_DIR}/")):
                    continue
                if stripped.startswith(("- `@{GPD_INSTALL_DIR}/", "* `@{GPD_INSTALL_DIR}/")):
                    continue
                if re.match(r"\d+[.)]\s+@\{GPD_INSTALL_DIR\}/", stripped):
                    continue
                if re.match(r"\d+[.)]\s+`@\{GPD_INSTALL_DIR\}/", stripped):
                    continue
                if "`@{GPD_INSTALL_DIR}/templates/plan-contract-schema.md`" in stripped:
                    continue
                offenders.append(f"{path.relative_to(REPO_ROOT)}:{line_number}:{line}")

    assert offenders == []


def test_backticked_install_dir_list_paths_are_references_not_includes() -> None:
    roots = (COMMANDS_DIR, WORKFLOWS_DIR, REFERENCES_DIR, TEMPLATES_DIR)
    backticked_list_path = re.compile(r"^\s*(?:[-*+]\s+|\d+[.)]\s+)`@\{GPD_INSTALL_DIR\}/")
    offenders: list[str] = []

    for root in roots:
        for path in sorted(root.rglob("*.md")):
            for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
                stripped = line.strip()
                if not backticked_list_path.match(stripped):
                    continue
                if parse_at_include_path(stripped) is not None:
                    offenders.append(f"{path.relative_to(REPO_ROOT)}:{line_number}:{line}")

    assert offenders == []


def test_public_templates_do_not_expose_internal_verify_phase_wording() -> None:
    roadmap = _read(TEMPLATES_DIR / "roadmap.md")
    state_machine = _read(TEMPLATES_DIR / "state-machine.md")

    _assert_forbidden(roadmap, "roadmap no verify-phase wording", "verify-phase")
    _assert_forbidden(state_machine, "state machine no verify-phase wording", "verify-phase")
    _assert_semantic(
        roadmap,
        "roadmap phase verification wording",
        "Verified by the phase verification workflow after execution",
    )
    _assert_machine(state_machine, "state machine automated verification label", "**Automated verification:**")


def test_research_verification_template_defers_schema_rules_to_canonical_sources() -> None:
    research_verification = _read(TEMPLATES_DIR / "research-verification.md")

    assert research_verification.count("```markdown") == 1
    _assert_machine(
        research_verification,
        "research verification canonical schema references",
        "{GPD_INSTALL_DIR}/templates/verification-report.md",
        "{GPD_INSTALL_DIR}/templates/contract-results-schema.md",
    )
    _assert_semantic(
        research_verification,
        "research verification defers schema rules",
        "do not restate their closed schema here",
    )
    _assert_forbidden(
        research_verification,
        "research verification stale inline schema aliases",
        "suggested_contract_checks: []",
        "only `check`, `reason`, `suggested_subject_kind`, `suggested_subject_id`, and `evidence_path`",
    )

    result = validate_frontmatter(_first_markdown_fence(research_verification), "verification")
    assert result.valid is True
    assert result.errors == []


def test_proof_redteam_repair_handoffs_carry_inline_spawn_contracts() -> None:
    for workflow_name, expected_path in (
        ("derive-equation.md", "${phase_dir}/DERIVATION-{slug}-PROOF-REDTEAM.md"),
        ("verify-phase.md", "${phase_dir}/${phase_number}-PROOF-REDTEAM.md"),
    ):
        task = _find_single_task(WORKFLOWS_DIR / workflow_name, "gpd-check-proof")
        _assert_machine(
            task.text,
            f"{workflow_name} proof redteam spawn contract",
            "<spawn_contract>",
            "write_scope:",
            "expected_artifacts:",
            "shared_state_policy: return_only",
            expected_path,
        )


def test_prompt_markdown_does_not_route_on_stale_prose_return_markers() -> None:
    stale_return_pattern = re.compile(r"\breturn\s+`?(?:##\s*)?[A-Z][A-Z0-9 _-]{4,}`?\b")

    offenders: list[str] = []
    for root in (COMMANDS_DIR, AGENTS_DIR, WORKFLOWS_DIR, TEMPLATES_DIR):
        for path in sorted(root.rglob("*.md")):
            for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
                if not stale_return_pattern.search(line):
                    continue
                if "gpd_return.status" in line or "presentation only" in line:
                    continue
                offenders.append(f"{path.relative_to(REPO_ROOT)}:{line_number}:{line}")

    assert offenders == []
