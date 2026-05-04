"""Focused assertions for verify-work child-return contracts."""

from __future__ import annotations

from pathlib import Path

from gpd.core.context import _build_verification_report_skeleton_bridge

REPO_ROOT = Path(__file__).resolve().parents[2]
AGENTS_DIR = REPO_ROOT / "src/gpd/agents"
TEMPLATES_DIR = REPO_ROOT / "src/gpd/specs/templates"
WORKFLOWS_DIR = REPO_ROOT / "src/gpd/specs/workflows"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_verify_work_inventory_bridge_exposes_writer_command_and_preview_command(tmp_path: Path) -> None:
    phase_info = {
        "directory": "GPD/phases/01-setup",
        "phase_number": "01",
        "plans": ["01-PLAN.md"],
    }

    bridge = _build_verification_report_skeleton_bridge(tmp_path, phase_info)

    assert bridge["skeleton_command"] == (
        f"gpd verification-report skeleton {(tmp_path / 'GPD/phases/01-setup/01-PLAN.md').as_posix()} "
        "--format markdown --status gaps_found"
    )
    assert bridge["writer_command"] == (
        f"gpd verification-report skeleton {(tmp_path / 'GPD/phases/01-setup/01-PLAN.md').as_posix()} "
        f"--write --output {(tmp_path / 'GPD/phases/01-setup/01-VERIFICATION.md').as_posix()} --force "
        "--body-file BODY.md --validate contract --status gaps_found"
    )
    body_contract = bridge["body_contract"]
    assert "`BODY.md` is body-only Markdown" in str(body_contract)
    assert "one fenced executed `python`/`bash` block" in str(body_contract)
    assert "adjacent `**Output:**` plus fenced `output` block" in str(body_contract)
    assert "following `PASS`/`FAIL`/`INCONCLUSIVE` verdict line" in str(body_contract)
    assert "prose bullets alone are invalid" in str(body_contract)
    assert "--raw" not in str(bridge["skeleton_command"])
    assert "run writer_command" in str(bridge["fallback_rule"])
    assert "body-only evidence" in str(bridge["fallback_rule"])
    assert "satisfies body_contract" in str(bridge["fallback_rule"])
    assert "Use skeleton_command as preview context only" in str(bridge["fallback_rule"])
    assert "hand-author or reflow VERIFICATION.md frontmatter" in str(bridge["fallback_rule"])
    assert "use the generated frontmatter as the starting YAML" not in str(bridge["fallback_rule"])


def test_verify_work_verifier_handoff_stays_one_shot_and_routes_on_typed_status() -> None:
    workflow = _read(WORKFLOWS_DIR / "verify-work.md")

    assert "Spawn `gpd-verifier` once and let it own the physics policy." in workflow
    assert 'subagent_type="gpd-verifier"' in workflow
    assert "<spawn_contract>" in workflow
    assert (
        "Route only on the canonical verification frontmatter and `gpd_return.status`; do not route on headings or marker strings."
        in workflow
    )
    assert (
        "If the artifact is missing, unreadable, absent from `gpd_return.files_written`, or fails validation, treat the handoff as incomplete: request a fresh verifier continuation when possible; otherwise surface a non-green stop with validator errors. Never present it as accepted or passed."
        in workflow
    )
    assert (
        "Human-readable headings in the verifier output are presentation only; route on the canonical verification frontmatter and `gpd_return.status`, not on headings or marker strings."
        in workflow
    )
    assert (
        "> Runtime delegation rule: this is a one-shot handoff. If the spawned verifier needs user input, it must checkpoint and return."
        in workflow
    )
    assert (
        "The wrapper must start a fresh continuation after the user responds instead of trying to keep the original verifier alive."
        in workflow
    )
    assert "Do not recompute canonical verification status in this workflow." in workflow


