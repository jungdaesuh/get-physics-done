<purpose>
Execute the selected research plan (`PLAN.md` or `*-PLAN.md`) and create the matching outcome summary (`SUMMARY.md` or `*-SUMMARY.md`).
`execute-phase.md` owns wave-level routing and fanout; this workflow owns the selected plan's local execution semantics, bounded gates, and summary emission.
</purpose>

<required_reading>
Load the structured init-state payload first; reopen `STATE.md` only if the payload is missing, stale, or flagged by `state_load_source` / `state_integrity_issues`.
Read config.json for planning behavior settings.
Defer execution-reference, checkpoint, recovery, and summary-schema loads until the stage that actually consumes them. When those files are needed, read them with the file_read tool in the relevant stage rather than frontloading them here.
</required_reading>

<process>

<step name="tangent_control">
If execution produces a bounded stop for possible side work, return it in the
same execution payload as a new event family with `tangent_summary` and
`tangent_decision`. Use the existing `execution` payload shape. Do not
auto-branch or start side work from telemetry alone.
</step>

<step name="init_context" priority="first">
Load the bootstrap execution context using the staged init payload:

```bash
INIT=$(gpd --raw init execute-phase "${phase}" --stage phase_bootstrap)
if [ $? -ne 0 ]; then
  echo "ERROR: gpd initialization failed: $INIT"
  exit 1
fi
```

This workflow assumes `execute-phase.md` already selected the plan and wave. It does not re-decide wave routing or specialist selection.

Apply `INIT.staged_loading.field_access_instruction` before reading `INIT`. Until the selected plan is visible, use only the selected-plan identity and execution metadata surfaced by that instruction. If `GPD/` is missing, error.
</step>

<step name="identify_plan">
Use `plans`, `incomplete_plans`, and selected-plan metadata from the staged init payload. Find the first plan artifact without a matching summary artifact; do not rediscover it with `ls`, `grep`, or filename parsing unless the payload is missing.

Canonical standalone pairing is `PLAN.md` <-> `SUMMARY.md`; numbered plans pair by shared stem. Decimal phases are supported for numbered files (`01.1-hotfix/`). Preserve separate `phase` and `plan` values from staged metadata so metrics render as "Phase 05 P05-02", not a collapsed plan code.

<if mode="yolo">
Auto-approve: `>> Execute {phase}-{plan}-PLAN.md [Plan X of Y for Phase Z]` -> load_prompt.
</if>

<if mode="interactive" OR="custom with gates.execute_next_plan true">
Present plan identification, ask for confirmation, then load the plan.
</if>
</step>

<step name="load_prompt">
Read the selected plan before the heavy lifecycle machinery:

```bash
ls "${phase_dir}"/PLAN.md "${phase_dir}"/*-PLAN.md 2>/dev/null | sort
ls "${phase_dir}"/SUMMARY.md "${phase_dir}"/*-SUMMARY.md 2>/dev/null | sort
cat "${PLAN_PATH}"
```

This IS the execution instruction. Follow it exactly. If the plan references `CONTEXT.md`, honor the user's research direction throughout.
</step>

<step name="load_phase_classification_context">
After the selected plan is visible, load the phase-classification payload for the local execution gate:

```bash
CONTRACT_INIT=$(gpd --raw init execute-phase "${phase}" --stage phase_classification)
if [ $? -ne 0 ]; then
  echo "ERROR: staged phase-classification init failed: $CONTRACT_INIT"
  exit 1
fi
```

Apply `CONTRACT_INIT.staged_loading.field_access_instruction` before reading `CONTRACT_INIT`.

If `project_contract_load_info.status` starts with `blocked`, STOP and repair the stored contract before executing. Use the surfaced `project_contract_load_info.errors` / `warnings`; do not guess around them from prose-only context.

If `project_contract_validation.valid` is false, STOP and repair the contract before executing. A visible-but-blocked contract is still not an approved execution contract.

Treat `project_contract` as authoritative machine-readable scope only when `project_contract_gate.authoritative` is true. Do not execute from PLAN markdown alone if the contract or active-anchor ledger says a decisive reference, prior output, or forbidden proxy still constrains the work. Treat `effective_reference_intake` as the structured carry-forward ledger for must-read refs, baselines, prior outputs, user anchors, and context gaps. Stable knowledge docs are reviewed background; they do not override the contract or decisive evidence.
</step>

<step name="verify_conventions">
Before execution, verify convention lock is consistent and non-empty:

```bash
CONV_CHECK=$(gpd --raw convention check)
if [ $? -ne 0 ]; then
  echo "WARNING: Convention verification failed - review before executing"
  echo "$CONV_CHECK"
fi
```

