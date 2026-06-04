<purpose>
Plan wave execution, dependency posture, proof-bearing routing, claim alignment, and cadence/risk gates.
</purpose>

<stage_boundary>
This stage owns phase-wide wave planning. It refreshes current phase context, groups incomplete plans, selects the current wave intent, then classifies proof obligations, checks claim/deliverable alignment, and decides cadence/risk policy for the selected wave. It does not spawn executors, verifiers, proof critics, or child-return handlers.
</stage_boundary>

<process>

<stage_policy>
Later staged refreshes surface `effective_reference_intake`, active-reference handles, citation/source status, `reference_artifact_files`, selected protocol-bundle handles, and convention locks for anchor-aware routing. Stable knowledge docs may appear only through those shared handle surfaces as reviewed background; they do not become a separate authority tier.

`execute-plan.md` owns plan-local execution. This stage owns only phase-wide routing and wave risk.

**Mode-aware behavior:**
- `autonomy` controls who gets interrupted at a wave boundary.
- `research_mode` adjusts depth and optional tangents; it never relaxes required gates.
- `review_cadence` controls bounded phase pauses.
- `balanced` keeps standard contract/anchor/review coverage; `adaptive` narrows only after decisive prior evidence or an explicit approach lock; `exploit` suppresses optional tangents by default.
- Disabled generic verifier, sparse cadence, `autonomy=yolo`, or "skip verification" never disables proof red-team for proof-bearing work.
</stage_policy>

<step name="refresh_wave_planning_context">
Refresh the wave-planning stage so the orchestrator does not keep late execution context pinned in bootstrap state:

```bash
WAVE_PLANNING_INIT=$(gpd --raw init execute-phase "${PHASE_ARG}" --stage wave_planning)
if [ $? -ne 0 ]; then
  echo "ERROR: wave-planning stage refresh failed: $WAVE_PLANNING_INIT"
  exit 1
fi
```

Apply `WAVE_PLANNING_INIT.staged_loading.field_access_instruction` before reading `WAVE_PLANNING_INIT`.
</step>

<step name="discover_and_group_plans">
Load plan inventory with wave grouping from `gpd phase index {phase_number}`.

Parse JSON for `phase`, `plans[]` (`id`, `wave`, `interactive`, `gap_closure`, `objective`, `files_modified`, `task_count`, `has_summary`), `waves`, `incomplete`, and `has_checkpoints`.

**Filtering:** skip plans where `has_summary: true`. If `$GAPS_ONLY` is true, also skip non-gap_closure plans. If all filtered: "No matching incomplete plans" -> exit.

**Intra-wave dependency validation:** verify that no plan's `depends_on` references another plan in the same wave. If any same-wave dependency exists, stop and report the plan IDs and wave number.

**Parallel file conflict detection:** for waves with two or more plans, compare the indexed `files_modified` sets. If two plans touch the same path, warn and offer to serialize those plans within the wave.

If `INTRA_WAVE_CONFLICT` is true: STOP, present the dependency issue, and do not proceed.
If `FILE_CONFLICT` is true: WARN, present the overlap, and offer to serialize the conflicting plans within the wave.

Report:

```
## Execution Plan

**Phase {X}: {Name}** -- {total_plans} plans across {wave_count} waves

| Wave | Plans | What it builds |
|------|-------|----------------|
| 1 | 01-01, 01-02 | {from plan objectives, 3-8 words} |
| 2 | 01-03 | ... |
```
</step>

<step name="select_current_wave_intent">
Before proof, claim-alignment, or cadence machinery, select exactly one current wave intent from the filtered incomplete plan inventory.

Choose the earliest runnable wave unless the user explicitly requested a gap-only or narrowed target. If the user changes a wave constraint, revise this current-wave selection before reopening proof or alignment gates.

Emit:

```yaml
current_wave_intent:
  phase: "{phase_number}"
  wave: "{wave_id}"
  selected_plan_ids:
    - "{plan_id}"
  gap_only: "{true | false}"
  objective: "{one sentence from selected plan objectives}"
  sequential_overrides:
    - "{plan_id pair or empty}"
  file_conflicts:
    - "{path or empty}"
  dependency_posture: "runnable | blocked"
```

If dependency posture is blocked, stop with the dependency issue and do not continue into proof, alignment, or dispatch policy.
</step>

