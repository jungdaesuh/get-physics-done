from __future__ import annotations

import json
import re
from pathlib import Path

from gpd.adapters.install_utils import parse_at_include_path
from gpd.core.workflow_staging import (
    WRITE_PAPER_MANAGED_INTAKE_ROOT,
    WRITE_PAPER_MANAGED_MANUSCRIPT_ROOT,
    validate_workflow_stage_manifest_payload,
)
from tests.prompt_metrics_support import count_unfenced_heading, expanded_prompt_text
from tests.workflow_authority_support import workflow_authority_text

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS_DIR = REPO_ROOT / "src" / "gpd" / "specs" / "workflows"
REFERENCES_DIR = REPO_ROOT / "src" / "gpd" / "specs" / "references" / "publication"
SOURCE_ROOT = REPO_ROOT / "src" / "gpd"
PATH_PREFIX = "/runtime/"
PUBLICATION_STAGED_WORKFLOWS = ("write-paper", "peer-review", "respond-to-referees", "arxiv-submission")
_SHELL_VAR_REFERENCE_RE = re.compile(r"\$(?:\{([A-Z_][A-Z0-9_]*)(?::-[^}]*)?\}|([A-Z_][A-Z0-9_]*))")
_SHELL_ASSIGNMENT_RE = re.compile(r"(?:^\s*|[;&]\s*|then\s+)(?:export\s+)?([A-Z_][A-Z0-9_]*)=")
_SHELL_READ_ASSIGNMENT_RE = re.compile(r"\bread(?:\s+-[A-Za-z]+)*\s+([A-Z_][A-Z0-9_]*)\b")
_PUBLICATION_STAGE_AMBIENT_VARS = frozenset(
    {
        "ARGUMENTS",
        "BIBLIO_HANDOFF_STARTED_AT",
        "PENDING_COUNT",
        "RESPONSE_HANDOFF_STARTED_AT",
        "REVISION_SECTION_HANDOFF_STARTED_AT",
        "SECTION_WRITER_HANDOFF_STARTED_AT",
    }
)
_REQUIRED_LOCAL_BINDINGS = {
    "peer-review": {
        "REVIEW_TARGET",
        "PUBLICATION_ROOT",
        "REVIEW_ROOT",
    },
    "write-paper": {
        "WRITE_PAPER_ARGUMENTS",
        "PAPER_DIR",
        "MANUSCRIPT_BASENAME",
    },
    "respond-to-referees": {
        "RESPONSE_ARGUMENTS",
        "PAPER_DIR",
        "MANUSCRIPT_BASENAME",
        "RESPONSE_AUTHOR_PATH",
        "RESPONSE_REFEREE_PATH",
    },
    "arxiv-submission": {
        "SUBJECT_SLUG",
        "PACKAGE_ROOT",
        "SUBMISSION_DIR",
        "PACKAGE_TARBALL",
    },
}
RAW_INCLUDE_ALLOWED_DEFERRED_AUTHORITIES = {
    "references/orchestration/runtime-delegation-note.md",
}
WRITE_PAPER_PUBLICATION_REVIEW_REQUIRED_EAGER = frozenset(
    {
        "workflows/write-paper/publication-review-finalization.md",
        "references/publication/publication-review-round-artifacts.md",
    }
)
WRITE_PAPER_PUBLICATION_REVIEW_DEFERRED = frozenset(
    {
        "references/publication/publication-response-writer-handoff.md",
        "references/publication/publication-response-artifacts.md",
        "references/publication/peer-review-panel.md",
        "references/publication/peer-review-reliability.md",
        "references/publication/stage-recovery-gate.md",
        "references/publication/paper-quality-scoring.md",
        "templates/paper/author-response.md",
        "templates/paper/referee-response.md",
        "templates/paper/review-ledger-schema.md",
        "templates/paper/referee-decision-schema.md",
    }
)
WRITE_PAPER_PUBLICATION_REVIEW_CONDITIONALS = {
    "response_pair_authoring": frozenset(
        {
            "references/publication/publication-response-writer-handoff.md",
            "references/publication/publication-response-artifacts.md",
            "references/publication/stage-recovery-gate.md",
            "templates/paper/author-response.md",
            "templates/paper/referee-response.md",
        }
    ),
    "advisory_paper_quality_scoring": frozenset({"references/publication/paper-quality-scoring.md"}),
    "proactive_critique_loop": frozenset({"references/publication/proactive-critique-loop.md"}),
    "review_failure_or_round_state_debug": frozenset({"references/publication/peer-review-reliability.md"}),
}
WRITE_OR_SPAWN_TOOLS = frozenset({"file_edit", "file_write", "task"})
READ_ONLY_BOOTSTRAP_STAGE_IDS = (
    ("write-paper", "paper_bootstrap"),
)
PEER_REVIEW_PANEL_REQUIRED_EAGER = frozenset(
    {
        "workflows/peer-review/panel-stages.md",
        "references/publication/peer-review-panel.md",
    }
)
PEER_REVIEW_PANEL_DEFERRED = frozenset(
    {
        "references/publication/peer-review-panel-playbook.md",
        "references/publication/peer-review-reliability.md",
        "references/publication/publication-final-adjudication-boundary.md",
        "references/publication/publication-response-writer-handoff.md",
        "references/publication/stage-recovery-gate.md",
        "references/verification/core/proof-redteam-workflow-gate.md",
        "references/verification/core/proof-redteam-protocol.md",
        "templates/proof-redteam-schema.md",
    }
)
PEER_REVIEW_PANEL_FINAL_ONLY_AUTHORITIES = frozenset(
    {
        "templates/paper/review-ledger-schema.md",
        "templates/paper/referee-decision-schema.md",
    }
)
PEER_REVIEW_FINAL_ADJUDICATION_REQUIRED_EAGER = frozenset(
    {
        "workflows/peer-review/final-adjudication.md",
        "references/publication/publication-final-adjudication-boundary.md",
        "references/publication/stage-recovery-gate.md",
        "templates/paper/review-ledger-schema.md",
        "templates/paper/referee-decision-schema.md",
    }
)
PEER_REVIEW_FINAL_ADJUDICATION_DEFERRED = frozenset(
    {
        "references/publication/peer-review-panel-playbook.md",
        "references/verification/core/proof-redteam-workflow-gate.md",
        "references/verification/core/proof-redteam-protocol.md",
        "templates/proof-redteam-schema.md",
    }
)


