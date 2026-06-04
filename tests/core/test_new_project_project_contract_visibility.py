"""Prompt/schema visibility assertions for approved-mode project-contract grounding."""

from __future__ import annotations

from pathlib import Path

from gpd.adapters.install_utils import expand_at_includes
from gpd.core.workflow_staging import load_workflow_stage_manifest
from tests.assertion_taxonomy_support import FragmentMode, forbidden_duplicate, machine_exact, semantic_anchor
from tests.markdown_test_support import extract_markdown_section
from tests.workflow_authority_support import workflow_authority_text

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS_DIR = REPO_ROOT / "src" / "gpd" / "specs" / "workflows"
NEW_PROJECT = WORKFLOWS_DIR / "new-project.md"
NEW_PROJECT_STAGE_DIR = WORKFLOWS_DIR / "new-project"
PROJECT_CONTRACT_SCHEMA = REPO_ROOT / "src" / "gpd" / "specs" / "templates" / "project-contract-schema.md"
STATE_SCHEMA = REPO_ROOT / "src" / "gpd" / "specs" / "templates" / "state-json-schema.md"
QUESTIONING = REPO_ROOT / "src" / "gpd" / "specs" / "references" / "research" / "questioning.md"
NEW_PROJECT_M15_SECTION = "#### M1.5. Synthesize And Approve The Scoping Contract"
NEW_PROJECT_STEP4_SECTION = "## 4. Synthesize The Approved Project Contract And Write PROJECT.md"
PROJECT_CONTRACT_OWNER = "project-contract visibility"


def _expanded(path: Path) -> str:
    return expand_at_includes(path.read_text(encoding="utf-8"), REPO_ROOT / "src/gpd/specs", "/runtime/")


def _assert_prompt_contracts(text: str, *assertions) -> None:
    for assertion in assertions:
        assertion.check(text)


def _extract_contract_rule_block_lines(text: str, start_marker: str) -> tuple[str, ...]:
    section = extract_markdown_section(
        text,
        NEW_PROJECT_M15_SECTION,
        context="new-project minimal contract approval section",
    )
    lines = section.splitlines()
    start = lines.index(start_marker)
    bullets: list[str] = []
    for line in lines[start + 1 :]:
        stripped = line.strip()
        if stripped.startswith("- "):
            bullets.append(stripped)
            continue
        if bullets and stripped:
            break
    return tuple(bullets)


