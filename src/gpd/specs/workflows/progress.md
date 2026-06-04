<purpose>
Check research progress, summarize recent work and what lies ahead, then show the code-owned suggested next action. Provides situational awareness before continuing research.
</purpose>

<required_reading>
Read all files referenced by the invoking prompt's execution_context before starting.
</required_reading>

<process>

<step name="mode_detection">
## Mode Detection

Check if `$ARGUMENTS` contains `--brief`, `--full`, or `--reconcile`.

**If --brief:**
Show compact 3-line status:
```
Phase {N} of {M} ({phase_name}) | Plan {X} of {Y} | [{progress_bar}] {percent}%
Last: {last_summary_one_liner}
>> Next: {recommended_next_command}
```
STOP here. Do not show full report.

**If --reconcile:**
Go to `reconcile_state` step.

**Default (no flag) or --full:**
Continue to full report below. With `--full`, also include detailed per-phase artifact listings.
</step>

<step name="reconcile_state">
## Reconcile Mode

When STATE.md appears out of sync with disk reality (e.g., a plan was completed but state not updated, or a phase was manually modified), reconcile by comparing disk artifacts against STATE.md.

```bash
# Get the structured current position from the state snapshot instead of scraping STATE.md with regexes
STATE_JSON=$(gpd --raw state snapshot)
STATE_PHASE=$(echo "$STATE_JSON" | gpd json get .current_phase --default "")
STATE_PLAN=$(echo "$STATE_JSON" | gpd json get .current_plan --default "")

# Count actual disk state from the canonical roadmap inventory
ROADMAP=$(gpd --raw roadmap analyze)
echo "$ROADMAP" | gpd json get .phases --default "[]"
```

**If discrepancies found between STATE.md and disk:**

```
## State Reconciliation

| Source | Phase | Plan | Status |
|--------|-------|------|--------|
| STATE.md | {X} | {Y} | {claimed_status} |
| Disk | {X} | {Z} | {actual_status} |

Discrepancy: STATE.md says plan {Y} is current, but disk shows {Z} plans complete.

Options:
1. "Sync STATE.md to disk" (Recommended) — update STATE.md to match actual artifacts
2. "Keep STATE.md" — trust the state file, investigate missing artifacts
3. "Show details" — list all mismatches before deciding
```

If user chooses sync: update STATE.md position, progress bar, and plan counters to match disk reality using `gpd state` commands.

Confirmation contract: before any command that writes reconciled state, ask for an explicit user decision. If `ask_user` is available, present the three options above with `Sync STATE.md to disk` as the recommended option. If `ask_user` is not available, require a typed reply that exactly matches one of `Sync STATE.md to disk`, `Keep STATE.md`, or `Show details`; do not infer consent from a vague acknowledgement.

**If no discrepancies:** Report "STATE.md is consistent with disk artifacts." and continue to full report.
</step>

<step name="init_context">
**Load progress context (with file contents to avoid redundant reads):**

```bash
INIT=$(gpd --raw init progress --include state,roadmap,project,config,references)
if [ $? -ne 0 ]; then
  echo "ERROR: gpd initialization failed: $INIT"
  # STOP; surface the error.
fi
```

Extract from init JSON: `project_exists`, `roadmap_exists`, `state_exists`, `phases`, `current_phase`, `next_phase`, `milestone_version`, `completed_count`, `phase_count`, `paused_at`, `autonomy`, `research_mode`, `project_contract`, `project_contract_gate`, `project_contract_validation`, `project_contract_load_info`, `contract_intake`, `effective_reference_intake`, `active_reference_context`, `reference_artifacts_content`, `knowledge_doc_files`, `knowledge_doc_count`, `stable_knowledge_doc_files`, `stable_knowledge_doc_count`, `knowledge_doc_status_counts`, `derived_knowledge_docs`, `derived_knowledge_doc_count`, `knowledge_doc_warnings`, `derived_convention_lock`, `derived_convention_lock_count`, `derived_intermediate_results`, `derived_intermediate_result_count`, `derived_approximations`, `derived_approximation_count`.

`phases`, `current_phase`, `next_phase`, `completed_count`, and `phase_count` are derived from the same canonical roadmap inventory used by `gpd --raw roadmap analyze`, including roadmap phases whose directories do not exist yet. Do not rescan only `GPD/phases/` to override them.

**File contents (from --include):** `state_content`, `roadmap_content`, `project_content`, `config_content`. These are null if files don't exist.

If missing STATE.md: suggest `gpd:new-project`.

**If ROADMAP.md missing but PROJECT.md exists:**

This means a milestone was completed and archived. Report that state, then let
the `route` step use `gpd --raw suggest` for the next command.

If missing both ROADMAP.md and PROJECT.md: suggest `gpd:new-project`.
</step>

<step name="load">
**Use project context from INIT:**

All file contents are already loaded via `--include` in init_context step:

- `state_content` — living memory (position, decisions, issues)
- `roadmap_content` — phase structure and objectives
- `project_content` — current state (Research Question, Framework, Answered Questions)
- `config_content` — settings (model_profile, workflow toggles)
- `project_contract` — machine-readable scoping and anchor contract, authoritative only when `project_contract_gate.authoritative` is true
- `project_contract_load_info` — structured load status, warnings, and blockers for the contract
- `project_contract_validation` — contract approval gate for authoritative use
- `effective_reference_intake` — structured carry-forward ledger for refs, baselines, prior outputs, and context gaps
- `active_reference_context` / `reference_artifacts_content` — readable anchor context to explain the next-step recommendation
- `knowledge_doc_files` / `knowledge_doc_count` — inventory-visible knowledge docs loaded from `GPD/knowledge/`
- `stable_knowledge_doc_files` / `stable_knowledge_doc_count` — reviewed docs that are runtime-active for shared reference context
- `knowledge_doc_status_counts` — lifecycle mix across `draft`, `in_review`, `stable`, and `superseded`
- `derived_knowledge_docs` / `derived_knowledge_doc_count` — stable runtime-active docs surfaced for this run
- `knowledge_doc_warnings` — parse/read problems forwarded from knowledge discovery

No additional file reads needed.

Run centralized context preflight before continuing:

```bash
CONTEXT=$(gpd --raw validate command-context progress "$ARGUMENTS")
if [ $? -ne 0 ]; then
  echo "$CONTEXT"
  exit 1
fi
```
</step>

<step name="analyze_roadmap">
**Get comprehensive roadmap analysis (replaces manual parsing):**

```bash
ROADMAP=$(gpd --raw roadmap analyze)
```

This returns structured JSON with:

- All phases with disk status (complete/partial/planned/empty/no_directory)
- Goal and dependencies per phase
- Plan and summary counts per phase
- Aggregated stats: total plans, summaries, progress percent
- Current and next phase identification

Use this instead of manually reading/parsing ROADMAP.md.
</step>

<step name="recent">
**Gather recent work context:**

- Find the 2-3 most recent summary artifacts (`SUMMARY.md` and `*-SUMMARY.md`)
- Count standalone and numbered phase artifacts with these canonical forms:
  `GPD/phases/[current-phase-dir]/PLAN.md`,
  `GPD/phases/[current-phase-dir]/*-PLAN.md`,
  `GPD/phases/[current-phase-dir]/SUMMARY.md`, and
  `GPD/phases/[current-phase-dir]/*-SUMMARY.md`.
- Pair standalone `PLAN.md` with standalone `SUMMARY.md`, and numbered
  `*-PLAN.md` with matching `*-SUMMARY.md`:
  ```bash
  for plan in GPD/phases/[current-phase-dir]/PLAN.md GPD/phases/[current-phase-dir]/*-PLAN.md; do
    SUMMARY="$(dirname "$plan")/SUMMARY.md"
  done
  ```
- Use `summary-extract` for efficient parsing:
  ```bash
  gpd --raw summary-extract <path> --field one_liner | gpd json get .one_liner --default ""
  ```
- This shows "what we've been working on"
  </step>

<step name="position">
**Parse current position from init context and roadmap analysis:**

- Use `current_phase` and `next_phase` from roadmap analyze
- Use phase-level `has_context` and `has_research` flags from analyze
- Note `paused_at` if work was paused (from init context)
- Count pending items: use `gpd --raw init todos`
- Check for active debug sessions: `ls GPD/debug/*.md 2>/dev/null | grep -v resolved | wc -l`
- Surface validation/diagnostic state with this scan:
  `grep -l -E "^(status: (gaps_found|human_needed|expert_needed)|session_status: diagnosed)$"`
- Treat `` `session_status: diagnosed` `` as a diagnostic artifact state; if
  `HEALTH.summary.warn > 0` or `HEALTH.summary.fail > 0`, report the failing
  checks without mutating project state. Verification artifacts include
  `GPD/phases/[current-phase-dir]/*-VERIFICATION.md`.
- Check state compaction health; capture non-fatally because `gpd --raw health` can exit 1 while still printing parseable JSON:
  ```bash
  HEALTH_JSON=$(gpd --raw health 2>/dev/null || true)
  ```
  If `HEALTH_JSON` parses, inspect the `State Compaction` check. If its status is `warn`, STATE.md is growing large. Report only; do not run raw state compaction from `gpd:progress`.
  </step>

<step name="report">
**Generate progress bar from gpd CLI, then present rich status report:**

```bash
PROGRESS_BAR=$(gpd --raw progress bar)

# Structured progress with live_execution and execution-preference flags.
PROGRESS_JSON=$(gpd --raw progress)
```

Present:

```
# [Research Project Name]

**Progress:** {PROGRESS_BAR}
**Profile:** [deep-theory/numerical/exploratory/review/paper-writing]
**Execution preferences:** strict_wait={strict_wait} | never_interrupt_workers={never_interrupt_running_workers} | never_auto_close_children={never_auto_close_child_agents}

## Live Execution
(Only show this block when PROGRESS_JSON.live_execution.phase is set.)

Active phase/plan: Phase {live_execution.phase}, Plan {live_execution.plan} (wave {live_execution.wave})
Current task: {live_execution.current_task} ({live_execution.current_task_index}/{live_execution.current_task_total})
Last artifact: {live_execution.last_artifact_path}
Last result:   {live_execution.last_result_label}
Updated:       {live_execution.last_updated_age_label}
Status:        {live_execution.segment_status}{ if live_execution.waiting_reason }, waiting: {live_execution.waiting_reason}{ endif }

## Recent Work
- [Phase X, Plan Y]: [what was accomplished - 1 line from summary-extract]
- [Phase X, Plan Z]: [what was accomplished - 1 line from summary-extract]

## Current Position
Phase [N] of [total]: [phase-name]
Plan [M] of [phase-total]: [status]
CONTEXT: [present if has_context | - if not]

## Key Results Established
- [result 1 from STATE.md — e.g., "Spectral gap scales as Delta ~ 1/N^2 (Phase 2)"]
- [result 2]

## Key Decisions Made
- [decision 1 from STATE.md — e.g., "Using dimensional regularization with MS-bar scheme"]
- [decision 2]

## Blockers/Concerns
- [any blockers or concerns from STATE.md — e.g., "Series diverges for g > 2, need resummation"]

## Pending Items
- [count] pending — gpd:check-todos to review

## Active Derivation Sessions
- [count] active — gpd:debug to continue
(Only show this section if count > 0)

## What's Next
[Next phase/plan objective from roadmap analyze]

## Knowledge Status
Inventory-visible knowledge docs: {knowledge_doc_count}
Runtime-active knowledge docs: {stable_knowledge_doc_count}
Lifecycle mix: {knowledge_doc_status_counts}
Runtime-active knowledge surfaced in this run: {derived_knowledge_doc_count}
Warnings: {knowledge_doc_warnings}
```

If STATE.md exceeds 1500 lines, append after the report:

```
STATE.md is large (N lines). Consider running `gpd:compact-state` to archive historical entries.
```

If the read-only health report's `State Compaction` check has status `warn`, append:

```
STATE.md is approaching compaction threshold (N lines). `gpd:progress` did not modify it; use `gpd:compact-state` when you want to archive historical entries.
```

**Deep diagnostics (--full mode only):** Run the health dashboard for comprehensive system checks:

```bash
HEALTH=$(gpd --raw health 2>/dev/null || true)
```

Do not stop just because raw health returned nonzero; if `HEALTH` contains parseable JSON, use that JSON.

If `HEALTH.summary.warn > 0` or `HEALTH.summary.fail > 0`, append a summary:

```
## System Health
{warn_count} warning(s), {fail_count} failure(s) detected. Run `gpd:health --fix` to auto-repair what it can.
```

</step>

<step name="route">
**Determine next action from the code-owned suggestion route.**

Keep the report above as situational awareness. Do not rescan plans,
summaries, verification files, context files, milestone status, or roadmap
phase counts to choose the next command; those route branches are owned by
lifecycle/suggest code.

```bash
SUGGEST=$(gpd --raw suggest)
```

Use the first suggestion's typed `next_command` / lifecycle route payload when
present. If the payload includes rendered next-up markdown, emit that exact
`## > Next Up` block and its matching stage-stop projection. Otherwise render a
single primary from the typed public runtime command and include only typed
runtime secondaries. Do not show raw helper commands as public next-up commands.

If `gpd --raw suggest` returns no actionable route, end with the situational
report and a conservative `gpd:suggest-next` next-up block. Do not choose
`gpd:discuss-phase` versus `gpd:plan-phase`, gap planning versus gap execution,
phase closeout, milestone completion, or new-milestone routing in this prompt.

</step>

<step name="edge_cases">
**Handle edge cases:**

- Phase complete but next phase not planned -> highlight it; let `gpd --raw suggest` choose the route
- All work complete -> highlight it; let lifecycle/suggest choose milestone routing
- Blockers present -> highlight before showing the code-owned next route
- Handoff file exists -> mention it; let lifecycle/suggest choose resume routing
- Derivation session active -> mention it; let lifecycle/suggest choose debug or resume routing
  </step>

</process>

<success_criteria>

- [ ] Rich context provided (recent work, key results, decisions, issues)
- [ ] Current position clear with visual progress
- [ ] What's next clearly explained
- [ ] Smart routing delegated to the code-owned suggestion/lifecycle payload
- [ ] User confirms before any action
- [ ] Seamless handoff to appropriate gpd command

</success_criteria>