def _load_manifest(workflow_name: str) -> object:
    return validate_workflow_stage_manifest_payload(
        json.loads((WORKFLOWS_DIR / f"{workflow_name}-stage-manifest.json").read_text(encoding="utf-8")),
        expected_workflow_id=workflow_name,
    )


def _conditional_authorities_by_when(stage: object) -> dict[str, frozenset[str]]:
    return {conditional.when: frozenset(conditional.authorities) for conditional in stage.conditional_authorities}


def _expanded_stage_surface(stage: object, *, selected_conditions: tuple[str, ...] = ()) -> str:
    return "\n\n".join(
        expanded_prompt_text(
            SOURCE_ROOT / "specs" / authority,
            src_root=SOURCE_ROOT,
            path_prefix=PATH_PREFIX,
        )
        for authority in stage.eager_authorities(selected_conditions=selected_conditions)
    )


def _canonical_include_relpath(include_path: str) -> str:
    if include_path.startswith("{GPD_INSTALL_DIR}/"):
        return include_path[len("{GPD_INSTALL_DIR}/") :]
    if "get-physics-done/" in include_path:
        return include_path.split("get-physics-done/", 1)[1]
    return include_path


def _raw_projection_include_relpaths(source: str) -> tuple[tuple[int, str], ...]:
    includes: list[tuple[int, str]] = []
    active_fence_marker: str | None = None

    for line_number, line in enumerate(source.splitlines(), start=1):
        stripped = line.strip()
        fence_marker = None
        if stripped.startswith("```"):
            fence_marker = "```"
        elif stripped.startswith("~~~"):
            fence_marker = "~~~"
        if fence_marker is not None:
            if active_fence_marker is None:
                active_fence_marker = fence_marker
            elif active_fence_marker == fence_marker:
                active_fence_marker = None
            continue
        if active_fence_marker is not None:
            continue

        include_path = parse_at_include_path(stripped)
        if include_path is not None:
            includes.append((line_number, _canonical_include_relpath(include_path)))

    return tuple(includes)


def _shell_variables_referenced(source: str) -> set[str]:
    return {braced or bare for braced, bare in _SHELL_VAR_REFERENCE_RE.findall(source) if (braced or bare)}


def _shell_variables_assigned(source: str) -> set[str]:
    assigned: set[str] = set()
    for line in source.splitlines():
        assigned.update(match.group(1) for match in _SHELL_ASSIGNMENT_RE.finditer(line))
        if match := _SHELL_READ_ASSIGNMENT_RE.search(line):
            assigned.add(match.group(1))
    return assigned


