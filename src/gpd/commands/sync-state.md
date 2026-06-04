---
name: gpd:sync-state
description: Reconcile diverged STATE.md and state.json after manual edits or corruption
argument-hint: ""
context_mode: project-required
project_reentry_capable: true
command-policy:
  schema_version: 1
  supporting_context_policy:
    project_reentry_mode: current-workspace
allowed-tools:
  - file_read
  - file_write
  - shell
  - find_files
  - search_files
help:
  group: Configuration and maintenance
  order: 690
  compact_description: Repair diverged `STATE.md` and `state.json`
  display_signature: gpd:sync-state
---


<objective>
Reconcile `STATE.md` and `state.json` when they diverge.
</objective>

<execution_context>
@{GPD_INSTALL_DIR}/workflows/sync-state/sync-bootstrap.md
</execution_context>

<process>
Read the included sync-state bootstrap authority first. Later recovery, conflict-analysis, and reconcile stages are manifest-owned.
</process>

<success_criteria>

- [ ] STATE.md and state.json are consistent after sync
- [ ] All conflicts identified and resolved (automatically or interactively)
- [ ] No data lost from either source during reconciliation
- [ ] Both files pass structural validation
      </success_criteria>