def test_new_project_prompt_surfaces_the_canonical_contract_schema_for_project_contract_grounding() -> None:
    new_project_text = workflow_authority_text(WORKFLOWS_DIR, "new-project")
    scope_intake_text = (NEW_PROJECT_STAGE_DIR / "scope-intake.md").read_text(encoding="utf-8")
    scope_approval_text = (NEW_PROJECT_STAGE_DIR / "scope-approval.md").read_text(encoding="utf-8")
    manifest = load_workflow_stage_manifest("new-project")
    scope_intake = manifest.stage("scope_intake")
    literature_survey = manifest.stage("literature_survey")
    roadmap_authoring = manifest.stage("roadmap_authoring")

    _assert_prompt_contracts(
        scope_approval_text,
        machine_exact(
            "canonical schema source remains visible",
            ("templates/project-contract-schema.md", "`project_contract`"),
            owner=PROJECT_CONTRACT_OWNER,
            rationale="new-project must author the object governed by the canonical schema path",
        ),
        semantic_anchor(
            "approval authors a literal project_contract object",
            (
                "literal JSON object",
                "`project_contract` subsection",
                "Follow the schema exactly",
                "near-miss enum values",
            ),
        ),
        semantic_anchor(
            "approval preserves decisive user guidance",
            (
                "decisive output",
                "anchors",
                "prior outputs",
                "stop conditions",
                "rethink triggers",
            ),
        ),
        semantic_anchor(
            "raw approval gate contract follows canonical schema",
            (
                "invented\nkeys",
                "no near-miss enum values",
                "no scalar shortcuts",
                "collapsed `context_intake`",
                "`approach_policy`",
                "`uncertainty_markers`",
                "near-miss enum values",
                "scalar shortcuts",
            ),
        ),
        machine_exact(
            "contract shape and boolean keys stay exact",
            (
                "`context_intake`",
                "`approach_policy`",
                "`uncertainty_markers`",
            ),
            owner=PROJECT_CONTRACT_OWNER,
            rationale="schema keys and JSON boolean values are machine contracts",
        ),
        semantic_anchor(
            "stale inlined schema prose stays absent",
            (
                "the contract schema is closed: do not add invented top-level or nested keys",
                "list fields must stay lists even for single-item values",
                "blank or duplicate list entries are invalid after trimming whitespace",
            ),
            mode=FragmentMode.ABSENT,
        ),
    )
    _assert_prompt_contracts(
        scope_intake_text,
        semantic_anchor(
            "approval-state diagnostics are preserved",
            (
                "`project_contract_load_info`",
                "`project_contract_validation`",
                "preserve that state",
                "visible-but-blocked contract",
            ),
        ),
    )
    assert "project_contract_load_info" in new_project_text
    assert "project_contract_validation" in new_project_text

    assert "staged_loading.field_access_instruction" in new_project_text
    assert "Parse JSON for:" not in scope_intake_text
    assert (
        tuple(
            field
            for field in (
                "commit_docs",
                "autonomy",
                "research_mode",
                "project_exists",
                "state_exists",
                "roadmap_exists",
                "recoverable_project_exists",
                "partial_project_exists",
                "project_recovery_status",
                "init_progress_status",
                "has_research_map",
                "planning_exists",
                "has_research_files",
                "research_file_samples",
                "has_project_manifest",
                "needs_research_map",
                "has_git",
                "platform",
                "project_contract",
                "project_contract_gate",
                "project_contract_load_info",
                "project_contract_validation",
            )
            if field not in scope_intake.required_init_fields
        )
        == ()
    )
    assert "researcher_model" not in scope_intake.required_init_fields
    assert "synthesizer_model" not in scope_intake.required_init_fields
    assert "researcher_model" in literature_survey.required_init_fields
    assert "synthesizer_model" in literature_survey.required_init_fields
    assert "roadmapper_model" in roadmap_authoring.required_init_fields
    for field in (
        "{researcher_model}",
        "{synthesizer_model}",
        "{roadmapper_model}",
    ):
        assert field in new_project_text
    machine_exact(
        "post-approval init commands stay exact",
        (
            "MINIMAL_ARTIFACTS_INIT=$(gpd --raw init new-project --stage minimal_artifacts)",
            "WORKFLOW_PREFS_INIT=$(gpd --raw init new-project --stage workflow_preferences)",
        ),
        owner=PROJECT_CONTRACT_OWNER,
        rationale="late stage selection uses exact raw init commands",
    ).check(new_project_text)
    semantic_anchor(
        "stale continuation wording stays absent",
        "preserve any init-surfaced `project_contract`, `project_contract_load_info`, and "
        "`project_contract_validation` state while deciding whether this is fresh work or a continuation",
        mode=FragmentMode.ABSENT,
    ).check(new_project_text)