def test_publication_stage_shell_variables_are_bound_by_same_stage_payloads() -> None:
    offenders: list[str] = []

    for workflow_name in PUBLICATION_STAGED_WORKFLOWS:
        stage_dir = WORKFLOWS_DIR / workflow_name
        for stage_path in sorted(stage_dir.glob("*.md")):
            source = stage_path.read_text(encoding="utf-8")
            referenced = _shell_variables_referenced(source)
            assigned = _shell_variables_assigned(source)
            for variable in sorted((referenced - assigned) - _PUBLICATION_STAGE_AMBIENT_VARS):
                offenders.append(f"{workflow_name}/{stage_path.name}:${variable}")

            for variable in sorted(_REQUIRED_LOCAL_BINDINGS[workflow_name] & referenced):
                if variable not in assigned:
                    offenders.append(f"{workflow_name}/{stage_path.name}:missing-local-binding:${variable}")

    assert offenders == []


def test_publication_stage_fields_are_read_after_field_access_instruction() -> None:
    offenders: list[str] = []

    for workflow_name in PUBLICATION_STAGED_WORKFLOWS:
        for stage_path in sorted((WORKFLOWS_DIR / workflow_name).glob("*.md")):
            source = stage_path.read_text(encoding="utf-8")
            first_json_read = source.find("gpd json get")
            if first_json_read == -1:
                continue
            first_field_access = source.find("staged_loading.field_access_instruction")
            if first_field_access == -1 or first_field_access > first_json_read:
                offenders.append(f"{workflow_name}/{stage_path.name}")

    assert offenders == []


def test_arxiv_finalize_revalidates_package_from_finalize_payload_before_success() -> None:
    source = (WORKFLOWS_DIR / "arxiv-submission" / "finalize.md").read_text(encoding="utf-8")

    for fragment in (
        'SUBJECT_SLUG=$(echo "$INIT" | gpd json get .publication_subject_slug --default "")',
        'PACKAGE_ROOT="${PUBLICATION_ROOT}/arxiv"',
        'SUBMISSION_DIR="${PACKAGE_ROOT}/submission"',
        'PACKAGE_TARBALL="${PACKAGE_ROOT}/arxiv-submission.tar.gz"',
        'PACKAGE_VALIDATION=$(gpd --raw validate arxiv-package --submission-dir "$SUBMISSION_DIR" --tarball "$PACKAGE_TARBALL"',
        'echo "$PACKAGE_VALIDATION"',
        "GPD/publication/${SUBJECT_SLUG}/arxiv/",
    ):
        assert fragment in source

    assert "${subject_slug}" not in source
    assert "--materialize" not in source
    assert source.index('echo "$PACKAGE_VALIDATION"') < source.index("Present a final checklist")


def test_stage_one_deferred_authorities_are_not_raw_projection_includes() -> None:
    offenders: list[str] = []

    for manifest_path in sorted(WORKFLOWS_DIR.glob("*-stage-manifest.json")):
        workflow_name = manifest_path.name.removesuffix("-stage-manifest.json")
        workflow_path = WORKFLOWS_DIR / f"{workflow_name}.md"
        if not workflow_path.is_file():
            continue

        manifest = _load_manifest(workflow_name)
        stage_ids = manifest.stage_ids()
        if not stage_ids:
            continue
        first_stage = manifest.stage(stage_ids[0])
        deferred_authorities = set(first_stage.must_not_eager_load)
        if not deferred_authorities:
            continue

        for line_number, include_relpath in _raw_projection_include_relpaths(workflow_path.read_text(encoding="utf-8")):
            if include_relpath in deferred_authorities:
                if include_relpath in RAW_INCLUDE_ALLOWED_DEFERRED_AUTHORITIES:
                    continue
                offenders.append(f"{workflow_path.name}:{line_number}:{include_relpath}")

    assert offenders == []


def test_split_publication_stage_authorities_do_not_raw_include_manifest_owned_authorities() -> None:
    offenders: list[str] = []

    for workflow_name in ("write-paper", "peer-review", "respond-to-referees", "arxiv-submission"):
        manifest = _load_manifest(workflow_name)
        for stage in manifest.stages:
            manifest_owned = set(stage.loaded_authorities)
            for conditional in stage.conditional_authorities:
                manifest_owned.update(conditional.authorities)

            for mode_path in stage.mode_paths:
                source_path = SOURCE_ROOT / "specs" / mode_path
                for line_number, include_relpath in _raw_projection_include_relpaths(
                    source_path.read_text(encoding="utf-8")
                ):
                    if include_relpath in manifest_owned:
                        offenders.append(
                            f"{workflow_name}.{stage.id}:{source_path.name}:{line_number}:{include_relpath}"
                        )

    assert offenders == []


