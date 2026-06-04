<purpose>
Dispatch the independent proof critic for proof-bearing execute-phase plans and gate proof-redteam artifacts.
</purpose>

<stage_boundary>
This stage owns only proof-critic model resolution, the `gpd-check-proof` handoff, theorem-inventory/proof-redteam requirements, and the proof-redteam child artifact gate. It does not accept executor SUMMARY returns, apply state updates, surface wave artifacts, or choose retry/rollback/skip/stop paths.
</stage_boundary>

<process>

<step name="refresh_proof_critic_dispatch_context">
Refresh only this stage before reading proof-critic fields:

```bash
PROOF_CRITIC_INIT=$(gpd --raw init execute-phase "${PHASE_ARG}" --stage proof_critic_dispatch)
if [ $? -ne 0 ] || [ -z "$PROOF_CRITIC_INIT" ]; then
  echo "ERROR: proof-critic dispatch stage refresh failed: $PROOF_CRITIC_INIT"
  exit 1
fi
```

Apply `PROOF_CRITIC_INIT.staged_loading.field_access_instruction` before reading `PROOF_CRITIC_INIT`.
</step>

<step name="dispatch_proof_critic">
Run this stage only for selected plans classified as proof-bearing by the wave plan.

If any executed plan is proof-bearing, proof verification still runs even when the generic post-execution verifier is disabled. The sibling proof-redteam artifact is a separate fail-closed gate before wave success.

Resolve the proof-critic model once per wave when any selected plan is proof-bearing:

```bash
CHECK_PROOF_MODEL=$(gpd resolve-model gpd-check-proof)
```

After the executor has written the proof/derivation artifacts and `${SUMMARY_FILE}`, but before any wave success is accepted, spawn `gpd-check-proof` in a fresh context:

```
PROOF_HANDOFF_STARTED_AT=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
task(
  subagent_type="gpd-check-proof",
  model="$CHECK_PROOF_MODEL",
  readonly=false,
  prompt="First, read {GPD_AGENTS_DIR}/gpd-check-proof.md for your role and instructions.

Read {GPD_INSTALL_DIR}/templates/proof-redteam-schema.md and {GPD_INSTALL_DIR}/references/verification/core/proof-redteam-protocol.md before writing the proof-redteam artifact.

Operate in proof-redteam mode with a fresh context and the proof-redteam protocol's one-shot return semantics.

Write exactly: {phase_dir}/{plan_id}-PROOF-REDTEAM.md

Read: {phase_dir}/{plan_file}; {phase_dir}/{plan_id}-SUMMARY.md; the proof, derivation, theorem, lemma, calculation, and verification artifacts referenced by the plan or SUMMARY.

Reconstruct the theorem inventory before judging correctness:
- theorem/lemma/claim ids and statements
- hypotheses and parameter domains
- quantifier scope and excluded cases
- dependencies on earlier results
- proof artifacts and evidence paths

Fail closed on missing parameter coverage, missing hypotheses, narrowed quantifiers, unsupported generalization from special cases, missing dependency checks, or counterexamples. Do not accept executor self-review as proof-redteam evidence.",
  description="Proof redteam for phase {phase_number} plan {plan_id}"
)
```

The proof critic may return `checkpoint` only by handing control back to the parent; it must not wait for user confirmation inside the child run.

Proof critic child artifact gate:

```yaml
child_gate:
  id: "proof_critic_wave_audit"
  profile: "execute.proof_critic_report.v1"
  artifact:
    path: "{phase_dir}/{plan_id}-PROOF-REDTEAM.md"
  allowed_root: "{phase_dir}"
  freshness:
    marker: "$PROOF_HANDOFF_STARTED_AT"
    require_mtime_at_or_after_marker: true
    preexisting_artifacts: "recovery_evidence_only"
  overrides:
    write_allowlist:
      - "{phase_dir}/{plan_id}-PROOF-REDTEAM.md"
```

Gate failure routes the plan to `wave_failure_menu`; a clean executor SUMMARY, local algebra check, or later human inspection is not a substitute for a fresh proof-redteam artifact with `status: passed`. For the sibling `{plan_id}-PROOF-REDTEAM.md` artifact, `gpd-check-proof` is the canonical owner.
</step>

</process>
