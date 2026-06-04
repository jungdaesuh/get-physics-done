<purpose>
Orchestrate conversational verification through a thin session wrapper around `gpd-verifier`.

The verifier owns target construction, proof policy, checks, comparison verdicts, and canonical status. Scientific status ownership and routing vocabulary live in `{GPD_INSTALL_DIR}/references/verification/verification-status-authority.md`. This workflow owns preflight, routing, interaction, sync, diagnosis, and gap repair.
</purpose>
<philosophy>
**Do not duplicate verifier policy here.**

- Fail closed before delegation if the project, roadmap, contract, or proof readiness are not usable.
- Use `{GPD_INSTALL_DIR}/references/verification/verification-status-authority.md` for status ownership and vocabulary; this wrapper gates artifacts and routes, but does not decide the scientific verdict.
- Present verifier-produced evidence one check at a time and record only the session overlay in this workflow.
- Every spawned agent is a one-shot delegation: if it needs user input or new evidence arrives after return, start a fresh continuation; never send more input to closed child.
- File-producing handoffs must prove the expected artifact exists before success is accepted.
</philosophy>
<stage_scope>
Stage id: `phase_bootstrap`. Owns proof-readiness classification and the mandatory proof-redteam repair handoff before verifier delegation. Do not load verifier report, interactive-validation, or gap-repair authorities here.
</stage_scope>
@{GPD_INSTALL_DIR}/references/orchestration/runtime-delegation-note.md

<process>

<step name="proof_readiness_gate">
Detect whether the phase is proof-bearing before any verifier handoff.

@{GPD_INSTALL_DIR}/references/verification/core/proof-redteam-workflow-gate.md

Load proof/bootstrap before using proof freshness or proof-repair routing:

```bash
PHASE_BOOTSTRAP_INIT=$(gpd --raw init verify-work "${PHASE_ARG}" --stage phase_bootstrap)
if [ $? -ne 0 ]; then
  echo "ERROR: gpd phase-bootstrap initialization failed: $PHASE_BOOTSTRAP_INIT"
  # STOP; surface the error.
fi
PHASE_DIR_ABS=$(echo "$PHASE_BOOTSTRAP_INIT" | gpd json get .phase_dir_abs --default "$PHASE_DIR_ABS")
```

<field_access>
Apply `PHASE_BOOTSTRAP_INIT.staged_loading.field_access_instruction` before
reading `PHASE_BOOTSTRAP_INIT`. Proof readiness stays fail-closed until phase
artifacts are inspected.
</field_access>

`staged_loading.checkpoints` is not a proof classifier; ignore `phase_proof_review_status.state=not_reviewed|fresh` alone.
Classify proof-bearing only from research artifacts; exclude installed runtime/config/skills trees and generated manifests.

Use `phase_proof_review_status` as the proof-review freshness summary. For proof-bearing work, require a canonical `*-PROOF-REDTEAM.md` artifact; if missing/stale/malformed/not `passed`, spawn `gpd-check-proof` once before finalizing gaps. Use `proof_redteam_finalizer_bridge` as the helper-owned passed-audit bridge.
This additional mandatory floor applies.

```bash
CHECK_PROOF_MODEL=$(gpd resolve-model gpd-check-proof)
```

> Apply the canonical runtime delegation convention above; this proof handoff uses the tuple below for status, freshness, and fail-closed routing.

```
PROOF_HANDOFF_STARTED_AT=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
task(
  subagent_type="gpd-check-proof",
  model="{check_proof_model}",
  readonly=false,
  prompt="First, read {GPD_AGENTS_DIR}/gpd-check-proof.md for your role and instructions. Use `gpd proof-redteam skeleton` for non-passing helper-owned proof-redteam frontmatter; for passed audits use `proof_redteam_finalizer_bridge` / `gpd proof-redteam finalize` before `gpd validate proof-redteam`. Use {GPD_INSTALL_DIR}/templates/proof-redteam-schema.md and {GPD_INSTALL_DIR}/references/verification/core/proof-redteam-protocol.md as authority references when helper/validator errors require them. Write `${PHASE_DIR_ABS}/${phase_number}-PROOF-REDTEAM.md`; audit phase proof artifacts, PLAN contract slice, and any current verification artifact; return through the typed proof-redteam handoff contract."
)
```

Run the local `child_gate` below. Generic acceptance and checkpoint semantics are owned by `references/orchestration/child-artifact-gate.md` and `references/orchestration/continuation-boundary.md`; this callsite owns the tuple fields, validators, applicator, and routes.

```yaml
child_gate:
  id: "verify_work_proof_critic"
  role: "gpd-check-proof"
  return_profile: "proof_redteam"
  required_status: "completed"
  expected_artifacts:
    - "${PHASE_DIR_ABS}/${phase_number}-PROOF-REDTEAM.md"
  allowed_roots:
    - "${PHASE_DIR_ABS}"
  freshness_marker: "after $PROOF_HANDOFF_STARTED_AT"
  validators:
    - "gpd proof-redteam finalize ... when producing passed audits"
    - "gpd validate proof-redteam ${PHASE_DIR_ABS}/${phase_number}-PROOF-REDTEAM.md"
    - "frontmatter status: passed before finalizing the gap ledger"
  applicator: none
  failure_route: "fail_closed_or_fresh_proof_continuation | repair_prompt_once | fail_closed | fresh_proof_continuation"
  status_route:
    checkpoint: "fresh proof continuation after user response"
    blocked: "fresh proof continuation or fail closed"
    failed: "fresh proof continuation or fail closed"
```

After the proof critic returns, re-open `${PHASE_DIR_ABS}/${phase_number}-PROOF-REDTEAM.md` from disk and confirm the artifact exists and is `passed` after a successful `gpd proof-redteam finalize ...` and `gpd validate proof-redteam` run before finalizing the gap ledger. Never trust the return text alone; if the file is missing, stale, malformed, or not passed, keep the verification session fail-closed and start a fresh proof continuation.
If `gpd-check-proof` still cannot produce a passed audit, keep the verification status fail-closed.
Do not stop with only the proof-redteam artifact: the canonical verification report must still record the proof gap ledger. Continue to verifier handoff with reopened proof content/freshness so `${PHASE_DIR_ABS}/${phase_number}-VERIFICATION.md` is written/updated with a gap report or blocked `gpd_return.status`; otherwise route to `gpd:verify-work ${phase_number}`.
</step>

</process>