def test_new_project_contract_rule_block_is_not_duplicated() -> None:
    scope_approval_text = (NEW_PROJECT_STAGE_DIR / "scope-approval.md").read_text(encoding="utf-8")
    project_artifacts_text = (NEW_PROJECT_STAGE_DIR / "project-artifacts.md").read_text(encoding="utf-8")
    contract_schema_text = _expanded(PROJECT_CONTRACT_SCHEMA)

    _assert_prompt_contracts(
        scope_approval_text,
        forbidden_duplicate(
            "raw approval contract rule appears once",
            "Build a literal JSON object for the `project_contract` subsection",
        ),
        forbidden_duplicate(
            "pre-approval literal contract reminder appears once",
            "literal JSON object",
        ),
    )
    _assert_prompt_contracts(
        project_artifacts_text,
        semantic_anchor(
            "project artifacts consume the approved contract without redefining approval",
            (
                "does not author, approve, validate, or persist the scoping contract",
                "already persisted `project_contract`",
                "source of truth",
            ),
        ),
        machine_exact(
            "project artifacts do not revive stale approval-card fields",
            ("`scope.question`", "`context_intake.must_read_refs`", 'header: "Scope"'),
            owner=PROJECT_CONTRACT_OWNER,
            rationale="stale schema/card fragments would create a second contract variant",
            mode=FragmentMode.ABSENT,
        ),
    )
    assert "context_intake" in scope_approval_text
    assert "uncertainty_markers" in scope_approval_text
    machine_exact(
        "contract schema version and must_surface scalar rules stay exact",
        ("`schema_version` must be the integer `1`.", "`must_surface` is a boolean scalar."),
        owner=PROJECT_CONTRACT_OWNER,
        rationale="schema version and must_surface scalar rules are validator-facing",
    ).check(contract_schema_text)


def test_project_contract_schema_slice_keeps_contract_critical_rules_visible() -> None:
    contract_schema_text = _expanded(PROJECT_CONTRACT_SCHEMA)

    _assert_prompt_contracts(
        contract_schema_text,
        semantic_anchor(
            "schema slice is project-contract-only",
            (
                "Canonical schema",
                "`project_contract` object",
                "`GPD/state.json`",
                "model-facing contract setup",
                "only the `project_contract` shape and rules",
            ),
            section="# Project Contract Schema",
        ),
        semantic_anchor(
            "object sections stay objects",
            (
                "`context_intake`",
                "`approach_policy`",
                "`uncertainty_markers`",
                "JSON objects",
                "not collapse them to strings or lists",
            ),
            section="## Contract Rules",
        ),
        machine_exact(
            "project-contract schema machine fields stay exact",
            ("`schema_version` must be the integer `1`.", "`must_surface` is a boolean scalar.", "`true`", "`false`"),
            owner=PROJECT_CONTRACT_OWNER,
            rationale="schema version and must_surface boolean literals are validator-facing",
            section="## Contract Rules",
        ),
    )