<step name="detect_proof_obligation_work">
Classify whether any plan in `current_wave_intent.selected_plan_ids` is proof-bearing before execution and before honoring verifier-disabled or sparse-review settings.

When the selected wave has proof-bearing work, load the conditional authority `{GPD_INSTALL_DIR}/references/verification/core/proof-redteam-workflow-gate.md` for the detailed workflow gate. Mark a plan proof-bearing when it establishes a theorem, lemma, equivalence, bound, identity, no-go result, derivation validity claim, parameter coverage claim, or proof-backed acceptance test. For each proof-bearing selected plan, require a sibling `{plan_id}-PROOF-REDTEAM.md` artifact before wave success can be claimed.

Never treat a clean `SUMMARY.md`, correct algebra in a subset of cases, or "human will inspect later" as a substitute for the sibling proof-redteam artifact. Runtime delegation should use `gpd-check-proof` for that independent audit; executors may draft proof context but must not self-certify theorem-proof alignment.
</step>

<step name="claim_deliverable_alignment_check">
Gate execution on explicit confirmation that the machine-readable claim matches user intent for Phase {N} and the selected current wave.

Read the persisted alignment status and current fingerprints before rendering anything:

```bash
ALIGNMENT_STATUS=$(gpd contract alignment-status 2>/dev/null || echo '{}')
CONTRACT_HASH=$(gpd contract fingerprint 2>/dev/null)
CONTEXT_HASH=$(gpd contract context-fingerprint 2>/dev/null)
CONFIRMED_AT=$(echo "$ALIGNMENT_STATUS" | gpd json get .confirmed_at --default null)
CONFIRMED_CONTRACT_HASH=$(echo "$ALIGNMENT_STATUS" | gpd json get .confirmed_contract_hash --default null)
CONFIRMED_CONTEXT_HASH=$(echo "$ALIGNMENT_STATUS" | gpd json get .confirmed_context_hash --default null)
```

**Fingerprint gate:** fail closed if either fingerprint command fails or resolves to an empty value before rendering the prompt or recording confirmation. Do not compare blank hashes, suppress the gate, or call `gpd contract record-alignment` on this path.

```bash
if [ -z "$CONTRACT_HASH" ] || [ -z "$CONTEXT_HASH" ]; then
  echo "ERROR: claim_deliverable_alignment_check could not resolve contract/context fingerprints."
  echo "Next Up: discuss, plan, then execute phase {N}"
  exit 1
fi
```

**Gating:** fires when `autonomy=supervised` OR `review_cadence=dense` OR any selected plan is proof-bearing per `detect_proof_obligation_work`. Skip only under `autonomy=yolo AND review_cadence in {adaptive, sparse} AND no proof-bearing plans`; log `claim_deliverable_alignment_check: skipped (autonomy=yolo, cadence=adaptive, no proof-bearing plans)` and continue to `resolve_execution_cadence` without prompting.

**Suppression:** if `confirmed_at` is set AND the current `contract_fingerprint == confirmed_contract_hash` AND `context_guidance_fingerprint == confirmed_context_hash`, skip and log `claim_deliverable_alignment_check: skipped (already confirmed this session)`.

**Render:** when fired and not suppressed, render one screen comparing CONTEXT/ContractContextIntake to `gpd contract alignment-summary`. Cover observables, deliverables, required references, stop/rethink conditions, claims, and acceptance tests; cap each side at 5 bullets.

**ask_user:** present exactly one question with 4 options. Enter selects `Y`.

```
ask_user([
  {
    question: "Does the machine contract above match your intent for Phase {N}? Press Enter to proceed, or pick an option to revise.",
    header: "Claim ↔ Deliverable Alignment",
    multiSelect: false,
    options: [
      { label: "Y: proceed (Recommended, Enter = Y)", description: "Record confirmed alignment and continue." },
      { label: "e: edit CONTEXT", description: "Revise intent with gpd:discuss-phase {N}, then re-enter once." },
      { label: "p: edit PLAN contract", description: "Revise the machine contract with gpd:plan-phase {N}, then re-enter once." },
      { label: "n: abort", description: "Stop cleanly. Next Up is gpd:execute-phase {N} after alignment is resolved." }
    ]
  }
])
```