def test_verify_work_verifier_sync_requires_artifact_gate_before_downstream_routing() -> None:
    workflow = _read(WORKFLOWS_DIR / "verify-work.md")

    assert (
        "Route only on the canonical verification frontmatter and `gpd_return.status`; do not route on headings or marker strings."
        in workflow
    )
    assert "`${PHASE_DIR_ABS}/${phase_number}-VERIFICATION.md` exists on disk and is readable" in workflow
    assert "the same path appears in `gpd_return.files_written`" in workflow
    assert 'gpd validate verification-contract "${PHASE_DIR_ABS}/${phase_number}-VERIFICATION.md"' in workflow
    assert (
        'Any verifier-written canonical `VERIFICATION.md`, including gap reports and `blocked`/`failed` handoffs, must pass `gpd validate verification-contract "${PHASE_DIR_ABS}/${phase_number}-VERIFICATION.md"` before this wrapper accepts it as canonical.'
        in workflow
    )
    assert (
        "If the artifact is missing, unreadable, absent from `gpd_return.files_written`, or fails validation, treat the handoff as incomplete: request a fresh verifier continuation when possible; otherwise surface a non-green stop with validator errors. Never present it as accepted or passed."
        in workflow
    )
    assert "Do not recompute canonical verification status in this workflow." in workflow
    assert "If a canonical verification file already existed before this run" in workflow
    assert (
        "If a canonical verification file already exists, preserve its authoritative frontmatter and append only the session-local overlay here."
        in workflow
    )
    assert "Write to `${PHASE_DIR_ABS}/${phase_number}-VERIFICATION.md`." in workflow
    assert (
        'Run `gpd validate verification-contract "${PHASE_DIR_ABS}/${phase_number}-VERIFICATION.md"` before committing it; invalid reports stop non-green and do not advance state.'
        in workflow
    )
    assert (
        workflow.count(
            "Changed verification files fail `gpd pre-commit-check` when this header is missing or mismatched against the active lock."
        )
        == 1
    )
    assert "If the verifier agent fails to spawn or returns an error, keep the session fail-closed." in workflow
    assert "Do not let a stale existing verification file satisfy the success path." in workflow


def test_verify_work_fallback_failed_validation_stops_at_sync_gate() -> None:
    workflow = _read(WORKFLOWS_DIR / "verify-work.md")

    fallback_fragments = (
        "fallback verifier execution is still `gpd-verifier` execution",
        "verification_report_skeleton_bridge",
        "write body-only evidence",
        "satisfies bridge `body_contract`",
        "one fenced executed `python`/`bash` block",
        "adjacent `**Output:**` plus fenced `output`",
        "following `PASS`/`FAIL`/`INCONCLUSIVE` verdict",
        "replace `BODY.md` in its `writer_command`",
        "The writer serializes YAML and validates before canonical acceptance.",
        "Use `skeleton_command` only as read-only preview context",
        "do not hand-author or reflow frontmatter",
        "keep command transcripts, hashes, oracle details, prose-only evidence, and `gpd_return` out of YAML",
        "Read the runtime-projected `{GPD_AGENTS_DIR}/gpd-verifier.md` and schema refs for verifier policy",
        "not for wrapper-side schema recreation",
        "Do not wrapper-repair the canonical report.",
    )
    sync_stop = (
        "- Fallback executions that reach this step after failed report validation stop here: emit the blocked/final response with latest validator errors. "
        "Do not list the invalid `VERIFICATION.md` as an authoritative artifact, do not route to gaps unless a schema-valid gap report exists, do not enter `gap_repair` or `complete_session`, "
        "and do not patch the canonical verification report from this wrapper."
    )

    for fragment in fallback_fragments:
        assert fragment in workflow
    assert sync_stop in workflow
    assert (
        "Schema finalization is bounded: validator pass returns; after the second validator failure total, including the initial failure and one repair rerun, return `gpd_return.status: blocked` with latest errors."
        in workflow
    )

    assert workflow.index("verification_report_skeleton_bridge") < workflow.index('<step name="sync_verifier_output">')
    assert workflow.index("writer_command") < workflow.index('<step name="sync_verifier_output">')
    assert workflow.index(sync_stop) < workflow.index(
        'INTERACTIVE_VALIDATION_INIT=$(gpd --raw init verify-work "${PHASE_ARG}" --stage interactive_validation)'
    )
    assert workflow.index(sync_stop) < workflow.index('<step name="load_gap_repair_stage">')
    assert workflow.index(sync_stop) < workflow.index('<step name="complete_session">')