def test_manifest_owned_publication_authorities_expand_once_without_inline_duplicates() -> None:
    respond_bootstrap = _load_manifest("respond-to-referees").stage("bootstrap")
    arxiv_bootstrap = _load_manifest("arxiv-submission").stage("bootstrap")
    peer_preflight = _load_manifest("peer-review").stage("preflight")
    write_authoring = _load_manifest("write-paper").stage("figure_and_section_authoring")
    response_authoring = _load_manifest("respond-to-referees").stage("response_authoring")

    assert count_unfenced_heading(_expanded_stage_surface(respond_bootstrap), "# Publication Bootstrap Preflight") == 1
    assert count_unfenced_heading(_expanded_stage_surface(arxiv_bootstrap), "# Publication Bootstrap Preflight") == 1
    assert _expanded_stage_surface(peer_preflight).count("Canonical manuscript-root publication preflight.") == 1

    assert "# Runtime Delegation Note" not in _expanded_stage_surface(write_authoring)
    assert (
        count_unfenced_heading(
            _expanded_stage_surface(write_authoring, selected_conditions=("writer_spawn_needed",)),
            "# Runtime Delegation Note",
        )
        == 1
    )
    assert "# Runtime Delegation Note" not in _expanded_stage_surface(response_authoring)
    assert (
        count_unfenced_heading(
            _expanded_stage_surface(response_authoring, selected_conditions=("writer_spawn_needed",)),
            "# Runtime Delegation Note",
        )
        == 1
    )


def test_write_paper_stage_manifest_uses_canonical_publication_contracts() -> None:
    manifest = _load_manifest("write-paper")

    assert manifest.stage_ids() == (
        "paper_bootstrap",
        "outline_and_scaffold",
        "figure_and_section_authoring",
        "consistency_and_references",
        "publication_review",
    )

    bootstrap = manifest.stage("paper_bootstrap")
    outline = manifest.stage("outline_and_scaffold")
    authoring = manifest.stage("figure_and_section_authoring")
    consistency = manifest.stage("consistency_and_references")
    publication_review = manifest.stage("publication_review")

    assert {
        "publication_subject_status",
        "publication_bootstrap_mode",
        "publication_bootstrap_root",
        "artifact_manifest_path",
        "effective_reference_intake",
        "publication_subject_slug",
        "publication_lane_kind",
        "publication_lane_owner",
        "selected_publication_root",
        "publication_intake_root",
        "managed_publication_root",
        "managed_manuscript_root",
    } <= set(bootstrap.required_init_fields)
    assert "reference_artifacts_content" not in bootstrap.required_init_fields
    assert {"active_reference_context", "protocol_bundle_context"}.isdisjoint(bootstrap.required_init_fields)
    assert {
        "selected_protocol_bundle_ids",
        "protocol_bundle_load_manifest",
    } <= set(bootstrap.required_init_fields)
    assert bootstrap.writes_allowed == ()
    for stage in (bootstrap, outline, authoring, consistency, publication_review):
        assert "write_paper_argument_input" in stage.required_init_fields
    assert {"active_reference_context", "protocol_bundle_context"}.isdisjoint(outline.required_init_fields)
    assert {
        "reference_artifacts_content",
        "state_content",
        "roadmap_content",
        "requirements_content",
    }.isdisjoint(outline.required_init_fields)
    assert "reference_artifact_files" in outline.required_init_fields
    assert {"active_reference_context", "protocol_bundle_context"}.isdisjoint(authoring.required_init_fields)
    assert {
        "selected_protocol_bundle_ids",
        "protocol_bundle_load_manifest",
    } <= set(authoring.required_init_fields)
    assert {
        "reference_artifacts_content",
        "state_content",
        "roadmap_content",
        "requirements_content",
    }.isdisjoint(authoring.required_init_fields)
    assert {
        "reference_artifact_files",
        "citation_source_files",
        "derived_citation_sources",
    } <= set(authoring.required_init_fields)
    assert _conditional_authorities_by_when(authoring) == {
        "writer_spawn_needed": frozenset({"references/orchestration/runtime-delegation-note.md"})
    }
    assert "references/orchestration/runtime-delegation-note.md" in authoring.must_not_eager_load
    assert {"active_reference_context", "protocol_bundle_context"}.isdisjoint(consistency.required_init_fields)
    assert {
        "state_content",
        "roadmap_content",
        "requirements_content",
    }.isdisjoint(consistency.required_init_fields)
    assert {
        "citation_source_files",
        "selected_protocol_bundle_ids",
        "protocol_bundle_load_manifest",
    } <= set(consistency.required_init_fields)
    assert outline.writes_allowed[0] == WRITE_PAPER_MANAGED_MANUSCRIPT_ROOT
    assert WRITE_PAPER_MANAGED_INTAKE_ROOT in outline.writes_allowed
    assert authoring.writes_allowed[0] == WRITE_PAPER_MANAGED_MANUSCRIPT_ROOT
    assert consistency.writes_allowed[0] == WRITE_PAPER_MANAGED_MANUSCRIPT_ROOT
    assert publication_review.writes_allowed[0] == WRITE_PAPER_MANAGED_MANUSCRIPT_ROOT
    assert "selected_review_root" in publication_review.required_init_fields
    assert "GPD/references-status.json" in consistency.writes_allowed
    assert "GPD/AUTHOR-RESPONSE.md" in publication_review.writes_allowed
    assert "GPD/REFEREE-REPORT.tex" in publication_review.writes_allowed
    assert {
        "GPD/publication/{subject_slug}/AUTHOR-RESPONSE{round_suffix}.md",
        "GPD/publication/{subject_slug}/review/REFEREE_RESPONSE{round_suffix}.md",
        "GPD/publication/{subject_slug}/REFEREE-REPORT{round_suffix}.md",
        "GPD/publication/{subject_slug}/REFEREE-REPORT{round_suffix}.tex",
    } <= set(publication_review.writes_allowed)

    assert {
        "references/publication/publication-review-round-artifacts.md",
        "references/publication/publication-response-artifacts.md",
    } <= set(bootstrap.must_not_eager_load)

    assert consistency.loaded_authorities == (
        "workflows/write-paper/consistency-references.md",
        "references/publication/stage-recovery-gate.md",
        "templates/paper/bibliography-audit-schema.md",
        "templates/paper/reproducibility-manifest.md",
    )
    publication_review_loaded = set(publication_review.loaded_authorities)
    assert WRITE_PAPER_PUBLICATION_REVIEW_REQUIRED_EAGER <= publication_review_loaded
    assert publication_review_loaded.isdisjoint(WRITE_PAPER_PUBLICATION_REVIEW_DEFERRED)
    assert WRITE_PAPER_PUBLICATION_REVIEW_DEFERRED <= set(publication_review.must_not_eager_load)
    assert _conditional_authorities_by_when(publication_review) == WRITE_PAPER_PUBLICATION_REVIEW_CONDITIONALS