If the project has existing phases and the convention lock is empty, this is an error. Conventions must be established before execution proceeds.

Load authoritative conventions when the active task needs them:

```bash
CONVENTIONS=$(gpd --raw convention list 2>/dev/null)
```

Single source of truth is the structured init-state convention payload (`convention_lock` / `derived_convention_lock`). Before using any equation from a prior phase or external source, verify conventions match the lock. See `shared-protocols.md` Convention Tracking Protocol for the 5-point checklist (metric, Fourier, normalization, coupling, renormalization scheme).
</step>

<step name="run_plan_tool_preflight">
Before executing the selected plan, validate any machine-checkable specialized tool requirements declared in plan frontmatter:

```bash
PLAN_PREFLIGHT=$(gpd --raw validate plan-preflight "${PLAN_PATH}")
if [ $? -ne 0 ]; then
  echo "ERROR: plan specialized-tool preflight failed"
  echo "$PLAN_PREFLIGHT"
  exit 1
fi
```

If the preflight reports warnings only, keep them visible during execution. Use declared fallbacks automatically only for non-blocking preferred tools (`required: false`) when the fallback preserves the plan's scientific intent, and document the switch in `SUMMARY.md`. If a required specialized tool is unavailable, stop and revise the plan or environment before execution.
</step>

<step name="previous_phase_check">
Use staged state and summary inventory when available. If the previous SUMMARY has unresolved "Issues Encountered" or "Next Phase Readiness" blockers, present: "Proceed anyway" | "Address first" | "Review previous".
</step>

<step name="record_start_time">
Record the start time and plan-local trace only after the selected plan has passed local preflight:

```bash
PLAN_START_TIME=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
PLAN_START_EPOCH=$(date +%s)
gpd observe event workflow execute-plan.start --phase "${phase}" --plan "${plan}" 2>/dev/null || true
gpd trace start "${phase}" "${plan}" 2>/dev/null || true
```

Keep the GitHub lifecycle reference deferred until checkpoint / closeout handling, but remember that this plan will eventually need `{GPD_INSTALL_DIR}/references/execution/github-lifecycle.md` for branch and remote examples.
</step>

<step name="resolve_execution_bounds">
Read autonomy and cadence controls from init JSON to control decision authority throughout execution. `autonomy` changes who is asked and when; it does NOT disable first-result sanity checks, bounded execution segments, contract/anchor gates, or physics hard stops.

Resolve plan-local bounds using orchestrator tags first, then plan shape:

- if the orchestrator passed `<first_result_gate>true</first_result_gate>`, honor it
- if `review_cadence=dense`, treat `FIRST_RESULT_GATE_REQUIRED=true` as forced; do not recompute it from per-plan heuristics
- if the orchestrator passed `<segment_task_cap>N</segment_task_cap>`, honor it
- otherwise require bounded execution when the plan has no authored checkpoints and `task_count >= CHECKPOINT_AFTER_N_TASKS`
- also require bounded execution when the uninterrupted segment is likely to exceed `MAX_UNATTENDED_MINUTES_PER_PLAN`
- also require bounded execution when the plan establishes a new baseline, new estimator, new ansatz, or first decisive-comparison path that many downstream tasks depend on
- phase ordering, prior momentum, or "we are already deep into execution" never waive a required bounded stop

Set `FIRST_RESULT_GATE_REQUIRED`, `SEGMENT_TASK_CAP`, `BOUNDED_EXECUTION`, and `PRE_FANOUT_REVIEW_REQUIRED` from those inputs. Required gates are only passed by explicit reason-scoped clear/override transitions. Clearing `first_result` must not clear `skeptical_requestioning` or `pre_fanout`, and a `fanout unlock` never substitutes for the matching review clear.

Clean-wave batching under dense is a checkpoint-display optimization, not a correctness shortcut: under supervised + `review_cadence=dense`, a clean pass may show `Approve tasks {N..M} as clean pass? [Y/n/e]` only when every verification event has typed payload `verification.status="passed"` and `verification.issue_count=0`, no deviation or required gate is pending, and the return envelope has `status="completed"` with empty `issues`. Do not parse prose such as "failure language" to decide batching eligibility. If any task omits the typed verification outcome, emits a deviation, fails verification, or trips a required gate, the wave reverts to per-task checkpoints. It collapses keystrokes, not gates.
</step>

<step name="create_checkpoint">
Before any task commit, load `{GPD_INSTALL_DIR}/references/execution/execute-plan-checkpoints.md` and follow its rollback-tag protocol. Keep only the resulting `CHECKPOINT_TAG` in local execution state.
Use `{GPD_INSTALL_DIR}/references/orchestration/checkpoint-ux-convention.md` for checkpoint display wording through that checkpoint reference.
</step>