def test_verify_work_gap_plan_checker_routes_on_canonical_gpd_return_status() -> None:
    workflow = _read(WORKFLOWS_DIR / "verify-work.md")
    checker = _read(AGENTS_DIR / "gpd-plan-checker.md")

    assert 'gpd --raw init verify-work "${PHASE_ARG}" --stage gap_repair' in workflow
    assert "staged payload as the source of truth for planner and checker routing" in workflow
    assert (
        "If the checker returns a structured `gpd_return`, route on `gpd_return.status` and the structured plan lists, not on presentation text:"
        in workflow
    )
    assert (
        "- `completed`: treat the fresh fix plans as verified only after the on-disk files still match the planner's `files_written` set."
        in workflow
    )
    assert (
        "- `checkpoint`: some plans are approved and others need revision; record `approved_plans` and `blocked_plans`, then send only the blocked plans back through the revision loop."
        in workflow
    )
    assert (
        "- `blocked`: nothing is approved; feed the checker issues and blocked plan IDs back into the revision loop without rewriting approved plans."
        in workflow
    )
    assert "- `failed`: present the issues and offer retry or manual revision." in workflow
    assert "Use the structured fields, not the human-readable approval table, as the source of truth." in workflow

    assert (
        "Headings such as `## VERIFICATION PASSED`, `## ISSUES FOUND`, and `## PLAN_BLOCKED — Escalation to User` are presentation only. Route on `gpd_return.status`."
        in checker
    )
    assert (
        "Headings above are presentation only. Route on `gpd_return.status`, the approved/blocked plan lists, and `issues`."
        in checker
    )
    assert "approved_plans: [list of plan IDs that passed]" in checker
    assert "blocked_plans: [list of plan IDs needing revision or escalation]" in checker


def test_verify_work_gap_plan_success_reconciles_files_written_and_disk_artifacts() -> None:
    workflow = _read(WORKFLOWS_DIR / "verify-work.md")
    planner_prompt = _read(TEMPLATES_DIR / "planner-subagent-prompt.md")

    assert (
        "Use `templates/planner-subagent-prompt.md` to build the gap_closure planner handoff from the staged payload."
        in workflow
    )
    assert (
        "Before treating the handoff as complete, verify that the expected `PLAN.md` files exist in the phase directory and are listed in `gpd_return.files_written` from the fresh planner run."
        in workflow
    )
    assert (
        "If the planner fails to spawn or returns an error, keep the session fail-closed and offer retry or manual plan creation. Do not fall through to gap verification on the basis of preexisting `PLAN.md` files alone."
        in workflow
    )
    assert (
        "Before accepting the handoff as complete, confirm the expected `PLAN.md` files are present, readable, and listed in `gpd_return.files_written` from the planner turn."
        in workflow
    )
    assert (
        "If the checker fails to spawn or returns an error, proceed without plan verification but note that the plans were not verified."
        in workflow
    )
    assert "Do not rewrite approved plans during the revision round." in workflow
    assert "Do not fall through to gap verification on the basis of preexisting `PLAN.md` files alone." in workflow

    assert "Planner runs must return a structured `gpd_return` envelope." in planner_prompt
    assert "Do not route on them; route on `gpd_return.status` and the artifact gate below." in planner_prompt
    assert (
        "- `gpd_return.status: completed` means the planner wrote the expected PLAN.md artifacts and they passed the on-disk artifact check."
        in planner_prompt
    )
    assert (
        "Always verify `gpd_return.files_written` against the expected plan artifacts before accepting completion."
        in planner_prompt
    )


def test_verify_work_proof_check_handoff_uses_structured_freshness_and_fail_closed_artifact_gates() -> None:
    workflow = _read(WORKFLOWS_DIR / "verify-work.md")

    assert "Use `phase_proof_review_status` as the proof-review freshness summary." in workflow
    assert (
        "> Runtime delegation rule: this is a single-turn handoff. If the spawned agent needs user input, it checkpoints and returns; do not keep the original run waiting inside the same task."
        in workflow
    )
    assert "Return `status: checkpoint` instead of waiting for user input inside this run." not in workflow
    assert (
        "Never trust the return text alone; if the file is missing, stale, malformed, or not passed, keep the verification session fail-closed and start a fresh proof continuation."
        in workflow
    )
    assert (
        "After the proof critic returns, re-open `${PHASE_DIR_ABS}/${phase_number}-PROOF-REDTEAM.md` from disk and confirm the artifact exists and is `passed` before finalizing the gap ledger."
        in workflow
    )
    assert (
        "If `gpd-check-proof` still cannot produce a passed audit, keep the verification status fail-closed."
        in workflow
    )
    assert "File-producing handoffs must prove the expected artifact exists before success is accepted." in workflow