def test_read_only_bootstrap_stages_do_not_expose_write_or_spawn_tools() -> None:
    offenders: list[str] = []

    for workflow_name, stage_id in READ_ONLY_BOOTSTRAP_STAGE_IDS:
        stage = _load_manifest(workflow_name).stage(stage_id)
        exposed_tools = sorted(WRITE_OR_SPAWN_TOOLS.intersection(stage.allowed_tools))
        if exposed_tools:
            offenders.append(f"{workflow_name}.{stage_id}: {', '.join(exposed_tools)}")

    assert offenders == []


def test_peer_review_stage_manifest_uses_canonical_publication_contracts() -> None:
    manifest = _load_manifest("peer-review")

    assert manifest.stage_ids() == (
        "bootstrap",
        "preflight",
        "artifact_discovery",
        "panel_stages",
        "final_adjudication",
        "finalize",
    )

    bootstrap = manifest.stage("bootstrap")
    preflight = manifest.stage("preflight")
    artifact_discovery = manifest.stage("artifact_discovery")
    panel_stages = manifest.stage("panel_stages")
    final_adjudication = manifest.stage("final_adjudication")
    finalize = manifest.stage("finalize")

    assert {
        "references/publication/publication-review-round-artifacts.md",
        "references/publication/publication-response-artifacts.md",
    } <= set(bootstrap.must_not_eager_load)
    assert {
        "publication_subject_slug",
        "publication_lane_kind",
        "publication_lane_owner",
        "managed_publication_root",
        "selected_publication_root",
        "selected_review_root",
    } <= set(bootstrap.required_init_fields)
    assert "reference_artifacts_content" not in bootstrap.required_init_fields
    assert {"active_reference_context", "protocol_bundle_context"}.isdisjoint(bootstrap.required_init_fields)

    assert preflight.loaded_authorities[0] == "workflows/peer-review/preflight.md"
    assert preflight.loaded_authorities == (
        "workflows/peer-review/preflight.md",
        "templates/paper/publication-manuscript-root-preflight.md",
    )
    assert _conditional_authorities_by_when(preflight) == {
        "review_integrity_recovery_needed": frozenset({"references/publication/peer-review-reliability.md"}),
        "manual_publication_artifact_validation": frozenset(
            {
                "templates/paper/paper-config-schema.md",
                "templates/paper/artifact-manifest-schema.md",
                "templates/paper/bibliography-audit-schema.md",
                "templates/paper/reproducibility-manifest.md",
            }
        ),
    }
    assert "reference_artifacts_content" not in preflight.required_init_fields
    assert "protocol_bundle_context" not in preflight.required_init_fields
    assert "active_reference_context" not in preflight.required_init_fields
    assert artifact_discovery.loaded_authorities == (
        "workflows/peer-review/artifact-discovery.md",
        "references/publication/publication-review-round-artifacts.md",
        "references/publication/publication-response-artifacts.md",
    )
    assert "GPD/review/CLAIMS{round_suffix}.json" in panel_stages.writes_allowed
    for field in (
        "manuscript_root",
        "manuscript_entrypoint",
        "artifact_manifest_path",
        "bibliography_audit_path",
        "reproducibility_manifest_path",
    ):
        assert field in panel_stages.required_init_fields
        assert field in final_adjudication.required_init_fields
    assert "GPD/publication/{subject_slug}/review/CLAIMS{round_suffix}.json" in panel_stages.writes_allowed
    assert "GPD/publication/{subject_slug}/review/PROOF-REDTEAM{round_suffix}.md" in panel_stages.writes_allowed
    assert {
        "project_contract",
        "reference_artifacts_content",
        "active_reference_context",
        "protocol_bundle_context",
    }.isdisjoint(panel_stages.required_init_fields)
    assert {
        "selected_protocol_bundle_ids",
        "protocol_bundle_load_manifest",
        "reference_artifact_files",
    } <= set(panel_stages.required_init_fields)
    panel_loaded = set(panel_stages.loaded_authorities)
    final_loaded = set(final_adjudication.loaded_authorities)
    assert PEER_REVIEW_PANEL_REQUIRED_EAGER <= panel_loaded
    assert PEER_REVIEW_PANEL_DEFERRED <= set(panel_stages.must_not_eager_load)
    assert _conditional_authorities_by_when(panel_stages) == {
        "panel_rubric_expansion_needed": frozenset({"references/publication/peer-review-panel-playbook.md"}),
        "panel_child_recovery_needed": frozenset({"references/publication/stage-recovery-gate.md"}),
        "theorem_bearing_claims_present": frozenset(
            {
                "references/verification/core/proof-redteam-workflow-gate.md",
                "references/verification/core/proof-redteam-protocol.md",
                "templates/proof-redteam-schema.md",
            }
        ),
    }
    assert panel_loaded.isdisjoint(PEER_REVIEW_PANEL_FINAL_ONLY_AUTHORITIES)
    assert PEER_REVIEW_FINAL_ADJUDICATION_REQUIRED_EAGER <= final_loaded
    assert final_loaded.isdisjoint(PEER_REVIEW_FINAL_ADJUDICATION_DEFERRED)
    assert PEER_REVIEW_FINAL_ADJUDICATION_DEFERRED <= set(final_adjudication.must_not_eager_load)
    assert "GPD/review/REVIEW-LEDGER{round_suffix}.json" in final_adjudication.writes_allowed
    assert "GPD/publication/{subject_slug}/review/REVIEW-LEDGER{round_suffix}.json" in final_adjudication.writes_allowed
    assert "GPD/publication/{subject_slug}/REFEREE-REPORT{round_suffix}.md" in final_adjudication.writes_allowed
    assert {
        "latest_review_round_suffix",
        "latest_referee_report_md",
        "latest_referee_report_tex",
        "latest_author_response",
        "latest_referee_response",
        "latest_response_round_suffix",
    } <= set(finalize.required_init_fields)