<step name="detect_previous_attempt">
Use `execute-plan-checkpoints.md` to detect prior task commits for this plan and offer resume-or-fresh-start. Load any prior `plan-commits.json` data into the task-commit ledger before executing.
</step>

<step name="load_wave_planning_context">
Load the wave-planning payload only when the plan is ready to move into segment execution:

```bash
SEGMENT_INIT=$(gpd --raw init execute-phase "${phase}" --stage wave_planning)
if [ $? -ne 0 ]; then
  echo "ERROR: staged wave-planning init failed: $SEGMENT_INIT"
  exit 1
fi
```

Apply `SEGMENT_INIT.staged_loading.field_access_instruction` before reading `SEGMENT_INIT`.

If `selected_protocol_bundle_ids` is non-empty, treat `protocol_bundle_load_manifest` and `protocol_bundle_context` as the plan-execution specialized-loading guide for this plan. Read any bundle-listed core assets now, not during bootstrap. Preserve `protocol_bundle_verifier_extensions` for verifier-ready outputs and downstream summary/verification checks.

Use `reference_artifacts_content` only here, when the segment actually needs to interpret prior outputs, baselines, or unresolved gaps. Use `{GPD_INSTALL_DIR}/references/execution/executor-index.md` as the topic-to-reference map and load only the row needed for active segment work.

When following GitHub lifecycle examples, substitute the repository's actual default branch and remote names for `<default-branch>` and `<remote-name>`; those placeholders are not literal branch or remote names.
</step>

<step name="parse_segments">
Read authored checkpoint declarations from the selected PLAN and merge virtual boundaries from the resolved cadence controls. Routing:

| Checkpoints | Pattern | Execution |
| --- | --- | --- |
| None | A (non-interactive) | Single `gpd-executor`: full plan + SUMMARY + completion commit |
| Verify-only | B (segmented) | Children execute segments; main context handles checkpoints and final aggregation |
| Decision | C (main) | Execute entirely in main context |
| Auto-bounded | D (virtual checkpoints) | Segment at first-result, task-cap, context-pressure, or pre-fanout boundaries |

Pattern A child completion is provisional until the local child gate passes. Pattern B/D child segment outputs and git commits are partial evidence only until the fresh artifact gate, valid typed return, and applicator pass succeed. Commits or output files do not prove success. If the return envelope is missing or invalid, keep the child handoff incomplete and load `execute-plan-recovery.md` for retry, explicit Pattern C main-context fallback, or abort.

> **Handoff verification:** Apply the Pattern A/B/D child artifact gate from `agent-delegation.md` and `child-artifact-gate.md` before success; git commits are partial evidence only. Durable state, contract, continuation, or lineage effects require `gpd apply-return-updates`.

Fresh context per subagent preserves peak quality. Main context stays lean.
</step>

<step name="segment_execution">
Pattern B/D only (authored or virtual checkpoints). Skip for A/C.

1. Build the segment map from authored checkpoint locations plus virtual boundaries from `FIRST_RESULT_GATE_REQUIRED`, `SEGMENT_TASK_CAP`, `MAX_UNATTENDED_MINUTES_PER_PLAN`, and context pressure.
2. Per segment:
   - Subagent route: spawn `gpd-executor` for assigned tasks only. Include task range, plan path, full-plan context requirement, `<autonomy_mode>{AUTONOMY}</autonomy_mode>`, `<review_cadence>{REVIEW_CADENCE}</review_cadence>`, `<segment_task_cap>{SEGMENT_TASK_CAP}</segment_task_cap>`, `<max_unattended_minutes_per_plan>{MAX_UNATTENDED_MINUTES_PER_PLAN}</max_unattended_minutes_per_plan>`, and `<first_result_gate>{FIRST_RESULT_GATE_REQUIRED}</first_result_gate>`. The child returns segment outputs, `contract_updates`, and any durable `continuation_update`; it does not create the final SUMMARY or completion commit.
   - Treat `execution_segment` as the runtime transport payload for pause/continue handoff only. Durable state is the canonical subset persisted as `continuation.bounded_segment` plus the matching execution-lineage event; markdown handoffs are discovery surfaces.
   - Main route: execute tasks using standard flow (step name="execute").
3. After all segments, aggregate files, deviations, decisions, and `contract_updates`; then enter `create_summary`.
</step>

<step name="execute">
Load `execute-plan-validation.md` when the first active task starts. Deviations are normal; classify them through that reference.