def test_state_schema_surfaces_the_exact_approved_mode_grounding_rule() -> None:
    state_schema_text = _expanded(STATE_SCHEMA)

    _assert_prompt_contracts(
        state_schema_text,
        semantic_anchor(
            "approved mode requires concrete grounding",
            (
                "approved project contract requires",
                "concrete anchor/reference/prior-output/baseline",
                "explicit missing-anchor notes preserve uncertainty",
                "do not satisfy approval on their own",
            ),
        ),
        semantic_anchor(
            "prior outputs require concrete project-root resolution",
            (
                "`must_include_prior_outputs[]`",
                "explicit project-artifact paths or filenames",
                "current project root",
                "`project_root` is unavailable",
                "non-grounding",
                "concrete root",
            ),
            section="### Shared Grounding And Linkage Rules",
        ),
        machine_exact(
            "approved-mode example and validator command stay exact",
            (
                '"must_include_prior_outputs": ["GPD/phases/00-baseline/00-01-SUMMARY.md"]',
                "gpd --raw validate project-contract - --mode approved",
            ),
            owner=PROJECT_CONTRACT_OWNER,
            rationale="examples and CLI command are executable/user-facing contracts",
        ),
        machine_exact(
            "wildcard prior-output examples stay absent",
            ("`GPD/phases/.../*-SUMMARY.md` or `paper/main.tex`", "`GPD/phases/.../SUMMARY.md`"),
            owner=PROJECT_CONTRACT_OWNER,
            rationale="wildcards would make non-concrete paths appear valid",
            mode=FragmentMode.ABSENT,
        ),
        semantic_anchor(
            "anchor text alone is insufficient",
            (
                "`user_asserted_anchors[]`",
                "`known_good_baselines[]`",
                "concrete, re-findable handle",
                "Multi-word prose alone does not count.",
            ),
        ),
        semantic_anchor(
            "stale multi-word grounding heuristic stays absent",
            "should use at least three words and name a concrete benchmark",
            mode=FragmentMode.ABSENT,
        ),
        machine_exact(
            "project-contract object shape and boolean rules stay exact",
            (
                "`context_intake`",
                "`approach_policy`",
                "`uncertainty_markers`",
                "`schema_version` must be the integer `1`.",
                "`must_surface` is a boolean scalar.",
                "`true`",
                "`false`",
                "`context_intake` must not be empty.",
            ),
            owner=PROJECT_CONTRACT_OWNER,
            rationale="schema keys, integer schema version, and JSON boolean literals are validator-facing",
        ),
        machine_exact(
            "proof-bearing claim schema fields stay exact",
            (
                '"claim_kind"',
                '"observables[]"',
                '"deliverables[]"',
                '"acceptance_tests[]"',
                '"references[]"',
                '"parameters[]"',
                '"hypotheses[]"',
                '"quantifiers[]"',
                '"conclusion_clauses[]"',
                '"proof_deliverables[]"',
                "claims[].proof_deliverables[]",
                "`claims[].parameters[]`",
                "`claims[].hypotheses[]`",
                "`claims[].conclusion_clauses[]`",
                "`claims[].acceptance_tests[]`",
            ),
            owner=PROJECT_CONTRACT_OWNER,
            rationale="proof-bearing claim field names and array paths are machine schema contracts",
        ),
        semantic_anchor(
            "project contract claim kind does not inherit peer-review ClaimRecord meaning",
            (
                "`ProjectContract`",
                "`project_contract.claims[]`",
                "`ContractClaim`",
                "`claim_kind` is `theorem`, `lemma`, `corollary`, `proposition`, or `claim`",
                "Do not import the staged peer-review Paper `ClaimRecord` meaning",
            ),
        ),
        semantic_anchor(
            "theorem-like proof obligations remain visible",
            (
                "the statement is theorem-like",
                "`prove/show that`",
                "`for all` / `exists`",
                "any proof field is already populated",
                "`proof_obligation` target",
                "quantifiers",
                "explicit quantifier or domain obligation",
                "proof-specific test kind",
            ),
        ),
        semantic_anchor(
            "placeholder grounding is rejected",
            (
                "already exists inside the current project root",
                "Placeholder or `TBD` text does not count",
                "do not satisfy approved-mode grounding on their own",
            ),
        ),
    )


def test_new_project_and_questioning_gate_do_not_treat_missing_anchor_notes_as_approval_ready_grounding() -> None:
    scope_approval_text = (NEW_PROJECT_STAGE_DIR / "scope-approval.md").read_text(encoding="utf-8")
    questioning_text = QUESTIONING.read_text(encoding="utf-8")

    _assert_prompt_contracts(
        scope_approval_text,
        semantic_anchor(
            "new-project approval waits for real grounding",
            (
                "at least one concrete anchor, reference, prior-output constraint, or baseline",
                "explicit missing-anchor uncertainty",
                "Approval is blocked",
                "Do not invent anchors",
            ),
        ),
        machine_exact(
            "approved-mode validation command remains visible",
            "gpd --raw validate project-contract - --mode approved",
            owner=PROJECT_CONTRACT_OWNER,
            rationale="scope approval must call the approved-mode validator exactly",
        ),
    )
    _assert_prompt_contracts(
        questioning_text,
        machine_exact(
            "questioning gate preserves schema shape warnings",
            (
                "do not invent extra keys or collapse list fields into scalars",
                "Array fields stay arrays, even for singletons",
            ),
            owner=PROJECT_CONTRACT_OWNER,
            rationale="questioning gate must not suggest invalid contract shape shortcuts",
        ),
        semantic_anchor(
            "questioning gate missing-anchor notes are not approval grounding",
            (
                "blank or duplicate list items",
                "at least one concrete anchor, reference, prior output, or baseline",
                "decisive anchor is still unknown",
                "explicit missing-anchor note",
                "do not replace the requirement",
            ),
        ),
    )