def test_arxiv_submission_stage_manifest_surfaces_publication_routing() -> None:
    manifest = _load_manifest("arxiv-submission")
    bootstrap = manifest.stage("bootstrap")
    manuscript_preflight = manifest.stage("manuscript_preflight")
    review_gate = manifest.stage("review_gate")
    package = manifest.stage("package")
    finalize = manifest.stage("finalize")
    route_fields = {
        "publication_subject_slug",
        "publication_lane_kind",
        "publication_lane_owner",
        "managed_publication_root",
        "selected_publication_root",
        "selected_review_root",
    }
    review_payload_fields = {
        "latest_review_artifacts",
        "latest_author_response",
        "latest_referee_response",
        "latest_response_artifacts",
    }

    assert manifest.prompt_usage == "staged_init"
    assert "arxiv_submission_argument_input" in bootstrap.required_init_fields
    assert route_fields <= set(bootstrap.required_init_fields)
    assert "latest_response_round" in bootstrap.required_init_fields
    assert "latest_response_requires_fresh_review" in bootstrap.required_init_fields
    assert "latest_response_freshness" in bootstrap.required_init_fields
    assert review_payload_fields.isdisjoint(bootstrap.required_init_fields)
    assert review_payload_fields.isdisjoint(manuscript_preflight.required_init_fields)
    assert review_payload_fields.isdisjoint(package.required_init_fields)
    assert review_payload_fields.isdisjoint(finalize.required_init_fields)
    assert {
        "latest_review_ledger",
        "latest_referee_decision",
        "latest_review_artifacts",
        "latest_author_response",
        "latest_referee_response",
        "latest_response_artifacts",
        "latest_response_freshness",
        "derived_manuscript_proof_review_status",
    } <= set(review_gate.required_init_fields)
    assert _conditional_authorities_by_when(review_gate) == {
        "review_integrity_recovery_needed": frozenset({"references/publication/peer-review-reliability.md"})
    }
    assert "references/publication/peer-review-reliability.md" in review_gate.must_not_eager_load
    assert package.writes_allowed == ("GPD/publication/{subject_slug}/arxiv",)
    for stage_id in manifest.stage_ids():
        stage_fields = set(manifest.stage(stage_id).required_init_fields)
        assert "arxiv_submission_argument_input" in stage_fields
        assert route_fields <= stage_fields