1. Read `@context` files named by the plan.
2. Per task:
   - `type="auto"`: execute the derivation/calculation/simulation, verify done criteria including dimensional checks, then load `{GPD_INSTALL_DIR}/references/execution/executor-task-checkpoints.md` and commit through `gpd commit --files`.
   - **Required first-result sanity gate:** At the earliest of first quantitative result, derived core equation, produced artifact, benchmark-style comparison, or two completed auto tasks, stop and ask whether this result is load-bearing, proxy-only, already sanity-checked, still missing decisive evidence, or vulnerable to a disconfirming observation. Load `execute-plan-checkpoints.md` for the full first-result, skeptical re-questioning, and pre-fanout payload protocol.
   - **Checkpoint events:** For `checkpoint:*`, first-result, skeptical, pre-fanout, context-pressure, or supervised post-task stops, load `execute-plan-checkpoints.md`. Emit the checkpoint return with the task result and all intermediate values; spawned children return structured checkpoint state to the orchestrator, which presents the checkpoint and creates any fresh continuation.
   - **Clean-wave batching under dense:** use the predicate in `resolve_execution_bounds` and the full display behavior in `execute-plan-checkpoints.md`.
3. Run `<verification>` checks including physics validation. Emit typed `verification-complete` telemetry; `passed` is valid only when all required checks passed with zero issues.
4. Confirm `<success_criteria>` met.
5. Document deviations in SUMMARY.

Context is finite. After each task, consult `{GPD_INSTALL_DIR}/references/orchestration/context-budget.md`; force a bounded pause before quality degrades or when `MAX_UNATTENDED_MINUTES_PER_PLAN` / `SEGMENT_TASK_CAP` is hit. If pausing mid-plan, commit current work and return checkpoint intent plus the matching `execution_segment`; the orchestrator writes `.continue-here.md` and persists `continuation.bounded_segment` through `gpd apply-return-updates --checkpoint-resume-file`.
</step>

<task_commit>

## Task Commit Protocol

After each completed task, load `{GPD_INSTALL_DIR}/references/execution/executor-task-checkpoints.md` and commit immediately through `gpd commit --files`.

Root-level invariants:

- choose exact task files; never use broad staging such as `git add .` or `git add -A`
- use a plan-scoped subject: `{type}({phase}-{plan}): {description}`
- let `gpd commit` run its blocking pre-commit validation; fix and retry on failure
- record the resulting hash in `TASK_COMMITS` for SUMMARY and crash recovery
- use per-segment `plan-commits-seg-${SEGMENT_NUM}.json` ledgers for Pattern B, then merge them into `plan-commits.json` after all segments complete

On resume (in `detect_previous_attempt`), read the ledger to reconstruct `TASK_COMMITS` and identify already committed tasks.

</task_commit>

<step name="checkpoint_protocol">
See `execute-plan-checkpoints.md` for the full checkpoint protocol (display format, types, resume signals) and `{GPD_INSTALL_DIR}/references/orchestration/checkpoints.md` for general checkpoint details. Spawned children return checkpoint state to the orchestrator; the orchestrator applies the protocol and owns the next-run handoff.
</step>

<step name="verification_failure_gate">
See `execute-plan-validation.md` for physics-specific verification failure handling (dimensional mismatch, limiting case failure, conservation violation). Autonomy changes retry cadence, not correctness: supervised stops immediately; balanced may attempt one local verifiable fix before stopping; yolo may attempt one alternative approach before stopping. If verification still fails, record the issue in SUMMARY and return failure/checkpoint details to the orchestrator.
</step>

<step name="record_completion_time">
```bash
PLAN_END_TIME=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
PLAN_END_EPOCH=$(date +%s)
DURATION_SEC=$(( PLAN_END_EPOCH - PLAN_START_EPOCH ))
```
</step>

<step name="create_summary">
Load the aggregate-and-verify payload only when the plan is ready to write `SUMMARY.md`:

```bash
SUMMARY_INIT=$(gpd --raw init execute-phase "${phase}" --stage aggregate_and_verify)
if [ $? -ne 0 ]; then
  echo "ERROR: staged aggregate-and-verify init failed: $SUMMARY_INIT"
  exit 1
fi
```

Apply `SUMMARY_INIT.staged_loading.field_access_instruction` before reading `SUMMARY_INIT`.

Keep `selected_protocol_bundle_ids`, `protocol_bundle_load_manifest`, `protocol_bundle_context`, and `protocol_bundle_verifier_extensions` visible through summary authoring when the selected bundle added decisive artifact or verifier-extension obligations.

