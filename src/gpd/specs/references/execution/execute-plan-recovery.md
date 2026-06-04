# Execute-Plan: Failure Recovery

Referenced by `{GPD_INSTALL_DIR}/workflows/execute-plan.md`. Governs recovery when plan execution fails.

**Recovery template:** For physics-specific root cause analysis (sign errors, convergence failures, numerical instability, dimensional mismatches, unphysical results), use the detailed template at `{GPD_INSTALL_DIR}/templates/recovery-plan.md`. It provides structured diagnosis, rollback options, retry strategies, and prevention checklists beyond the minimal recovery document below.

## Plan Failure Recovery

When plan execution fails (task error, unrecoverable validation failure, agent crash), this section governs recovery.

**Trigger:** Any task fails and cannot be auto-fixed by deviation rules 1-3, OR the executor agent crashes/times out, OR a physics validation gate halts execution permanently.

### Diagnose Failure

Determine which tasks completed and which failed:

```bash
# Candidate completed tasks: commits after the checkpoint are partial evidence
COMPLETED=$(git log --oneline "${CHECKPOINT_TAG}"..HEAD --grep="(${PHASE}-${PLAN}):")
FAILED_TASK="${CURRENT_TASK_NUM}: ${CURRENT_TASK_NAME}"
REMAINING_TASKS="${TASKS_AFTER_FAILED}"
```

Classify completion only after expected artifacts exist, the required `gpd_return` envelope validates, and any required `gpd apply-return-updates` pass has succeeded. Commits/files are partial-work evidence, not success proof.

## Child Handoff Recovery

Apply this when a Pattern A, B, or D executor child fails to spawn, crashes, times out, or returns without a valid envelope.

**Pattern A full-plan child gate:** require a fresh summary, declared deliverables, valid child `gpd_return`, non-failing self-check/validation markers, and `gpd apply-return-updates` for durable updates. `git log --oneline -3` is only partial evidence. If the return envelope is missing or invalid, keep the child handoff incomplete and offer: 1) retry executor, 2) Pattern C main-context execution with its own return, 3) abort. Mark tracking failed with details.

**Pattern B/D segment child gate:** require fresh segment outputs, aggregator summary, valid typed return data, aggregator gate, non-failing self-check/validation markers, and final-summary return updates. Treat output files as partial evidence. If the envelope is missing or invalid, retry or use explicit main-context fallback; otherwise offer skip/continue as an incomplete segment. Record the failure in agent tracking.

Present failure report:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 GPD > PLAN EXECUTION FAILED
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

**Plan:** {PHASE}-{PLAN} ({plan name})
**Checkpoint:** ${CHECKPOINT_TAG}

### Completed Tasks (validated)
{list of tasks whose commits, artifacts, return envelope, and applicator gate all passed}

### Partial Evidence (not yet success)
{list of commits or files that exist but still lack a valid return/artifact/applicator gate}

### Failed Task
**Task {N}: {name}**
Reason: {error description, validation failure details, or agent crash info}

### Remaining Tasks (not started)
{list of tasks that were never attempted}

──────────────────────────────────────────────────────
Options:
  1. "Rollback" -- revert all work to checkpoint, single clean undo commit
  2. "Keep partial" -- preserve completed tasks, document failure for recovery
──────────────────────────────────────────────────────
```

### Rollback to Checkpoint

**If user chooses rollback:**

Revert all commits between the checkpoint and HEAD using a single clean revert:

```bash
# Get the commit hash at the checkpoint tag
CHECKPOINT_COMMIT=$(git rev-list -n 1 "${CHECKPOINT_TAG}")

# Revert all changes since checkpoint (staged but not committed)
git revert --no-commit HEAD...${CHECKPOINT_COMMIT}

# Single rollback commit with descriptive message
git commit -m "$(cat <<EOF
revert: rollback failed plan ${PHASE}-${PLAN}

Plan failed at task ${FAILED_TASK}.
Rolled back to checkpoint: ${CHECKPOINT_TAG}
Reason: ${FAILURE_REASON}
EOF
)"
```

Update STATE.md to reflect the rollback:

```bash
gpd state add-decision \
  --phase "${PHASE}" --summary "Rolled back plan ${PHASE}-${PLAN}" \
  --rationale "${FAILURE_REASON}"
```

**Keep the checkpoint tag** -- it documents the rollback point for audit purposes.

Report:

```
Rollback complete. Repository restored to pre-plan state.
Checkpoint tag preserved: ${CHECKPOINT_TAG}

Next steps:
- gpd:execute-phase {phase} -- retry (will detect no prior commits)
- Review plan for issues before retrying
```

### Keep Partial Work

**If user chooses to keep partial work:**

1. **Create recovery document:**

```bash
RECOVERY_FILE="GPD/phases/${PHASE_DIR}/RECOVERY-${PLAN}.md"
```

Write `RECOVERY-{PLAN}.md` with:

```markdown
---
phase: { PHASE }
plan: { PLAN }
failed_at: { FAILED_TASK_NUM }
failed_task: { FAILED_TASK_NAME }
failure_reason: { reason }
checkpoint_tag: { CHECKPOINT_TAG }
completed_tasks: [{ list of completed task numbers }]
remaining_tasks: [{ list of remaining task numbers }]
created: { ISO timestamp }
---

# Recovery: Plan {PHASE}-{PLAN}

## Failure Context

**Task {N}: {name}** failed because:
{detailed failure description}

## Completed Work

| Task | Commit | Description |
| ---- | ------ | ----------- |

{rows for each completed task}

Do not list a task here merely because commits/files exist. If the return was missing or invalid, record partial evidence under Failure Context or Remaining Work and require retry or explicit main-context fallback.

## Remaining Work

{list of tasks not yet attempted, with their objectives from PLAN.md}

## Recovery Options

1. Fix the failing task and resume from task {N}
2. Revise the plan to work around the failure
3. Rollback: `git revert --no-commit HEAD...$(git rev-list -n 1 {CHECKPOINT_TAG})` then commit
```

2. **Update STATE.md** with failure context:

```bash
gpd state add-blocker --text \
  "Plan ${PHASE}-${PLAN} failed at task ${FAILED_TASK_NUM}: ${FAILURE_REASON}"

gpd state record-session \
  --stopped-at "Plan ${PHASE}-${PLAN} FAILED at task ${FAILED_TASK_NUM}" \
  --resume-file "${RECOVERY_FILE}"
```

3. **Commit the recovery document:**

```bash
gpd commit \
  "docs(${PHASE}-${PLAN}): document plan failure and recovery options" \
  --files "${RECOVERY_FILE}" GPD/STATE.md
```

**Keep the checkpoint tag** -- needed if user later decides to rollback.

Report:

```
Partial work preserved. Recovery document created.

Recovery: ${RECOVERY_FILE}
Checkpoint: ${CHECKPOINT_TAG} (for future rollback if needed)

Next steps:
- gpd:execute-phase {phase} -- will detect partial completion, offer resume
- Review ${RECOVERY_FILE} for recovery options
```
