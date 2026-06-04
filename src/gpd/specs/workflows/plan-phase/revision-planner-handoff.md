<purpose>
Spawn and gate the revision planner after the blocked-plan branch has selected a
retry or manual-guided revision path.
</purpose>

<process>

## 12a. Event: revision_planner_handoff

Use this event only from `blocked_plan_revision_branch` after blocked plan IDs
are reconciled and any required user choice has selected retry/manual-guided
revision.

Revision prompt:

Load the `revision_template_rendering` conditional authority pack first. Use
`templates/planner-subagent-prompt.md` here as the stage-local planner template
and render its `## Revision Template` section.

```markdown
Render the template's `## Revision Template` into `revision_prompt` with fresh
blocked-plan content, checker issues, and these staged bindings. Do not add
unselected body fields.

- `{phase_number}` -> {phase_number}
- `{plans_content}` -> {plans_content}
- `{structured_issues_from_checker}` -> {structured_issues_from_checker}
- `{project_contract}` -> {project_contract}
- `{project_contract_gate}` -> {project_contract_gate}
- `{project_contract_load_info}` -> {project_contract_load_info}
- `{project_contract_validation}` -> {project_contract_validation}
- `{contract_intake}` -> {contract_intake}
- `{effective_reference_intake}` -> {effective_reference_intake}
- `{selected_protocol_bundle_ids}` -> {selected_protocol_bundle_ids}
- `{protocol_bundle_load_manifest}` -> {protocol_bundle_load_manifest}
- `{protocol_bundle_verifier_extensions}` -> {protocol_bundle_verifier_extensions}
- `{reference_artifact_files}` -> {reference_artifact_files}
- `{literature_review_files}` -> {literature_review_files}
- `{research_map_reference_files}` -> {research_map_reference_files}
If the revised fix plan still needs specialized tooling or other
machine-checkable hard requirements, keep them in PLAN frontmatter
`tool_requirements`.
Treat `effective_reference_intake` as the structured source of carry-forward
anchors; read reference paths by handle only for targeted checker fixes.

Keep the revision prompt scoped to targeted checker fixes. Do not restate
template-owned revision policy here.
```

```
PLANNER_HANDOFF_STARTED_AT=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
PLANNER_RETURN=$(
task(
  prompt="First, read {GPD_AGENTS_DIR}/gpd-planner.md for your role and instructions.\n\n" + revision_prompt + "\n\n<spawn_contract>\nwrite_scope:\n  mode: scoped_write\n  allowed_paths:\n    - \"{phase_dir}/*-PLAN.md\"\nexpected_artifacts:\n  - \"revised readable {phase_dir}/*-PLAN.md named in gpd_return.files_written\"\nshared_state_policy: return_only\n</spawn_contract>",
  subagent_type="gpd-planner",
  model="{planner_model}",
  readonly=false,
  description="Revise Phase {phase} plans"
)
)
```

Run this `child_gate`; shared gate and continuation rules live in
`references/orchestration/child-artifact-gate.md` and
`references/orchestration/continuation-boundary.md`.

```yaml
child_gate:
  id: "planner_revision"
  role: "gpd-planner"
  return_profile: "planner"
  required_status: "completed"
  expected_artifacts:
    - path: "${PHASE_DIR}/*-PLAN.md"
      kind: "glob"
  allowed_roots:
    - "${PHASE_DIR}"
  freshness_marker: "after $PLANNER_HANDOFF_STARTED_AT"
  validators:
    - "gpd validate handoff-artifacts - --expected-glob '${PHASE_DIR}/*-PLAN.md' --allowed-root '${PHASE_DIR}' --required-suffix=-PLAN.md --require-files-written --require-status completed --fresh-after \"$PLANNER_HANDOFF_STARTED_AT\""
    - "gpd validate plan-contract <each fresh plan>"
    - "gpd validate plan-preflight <each fresh plan>"
  applicator: none
  failure_route: "retry_revision_planner_or_manual_revision_or_force_decision | repair_prompt_once | fail_closed | retry_once | repair_path_once | recheck_or_manual_decision"
  status_route:
    checkpoint: "fresh revision-planner continuation after user response"
    blocked: "retry, manual revision, or force decision"
    failed: "retry, manual revision, or force decision"
```

Non-completed: use `status_route`.

**If the revision planner agent fails to spawn or returns an error:** Do not
proceed to re-check just because revised `PLAN.md` files exist on disk. Treat
them as incomplete until `planner_revision` passes. If no accepted revision
return is available, keep the loop fail-closed and offer: 1) Retry revision
planner, 2) Apply revisions manually in the main context using checker
feedback, 3) Force proceed with current plans despite checker issues.

After planner returns, update `FRESH_PLAN_FILES` only from the accepted
`planner_revision` return, increment `iteration_count`, and return to
`checker_handoff`. If revising from PARTIAL APPROVAL, only pass the revised
plans, not already-approved plans, to the checker.

</process>
