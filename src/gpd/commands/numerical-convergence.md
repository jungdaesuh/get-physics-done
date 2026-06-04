---
name: gpd:numerical-convergence
description: Systematic convergence testing for numerical physics computations
argument-hint: "[phase number or file path]"
context_mode: project-aware
command-policy:
  schema_version: 1
  subject_policy:
    explicit_input_kinds:
      - phase number or file path
  supporting_context_policy:
    project_context_mode: project-aware
    project_reentry_mode: disallowed
    optional_file_patterns:
      - GPD/STATE.md
      - GPD/ROADMAP.md
      - GPD/research-map/VALIDATION.md
      - GPD/analysis/*.md
  output_policy:
    output_mode: managed
    managed_root_kind: gpd_managed_durable
    default_output_subtree: GPD/analysis
    stage_artifact_policy: gpd_owned_outputs_only
allowed-tools:
  - file_read
  - file_write
  - file_edit
  - shell
  - search_files
  - find_files
  - ask_user
help:
  group: Validation and analysis
  order: 330
  compact_description: Run convergence checks for a project phase or one explicit current-workspace artifact
  display_signature: gpd:numerical-convergence
  examples:
    - gpd:numerical-convergence results/mesh-study.csv
  notes:
    - Part of the project-aware technical-analysis lane for explicit current-workspace convergence checks.
  root_detail_order: 160
---


<objective>
Route a numerical-convergence request into the workflow-owned validation flow.

Keep standalone/current-workspace durable outputs under `GPD/analysis/` rooted at the invoking workspace. Only authoritative phase-backed runs may write phase-local reports. Standalone/current-workspace runs stop after writing the analysis artifact, do not mutate `STATE.md` or `state.json`, and do not assume a standalone commit step.
</objective>

<execution_context>
@{GPD_INSTALL_DIR}/workflows/numerical-convergence.md
</execution_context>

<context>
Target: $ARGUMENTS

Interpretation:

- If a number: test convergence for that current-workspace phase only when authoritative phase context exists
- If a file path: test convergence for computations in that file
- If empty in current-workspace project mode: ask one focused question to identify the phase or file target
- If empty outside a project: command-context validation rejects the request; require an explicit phase number or file path
- Phase-local reports are honest only when authoritative phase context exists in the current workspace. Otherwise write the durable artifact under `GPD/analysis/numerical-{slug}.md`

</context>

<process>
## 0. Validate Context

```bash
CONTEXT=$(gpd --raw validate command-context numerical-convergence "$ARGUMENTS")
if [ $? -ne 0 ]; then
  echo "$CONTEXT"
  exit 1
fi
```

Execute the included numerical-convergence workflow end-to-end.
The workflow owns target resolution, decisive checks, report content, and the
phase-backed vs standalone/current-workspace persistence split.
</process>

<success_criteria>

- [ ] Numerical target resolved from the explicit request or authoritative current-workspace phase context
- [ ] Convergence study design and grading recorded for each computation tested
- [ ] Output path is phase-local only when authoritative phase context exists
- [ ] Standalone/current-workspace runs write only under `GPD/analysis/` and do not mutate project state
- [ ] Final report contains enough detail to reproduce the convergence study

</success_criteria>