def test_respond_to_referees_stage_manifest_uses_publication_response_contracts() -> None:
    manifest = _load_manifest("respond-to-referees")

    assert manifest.stage_ids() == (
        "bootstrap",
        "report_triage",
        "revision_planning",
        "response_authoring",
        "finalize",
    )

    bootstrap = manifest.stage("bootstrap")
    report_triage = manifest.stage("report_triage")
    revision_planning = manifest.stage("revision_planning")
    response_authoring = manifest.stage("response_authoring")
    finalize = manifest.stage("finalize")

    assert "references/publication/publication-bootstrap-preflight.md" in bootstrap.loaded_authorities
    assert "references/publication/publication-response-writer-handoff.md" in bootstrap.must_not_eager_load
    assert "references/publication/stage-recovery-gate.md" in bootstrap.must_not_eager_load
    assert "project_root" in bootstrap.required_init_fields
    assert "response_intake_input" in bootstrap.required_init_fields
    assert "publication_subject_slug" in bootstrap.required_init_fields
    assert "publication_lane_kind" in bootstrap.required_init_fields
    assert "selected_publication_root" in bootstrap.required_init_fields
    assert "selected_review_root" in bootstrap.required_init_fields
    assert "latest_response_artifacts" in bootstrap.required_init_fields
    assert "reference_artifacts_content" not in bootstrap.required_init_fields
    assert "reference_artifacts_content" not in report_triage.required_init_fields
    assert "reference_artifacts_content" not in revision_planning.required_init_fields
    assert "reference_artifacts_content" in response_authoring.required_init_fields
    assert {"active_reference_context", "protocol_bundle_context"}.isdisjoint(bootstrap.required_init_fields)
    assert {"active_reference_context", "protocol_bundle_context"}.isdisjoint(report_triage.required_init_fields)
    assert {"active_reference_context", "protocol_bundle_context"}.isdisjoint(revision_planning.required_init_fields)
    assert {
        "selected_protocol_bundle_ids",
        "protocol_bundle_load_manifest",
    } <= set(revision_planning.required_init_fields)
    assert {"active_reference_context", "protocol_bundle_context"} <= set(response_authoring.required_init_fields)

    assert bootstrap.mode_paths == ("workflows/respond-to-referees/bootstrap.md",)
    assert bootstrap.loaded_authorities == (
        "workflows/respond-to-referees/bootstrap.md",
        "references/publication/publication-bootstrap-preflight.md",
    )
    assert "workflows/respond-to-referees.md" in bootstrap.must_not_eager_load
    assert "workflows/respond-to-referees/report-triage.md" in bootstrap.must_not_eager_load
    assert "workflows/respond-to-referees/response-authoring.md" in bootstrap.must_not_eager_load
    assert "workflows/respond-to-referees/finalize.md" in bootstrap.must_not_eager_load
    assert report_triage.loaded_authorities == (
        "workflows/respond-to-referees/report-triage.md",
        "references/publication/publication-response-writer-handoff.md",
    )
    assert _conditional_authorities_by_when(report_triage) == {
        "review_integrity_recovery_needed": frozenset({"references/publication/peer-review-reliability.md"}),
        "checkpoint_or_child_recovery_needed": frozenset({"references/publication/stage-recovery-gate.md"}),
    }
    assert revision_planning.loaded_authorities == ("workflows/respond-to-referees/revision-planning.md",)
    assert _conditional_authorities_by_when(revision_planning) == {
        "response_pair_artifact_contract_needed": frozenset(
            {"references/publication/publication-response-writer-handoff.md"}
        ),
        "review_integrity_recovery_needed": frozenset({"references/publication/peer-review-reliability.md"}),
        "checkpoint_or_child_recovery_needed": frozenset({"references/publication/stage-recovery-gate.md"}),
    }
    for stage_id in manifest.stage_ids()[1:]:
        assert "response_intake_input" in manifest.stage(stage_id).required_init_fields
    assert "templates/paper/referee-response.md" in response_authoring.loaded_authorities
    assert "templates/paper/author-response.md" in response_authoring.loaded_authorities
    assert "references/publication/stage-recovery-gate.md" in response_authoring.loaded_authorities
    assert "references/orchestration/runtime-delegation-note.md" not in response_authoring.loaded_authorities
    assert "references/orchestration/runtime-delegation-note.md" in response_authoring.must_not_eager_load
    assert _conditional_authorities_by_when(response_authoring) == {
        "writer_spawn_needed": frozenset({"references/orchestration/runtime-delegation-note.md"}),
        "review_integrity_recovery_needed": frozenset({"references/publication/peer-review-reliability.md"}),
    }
    assert finalize.loaded_authorities == (
        "workflows/respond-to-referees/finalize.md",
        "references/publication/publication-response-writer-handoff.md",
    )
    assert _conditional_authorities_by_when(finalize) == {
        "review_integrity_recovery_needed": frozenset({"references/publication/peer-review-reliability.md"}),
        "checkpoint_or_child_recovery_needed": frozenset({"references/publication/stage-recovery-gate.md"}),
    }
    assert "GPD/AUTHOR-RESPONSE{round_suffix}.md" in response_authoring.writes_allowed
    assert "GPD/review/REFEREE_RESPONSE{round_suffix}.md" in response_authoring.writes_allowed
    assert "GPD/publication/{subject_slug}/AUTHOR-RESPONSE{round_suffix}.md" in response_authoring.writes_allowed
    assert "GPD/publication/{subject_slug}/review/REFEREE_RESPONSE{round_suffix}.md" in finalize.writes_allowed
    assert "latest_review_round_suffix" in finalize.required_init_fields


