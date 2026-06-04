<purpose>
Route post-execution verification through a fresh verifier child, report bridges, and canonical verification status.
</purpose>

<stage_boundary>
This stage owns verifier spawn, verification_report_skeleton_bridge / verification_report_finalizer_bridge handoff, verification report validation, the verifier child_gate, and canonical verification_status routing. It does not aggregate summaries, close gaps, run the consistency checker, or close the phase.
</stage_boundary>

<handoff_verification>
Handoff verification stays child-owned: the verifier writes `VERIFICATION.md`, the parent validates the artifact and routes on canonical status.
</handoff_verification>

<verification_contract_fields>
`VERIFICATION.md` owns schema-owned ledgers: `plan_contract_ref`, `contract_results`, `comparison_verdicts`, and verifier-side `suggested_contract_checks`. Do not accept verifier-local aliases for these fields.
</verification_contract_fields>

<reference_context_boundary>
Stable knowledge docs surfaced through shared reference surfaces are reviewed background. They do not override the project contract, proof audits, or decisive evidence, and they do not become a separate authority tier.
</reference_context_boundary>

<process>

<step name="load_verification_handoff_stage">
Refresh only this stage before reading verification handoff fields:

```bash
VERIFICATION_HANDOFF_INIT=$(gpd --raw init execute-phase "${PHASE_ARG}" --stage verification_handoff)
if [ $? -ne 0 ] || [ -z "$VERIFICATION_HANDOFF_INIT" ]; then
  echo "ERROR: verification-handoff stage refresh failed: $VERIFICATION_HANDOFF_INIT"
  exit 1
fi
```

Apply `VERIFICATION_HANDOFF_INIT.staged_loading.field_access_instruction` before reading `VERIFICATION_HANDOFF_INIT`.

`VERIFICATION_HANDOFF_INIT` must carry:

- `verification_report_skeleton_bridge`
- `verification_report_finalizer_bridge`
- `effective_reference_intake`, `active_references`, citation/source status, and `reference_artifact_files`
- `selected_protocol_bundle_ids`, `protocol_bundle_load_manifest`, and `protocol_bundle_verifier_extensions`
- proof-review status from child `phase-op` init when available

Keep `{GPD_INSTALL_DIR}/workflows/verify-phase.md` child-readable. Do not eagerly load or restate the full verifier workflow, `verification-core.md`, or schemas unless a helper/validator error requires them.
</step>

<step name="verifier_eligibility">
If `verifier_enabled` is false, skip only the generic post-execution verifier for non-proof phases. Proof-bearing work still needs fresh passing proof-redteam artifacts; missing, stale, malformed, or non-passing artifacts fail closed.

Do not treat a disabled generic verifier as permission to close the phase. Closeout still requires the structured readiness gate and any proof/consistency gates that apply.
</step>

<step name="spawn_verifier">
Verify phase goal achievement, not task completion. Pass phase class, reference/protocol handles, and proof-review status; the child owns target construction and physics checks.

Set the freshness marker immediately before spawning:

```bash
VERIFIER_HANDOFF_STARTED_AT=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
```

Spawn one fresh verifier:

```
task(
  subagent_type="gpd-verifier",
  model="{verifier_model}",
  readonly=false,
  prompt="First, read {GPD_AGENTS_DIR}/gpd-verifier.md for your role and instructions.

Verify Phase {PHASE_NUMBER} against its phase goal and plan contracts.

Load before verdict: verify-phase.md, both report bridges from `VERIFICATION_HANDOFF_INIT`, and schema templates only after helper/validator schema errors. Use the skeleton bridge only for conservative gaps and the finalizer bridge for passed, human_needed, expert_needed, or typed non-gap outcomes. Do not hand-author frontmatter.

<phase_class>{PHASE_CLASSES}</phase_class>
<effective_reference_intake>{effective_reference_intake}</effective_reference_intake>
<active_references>{active_references}</active_references>
<citation_source_files>{citation_source_files}</citation_source_files>
<citation_source_warnings>{citation_source_warnings}</citation_source_warnings>
<reference_artifact_files>{reference_artifact_files}</reference_artifact_files>
<selected_protocol_bundle_ids>{selected_protocol_bundle_ids}</selected_protocol_bundle_ids>
<protocol_bundle_load_manifest>{protocol_bundle_load_manifest}</protocol_bundle_load_manifest>
<protocol_bundle_verifier_extensions>{protocol_bundle_verifier_extensions}</protocol_bundle_verifier_extensions>

<files_to_read>
- Phase plans and summaries: {phase_dir}
- Roadmap: GPD/ROADMAP.md
- State: GPD/STATE.md and GPD/state.json
</files_to_read>

<spawn_contract>
write_scope:
  mode: scoped_write
  allowed_paths:
    - "{phase_dir}/{phase_number}-VERIFICATION.md"
expected_artifacts:
  - "{phase_dir}/{phase_number}-VERIFICATION.md"
shared_state_policy: return_only
</spawn_contract>

Run `gpd --raw init phase-op {PHASE_NUMBER}` and keep project contract, reference handles, protocol verifier extensions, and phase_proof_review_status visible. Stable knowledge docs are background only.

Write to {phase_dir}/{phase_number}-VERIFICATION.md through the verification-report skeleton/finalizer bridge. Return one typed `gpd_return` envelope with status, files_written, the report path, and canonical verification_status: passed | gaps_found | expert_needed | human_needed.",
  description="Verify Phase {PHASE_NUMBER} goal"
)
```
</step>

<step name="verifier_child_gate">
Run the local child_gate before accepting the verifier result. Shared gate/status/continuation rules live in the loaded child-artifact, status-authority, and continuation-boundary references.

```yaml
child_gate:
  id: "post_execution_verifier"
  profile: "execute.verification_report.v1"
  artifact:
    path: "{phase_dir}/{phase_number}-VERIFICATION.md"
  allowed_root: "{phase_dir}"
  freshness_marker: "$VERIFIER_HANDOFF_STARTED_AT"
```

Spawn errors, tuple failures, validator failures, malformed returns, stale or missing `files_written`, and proof-redteam blockers fail closed. The profile-expanded gate requires the verification contract and `verification-status-authority.md` status rules. Verifier returns and frontmatter stay child/helper-owned; this stage cannot mark the phase complete.
</step>

<step name="canonical_status_route">
Read status only after child_gate passes. Route from typed return plus validated top-level `status` / `verification_status`, not headings, marker strings, `session_status`, or prose.

`session_status: validating|completed|diagnosed` is conversational progress only. If the prior report carries `session_status: diagnosed`, use it as context but continue to route from canonical verification status.

| Canonical verification status | Route |
| --- | --- |
| `passed` | Continue to `consistency_check`; do not close the phase yet. |
| `gaps_found` | Continue to `gap_reverification` or stop with the gap route below. |
| `human_needed` | Stop for human review; do not update roadmap/state. |
| `expert_needed` | Stop for expert review; do not update roadmap/state. |

For `gaps_found`, populate a stage_stop before rendering:

```yaml
stage_stop:
  workflow: execute-phase
  stage: verification_handoff
  status: blocked
  reason: verification_gaps_found
  checkpoint: verification_gap
  user_decision_needed: true
  next_runtime_command: "gpd:plan-phase {PHASE_NUMBER} --gaps"
  also_available:
    - "gpd:verify-work {PHASE_NUMBER}"
    - "gpd:suggest-next"
```

## > Next Up

Primary: `gpd:plan-phase {PHASE_NUMBER} --gaps`

**Report:**
- `{phase_dir}/{phase_number}-VERIFICATION.md` -- canonical verification report path

**Also available:**
- `gpd:verify-work {PHASE_NUMBER}` -- rerun or continue verification
- `gpd:suggest-next` -- confirm the next action

<sub>Start a fresh context window, then run the primary command above.</sub>
</step>

</process>