Only explicit `Y: proceed` authorizes record-alignment. Missing `ask_user`, timeout, empty answer, or noninteractive run is not confirmation; STOP before writes, scripts, computations, dispatches, subagents, or artifacts.

On `Y: proceed` record alignment and continue:

```bash
gpd contract record-alignment --contract-hash "$CONTRACT_HASH" --context-hash "$CONTEXT_HASH"
```

On `n`, exit cleanly and emit `Next Up: gpd:execute-phase {N}`. On `e` or `p`, hand off to `gpd:discuss-phase {N}` or `gpd:plan-phase {N}`; if repeated, defer and stop looping.
</step>

<step name="resolve_execution_cadence">
Translate cadence config plus selected-wave risk into execution boundaries before spawning executors.

Read `review_cadence`, `research_mode`, the unattended-minute limits, checkpoint thresholds, `strict_wait`, `never_interrupt_running_workers`, and `never_auto_close_child_agents` from the current staged payload/config. `strict_wait` disables unattended-minute cutoffs entirely; `never_interrupt_running_workers` is the narrower form of the same guarantee. In either case, set plan and wave unattended-minute limits to zero so workers run to natural completion. `never_auto_close_child_agents` means a spawned child remains open until it returns, checkpoints, or fails; no parent stage may synthesize closure.

`autonomy` decides who gets interrupted; `review_cadence` decides when to stop, inspect, or re-question. Even in `yolo`, first-result and pre-fanout gates still run; a clean pass may auto-continue. These are task-level gates, not line-by-line interruptions.

For each wave, classify downstream fanout as risky when any of these holds:
- multiple plans and any later wave depends on it
- any plan has `task_count >= CHECKPOINT_AFTER_N_TASKS`, no authored checkpoints, or likely exceeds `MAX_UNATTENDED_MINUTES_PER_PLAN`
- derivation, formalism, numerical, or validation phase classes
- file conflicts, convention-lock requirements, or benchmark-critical anchors
- new estimator, baseline, or branch point whose downstream value depends on a decisive comparison still to be earned
- sparse evidence where the first material result validates only a proxy or supporting artifact while decisive anchors remain unresolved

When a wave is risky:
- set `FIRST_RESULT_GATE_REQUIRED=true`
- set `PRE_FANOUT_REVIEW_REQUIRED=true`
- set `SEGMENT_TASK_CAP=${CHECKPOINT_AFTER_N_TASKS}`
- force bounded continuation segments even when the authored plan has no checkpoints

When `review_cadence=dense`, treat every wave as risky and require both first-result and pre-fanout gates.

When a wave is not risky, keep bounded execution available for long plans, wall-clock budgets, and context pressure, but allow short low-fanout plans to run without checkpoint-free micro-pauses.

If the risk logic predicts an anchor-thin first material result, emit required placeholder labels for downstream gate owners: weakest unchecked anchor, remaining assumption, quickest disconfirming observation, and downstream plans at risk. Do not populate live first-result or pre-fanout result fields before `wave_return_checkpoint` has accepted a concrete result.

Unexpected but non-blocking alternatives are tangent proposals, not silent side work. Classify each proposal as `ignore`, `defer`, `branch_later`, or `pursue_now`; `pursue_now` requires explicit user request or approved contract scope.

If a tangent should become an explicit side investigation, surface `gpd:tangent` as the follow-up command instead of silently branching inside execution.

Do NOT narrow bounded review scope just because a wave advanced or one proxy passed. Later gate owners keep the weakest unchecked anchor and decisive disconfirming check visible until the gate clears.
</step>

<step name="publish_wave_plan_for_dispatch">
Emit a compact wave-plan record for downstream stages. It must include `current_wave_intent`, each wave's plan IDs, sequential/parallel posture, risk flags, `FIRST_RESULT_GATE_REQUIRED`, `PRE_FANOUT_REVIEW_REQUIRED`, `SEGMENT_TASK_CAP`, proof-bearing plan IDs, file-conflict serialization decisions, and convention-lock assumptions.

This stage owns only the policy and route labels. Full checkpoint presentation belongs to `checkpoint_resume`; executor task semantics belong to `executor_dispatch` and child-readable `workflows/execute-plan.md`; proof-redteam execution belongs to proof critic dispatch/return stages; final verification belongs to aggregate/verification stages.
</step>

</process>