def test_respond_to_referees_workflow_uses_staged_init_without_inline_field_list() -> None:
    root_index = (WORKFLOWS_DIR / "respond-to-referees.md").read_text(encoding="utf-8")
    workflow = workflow_authority_text(WORKFLOWS_DIR, "respond-to-referees")

    assert "Do not use this index as active stage authority." in root_index
    assert "workflows/respond-to-referees/bootstrap.md" in root_index
    assert "gpd --raw init respond-to-referees --stage bootstrap" in workflow
    assert "gpd --raw init phase-op --include config" not in workflow
    assert "respond-to-referees-stage-manifest.json" in root_index
    assert "INIT.staged_loading.field_access_instruction" in workflow
    assert "Parse JSON for: `commit_docs`, `state_exists`, `project_exists`" not in workflow


def test_publication_bootstrap_preflight_uses_canonical_publication_contracts() -> None:
    source = (REFERENCES_DIR / "publication-bootstrap-preflight.md").read_text(encoding="utf-8")

    assert "Canonical workflow-facing bootstrap and preflight reference for publication tasks." in source
    assert "publication-manuscript-root-preflight.md" in source
    assert "publication-review-round-artifacts.md" in source
    assert "publication-response-artifacts.md" in source
    assert "publication-artifact-gates.md" not in source


def test_publication_response_writer_handoff_uses_canonical_completion_gate() -> None:
    source = (REFERENCES_DIR / "publication-response-writer-handoff.md").read_text(encoding="utf-8")

    assert "Canonical workflow-facing handoff and completion reference for spawned response-writing work." in source
    assert "publication-response-artifacts.md" in source
    assert "stage-recovery-gate.md" in source
    assert "status: checkpoint" in source
    assert "gpd_return.files_written" in source
    assert "publication-artifact-gates.md" not in source


def test_publication_review_wrapper_guidance_points_to_the_new_shared_refs() -> None:
    source = (REFERENCES_DIR / "publication-review-wrapper-guidance.md").read_text(encoding="utf-8")

    assert "publication-bootstrap-preflight.md" in source
    assert "publication-response-writer-handoff.md" in source
    assert "publication-artifact-gates.md" not in source