Load `{GPD_INSTALL_DIR}/references/execution/executor-completion.md` and `{GPD_INSTALL_DIR}/templates/summary.md`, then create the canonical summary (`SUMMARY.md` for standalone plans, otherwise `${phase}-${plan}-SUMMARY.md`) at `${phase_dir}/`.

For contract-backed plans, SUMMARY frontmatter must include `plan_contract_ref`, `contract_results`, and `comparison_verdicts`. `contract_results` is authoritative. Immediately before writing frontmatter, re-open `{GPD_INSTALL_DIR}/templates/contract-results-schema.md` and apply it literally. Do not rely on memory or paraphrased summary rules. Before treating the summary as complete, run `gpd validate summary-contract "${SUMMARY_FILE}"` and fix any contract-linkage or verdict-ledger errors.

Autonomy mode (`supervised` / `balanced` / `yolo`) and profile may change cadence or verbosity, but they do NOT relax contract-result emission. `comparison_verdicts` must cover decisive internal/external comparisons that were required or attempted; if the comparison is still open, emit `verdict: inconclusive` or `verdict: tension` instead of omitting the entry.

Follow `executor-completion.md` for substantive title, key results, uncertainty budget, limiting cases, validation events, open questions, final self-check, typed return examples, `gpd apply-return-updates`, and completion commit.
</step>

<step name="update_current_position">
Use `executor-completion.md` as the authority for completion-state effects. Do NOT write `STATE.md`, `state.json`, roadmap, metrics, or continuation files directly when an applicator/helper exists. Return `state_updates` and `contract_updates:` in the `gpd_return` envelope, then apply them through `gpd apply-return-updates "${SUMMARY_FILE}"`.
</step>

<step name="extract_decisions_and_issues">
From SUMMARY, include decisions and blockers in the `gpd_return` envelope. The orchestrator applies them through `gpd apply-return-updates`; do not duplicate this with direct `gpd state ...` commands.
</step>

<step name="update_continuation">
Include completion cleanup in `continuation_update:` so `gpd apply-return-updates` can retire the completed bounded segment and persist the canonical handoff. do not include `recorded_at` or `recorded_by` in child returns. `STATE.md` reflects persisted continuation after application but is not an independent authority.
</step>

<step name="completion_event">
The root workflow does not restate the completion lifecycle. Load `executor-completion.md` and follow it for final self-check, issues handling, applicator error handling, typed return examples, checkpoint-tag cleanup, trace stop, and final commit.

If a SUMMARY exists but a live bounded segment remains, route to resume/execute through the orchestrator instead of marking completion. This workflow does not perform phase closeout; use `execute-phase/closeout.md` for read-only closeout readiness and any phase-complete transition.
</step>

<step name="stop_trace">
Record workflow completion in the local observability stream, then stop the plan-local trace:

```bash
gpd observe event workflow execute-plan.complete --phase "${phase}" --plan "${plan}" 2>/dev/null || true
gpd trace stop 2>/dev/null || true
```
</step>

<step name="offer_next">
Use staged `plans` and `summaries` from the aggregate/finalization payload rather than shelling out to count files.

| Condition | Route | Action |
| --- | --- | --- |
| summaries < plans | More plans | Find next PLAN without SUMMARY. balanced/yolo may continue when no blockers remain; supervised shows next plan + completion summary and ends with `## > Next Up`: primary `gpd:execute-phase {phase}`, plus `gpd:suggest-next`. |
| summaries = plans | Execute-phase closeout | Route back to `gpd:execute-phase {phase}`; that workflow owns phase closeout readiness, verification routing, and downstream next-up rendering. |

All routes start a fresh context window first.
</step>

</process>

<failure_recovery>
When plan execution fails, see `execute-plan-recovery.md` for the full recovery protocol including rollback, partial work preservation, child-return recovery, and RECOVERY.md creation. For physics-specific failure diagnosis (sign errors, convergence failures, numerical instability, dimensional mismatches), use the template at `{GPD_INSTALL_DIR}/templates/recovery-plan.md`.
</failure_recovery>

<success_criteria>

- All tasks from PLAN.md completed or a valid checkpoint return handed back to the orchestrator
- All required verifications pass, including physics validation gates
- Dimensional consistency verified for all quantitative results
- Limiting cases checked where specified
- SUMMARY.md created with substantive content including key results
- Contract-backed plans emit `contract_results` and `comparison_verdicts` when applicable
- Shared state, contract, continuation, roadmap/progress projections, decisions, and issues update only through `gpd_return` / `gpd apply-return-updates` or the owning helper
- Validation events documented
- Checkpoint tag cleaned up on success and retained on failure
</success_criteria>
