<purpose>
Aggregate completed execution results and route only aggregation-owned follow-up artifacts.
</purpose>

<stage_boundary>
This stage owns result aggregation only: summary context budgeting, one-line summary extraction when needed, the phase execution summary, figure inventory detection, experimental/observational comparison detection, and recovery-report routing for failures, skips, or rollbacks.

This stage does not spawn verifiers or consistency checkers, route verification status, close verification gaps, spawn debuggers, re-verify gap closures, or decide final closeout. Those responsibilities belong to the verification/consistency/closeout stages after aggregation.
</stage_boundary>

<process>

<step name="refresh_aggregation_context">
Refresh the stage payload before reading aggregation fields:

```bash
AGGREGATE_VERIFY_INIT=$(gpd --raw init execute-phase "${PHASE_ARG}" --stage aggregate_and_verify)
if [ $? -ne 0 ] || [ -z "$AGGREGATE_VERIFY_INIT" ]; then
  echo "ERROR: aggregate-and-verify stage refresh failed: $AGGREGATE_VERIFY_INIT"
  exit 1
fi
```

Apply `AGGREGATE_VERIFY_INIT.staged_loading.field_access_instruction` before reading `AGGREGATE_VERIFY_INIT`. Do not rely on fields that belong to verifier handoff, verifier report finalization, gap re-verification, or consistency checking.
</step>

<step name="summary_context_budget">
Before reading full summaries, count candidate `*-SUMMARY.md` files for the phase and estimate their context impact with the compact heuristic below:

- prefer one-line extraction when there are more than 12 summaries;
- prefer one-line extraction when estimated summary text would exceed 15% of the current context window;
- otherwise read summary bodies needed for aggregation and artifact validation.

When the threshold is crossed, use `gpd summary-extract --field one_liner` for each summary instead of loading full summary bodies; this is the summary-extract for one-liners path. Load `references/orchestration/context-budget.md` only when the compact heuristic is insufficient or the estimate is disputed.
</step>

<step name="false_success_guard">
Before classifying a plan or wave as complete, reopen the child-listed artifacts and the current plan summary. A stale summary, a failed spot-check, a failed child gate, or a missing required artifact is not evidence of success.

Classify every questionable result as one of:

- `missing`: the promised summary or required artifact is absent;
- `stale`: the summary or artifact predates the accepted child return or checkpoint;
- `malformed`: the file exists but does not satisfy the expected contract;
- `unsurfaced`: the artifact exists but was not listed or linked from the child summary.

Only aggregate a plan as successful after its current summary, child gate outcome, required artifacts, and spot-check record agree.
</step>

<step name="phase_execution_summary">
Build the phase execution summary from accepted plan summaries, phase index data, and the orchestrator-maintained outcome records.

```markdown
## Phase {X}: {Name} Execution Aggregated

**Waves:** {N} | **Plans:** {completed}/{total} accepted

| Wave | Plans | Aggregation Status |
| ---- | ----- | ------------------ |
| 1 | plan-01, plan-02 | accepted |
| 2 | plan-03 | needs recovery |

### Plan Details

1. **03-01**: [one-liner from current SUMMARY.md]
2. **03-02**: [one-liner from current SUMMARY.md]

### Result Rollup

[Aggregate durable outputs, limiting-case checks, dimensional checks, cross-checks, uncertainty propagation, and known approximations surfaced by accepted summaries.]

### Issues Encountered

[Aggregate failed, skipped, rolled-back, stale, malformed, missing, or unsurfaced results, or "None".]
```

This summary is an aggregation artifact. It does not assert phase success, verification success, or closeout readiness.
</step>

<step name="figure_inventory_detection">
Detect generated figures by scanning accepted summary key-files and durable workspace figure roots for `*.pdf`, `*.png`, `*.eps`, `*.svg`, `*.jpg`, `*.jpeg`, or `*.tif`/`*.tiff`.

Durable figure roots are `artifacts/phases/${phase_number}-${phase_slug}/`, `figures/`, or `paper/figures/`. Generated figures and plots should live in stable workspace roots. Do not treat `GPD/phases/**` as a durable figure root.

If figures exist, route to the figure inventory template path `{GPD_INSTALL_DIR}/templates/paper/figure-tracker.md` and append or create `paper/FIGURE_TRACKER.md` with source phase, source/data files, status, and update date. If no figures exist, do not load the template and skip the inventory silently.
</step>

<step name="experimental_comparison_detection">
Detect whether accepted results compare theory against experimental or observational data.

Positive signals include accepted summaries or contract results that mention experimental data, observational data, benchmark measurements, fitted observables, detector/survey data, lab data, or explicit comparison plots/tables against measured quantities.

When prior decisive `contract_results` and decisive `comparison_verdicts` exist, preserve the explicit approach lock unless new evidence invalidates it.

If such a comparison exists, route to `{GPD_INSTALL_DIR}/templates/paper/experimental-comparison.md` and create or update `paper/EXPERIMENTAL_COMPARISON.md`. If no comparison exists, do not load the template and skip the artifact silently.
</step>

<step name="publication_artifact_context">
For paper-writing or manuscript-facing phases, resolve the publication manuscript root through the publication preflight surfaces before suggesting any LaTeX compile smoke check. Use `MANUSCRIPT_ROOT` and the manifest-recorded TeX entrypoint for `latex_compile`; never assume `paper/` as the current directory.
</step>

<step name="recovery_report_routing">
Build recovery outcome lists from the phase index, current summaries, child gate results, spot-check results, and the orchestrator's maintained failed/skipped/rolled-back records. Track succeeded, failed, skipped, and rolled-back plan IDs with reasons.

If there are no failures, skips, rollbacks, stale summaries, failed spot-checks, failed child gates, or missing required artifacts, do not load the recovery template and pass the aggregation state to the next stage.

If any recovery condition exists, route to `{GPD_INSTALL_DIR}/templates/recovery-plan.md` and write a phase recovery report:

```bash
RECOVERY_FILE="${phase_dir}/PHASE-RECOVERY.md"
```

The recovery report includes frontmatter for phase, timestamp, succeeded, failed, skipped, rolled_back, stale, malformed, missing, and unsurfaced entries. Include links to current summaries and plan-level recovery files when present.

Offer aggregation-owned recovery routes only:

- isolated failed or stale plan: `gpd:execute-phase {X}`;
- gap-shaped remaining work: `gpd:plan-phase {X} --gaps`;
- unclear or systemic execution failure: `gpd:discuss-phase {X}`;
- non-critical skipped downstream work: `gpd:plan-phase {X+1}`.

Do not mark the phase complete from this report. Recovery routing is evidence for the later verification and closeout stages, not a substitute for them.
</step>

</process>
