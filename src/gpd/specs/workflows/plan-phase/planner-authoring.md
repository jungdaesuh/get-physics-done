<purpose>
Author phase plans through the staged planner handoff and planner artifact gate.
</purpose>

<stage_boundary>
Third-stage authority: existing-plan handling, planner prompt assembly, planner child return handling, roadmap-update consumption, fresh-plan validation, and planner checkpoint handling. Do not load checker/revision authority here until the planner gate completes.
</stage_boundary>

<process>

## 6. Check Existing Plans

```bash
ls "${PHASE_DIR}"/*-PLAN.md 2>/dev/null
```

**If exists:** Offer: 1) Add more plans, 2) View existing, 3) Replan from scratch.

## 7. Use Context Files from INIT

Refresh the stage-local planning payload now that research routing is complete:

```bash
INIT=$(gpd --raw init plan-phase "$PHASE" --stage planner_authoring)
if [ $? -ne 0 ]; then
  echo "ERROR: staged plan-phase init failed: $INIT"
  exit 1
fi
# Apply INIT.staged_loading.field_access_instruction before using this payload.
```

## 8. Spawn gpd-planner Agent

Display banner:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 GPD > PLANNING PHASE {X}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

* Spawning planner...
```

Planner prompt:

Use `templates/planner-subagent-prompt.md` here as the stage-local planner template and render its `## Standard Planning Template` section.

```markdown
Render the template's `## Standard Planning Template` into `filled_prompt` with these bindings:

- `{phase_number}` -> {phase_number}
- `{standard | gap_closure}` -> `standard` unless this is explicit gap-closure planning
- `{full | light}` -> `light` only when `--light`; otherwise `full`
- `{research_mode}` -> {RESEARCH_MODE}
- `{autonomy}` -> {AUTONOMY}
- `{state_content}` -> {state_content}
- `{project_contract}` -> {project_contract}
- `{project_contract_gate}` -> {project_contract_gate}
- `{project_contract_load_info}` -> {project_contract_load_info}
- `{project_contract_validation}` -> {project_contract_validation}
- `{contract_intake}` -> {contract_intake}
- `{effective_reference_intake}` -> {effective_reference_intake}
- `{roadmap_content}` -> {roadmap_content}
- `{requirements_content}` -> {requirements_content}
- `{selected_protocol_bundle_ids}` -> {selected_protocol_bundle_ids}
- `{protocol_bundle_load_manifest}` -> {protocol_bundle_load_manifest}
- `{protocol_bundle_verifier_extensions}` -> {protocol_bundle_verifier_extensions}
- `{active_reference_context}` -> {active_reference_context}
- `{reference_artifact_files}` -> {reference_artifact_files}
- `{literature_review_files}` -> {literature_review_files}
- `{research_map_reference_files}` -> {research_map_reference_files}
- `{context_content}` -> {context_content}
- `{research_content}` -> {research_content}
- `{experiment_design_content}` -> {experiment_design_content}
- `{verification_content}` -> {verification_content}
- `{validation_content}` -> {validation_content}
Keep `{contract_intake}` and `{effective_reference_intake}` visible in the rendered prompt.
Render body/prose template placeholders that are not selected in this staged init as `deferred; read selected handles only if needed`. Stable knowledge docs surfaced through `{active_reference_context}` are advisory: they may refine assumptions but never override `convention_lock`, `project_contract`, PLAN `contract`, or direct evidence.
If a plan relies on a knowledge doc in a downstream-gateable way, express that as explicit `knowledge_deps`.

Do not restate template-owned contract gates, tangent control, tool-requirement policy, proof-bearing plan policy, context-budget guidance, downstream-consumer rules, or the quality gate here.
```

```
PLANNER_HANDOFF_STARTED_AT=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
PLANNER_RETURN=$(
task(
  prompt="First, read {GPD_AGENTS_DIR}/gpd-planner.md for your role and instructions.\n\n" + filled_prompt + "\n\n<spawn_contract>\nwrite_scope:\n  mode: scoped_write\n  allowed_paths:\n    - \"{phase_dir}/*-PLAN.md\"\nexpected_artifacts:\n  - \"readable {phase_dir}/*-PLAN.md named in gpd_return.files_written\"\nshared_state_policy: return_only\n</spawn_contract>",
  subagent_type="gpd-planner",
  model="{planner_model}",
  readonly=false,
  description="Plan Phase {phase}"
)
)
```

Run this `child_gate`; shared gate and continuation rules live in `references/orchestration/child-artifact-gate.md` and `references/orchestration/continuation-boundary.md`.

```yaml
child_gate:
  id: "planner_initial_plan"
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
  failure_route: "retry_planner_or_main_context_plan_or_abort | repair_prompt_once | fail_closed | retry_once | repair_path_once | abort | ..."
  status_route:
    checkpoint: "fresh planner continuation after user response"
    blocked: "add context, retry, or main-context plan"
    failed: "add context, retry, or main-context plan"
```

Non-completed: use `status_route`.

## 9. Handle Planner Return

**If the planner agent fails to spawn or returns an error:** Keep the child handoff incomplete under the planner gate. Existing `PLAN.md` files are recovery evidence only. Offer: Retry planner / Main-context plan / Abort.

Planner return validation and main-context fallback are separate paths. The shared child artifact gate owns the no-synthetic-child-return rule; an explicit main-context authoring path owns its own artifacts and return envelope.

If the user chooses Main-context plan or any manual bounded authoring branch, it is not an override: set `PLANNER_HANDOFF_STARTED_AT`, write only `${PHASE_DIR}/*-PLAN.md`, set `FRESH_PLAN_FILES` to the newly created path(s), and run one gate with a complete orchestrator-owned fenced YAML `MAIN_CONTEXT_PLAN_RETURN`. No full planner/checker loop is required for this fallback unless requested, but a failing gate means `status: blocked`, not `planned_ready`/`green`, and no `gpd:execute-phase` route.

- **`gpd_return.status: completed`:** Accept only after the planner gate tuple passes, then display plan count. In `AUTONOMY=supervised`, show draft plans and get user confirmation before checker or next-step output. If `--skip-verify` or `plan_checker_enabled` is false, skip to step 13 only when no proof-bearing plans were written; proof-bearing plans still need checker review or an equivalent main-context audit. Otherwise: step 10.
- **`gpd_return.status: checkpoint`:** Use step 9b. Do not route planner checkpoints into the checker revision loop.
- **`gpd_return.status: blocked` or `failed`:** Show attempts, offer: Add context / Retry / Manual

On completed returns, consume `gpd_return.roadmap_updates` before checker review or next-step output. The planner returns proposed roadmap edits; the orchestrator applies them to `GPD/ROADMAP.md` and verifies placeholders/count against fresh `*-PLAN.md` artifacts. If missing, malformed, or unapplied, treat the handoff as incomplete: Retry planner / Apply manually / Abort.

Before checker/final status, validate only fresh `FRESH_PLAN_FILES` from the planner or manual branch. For a planner handoff, derive that list from the typed `PLANNER_RETURN`; for a main-context branch, build an orchestrator-owned `gpd return skeleton --role planner --status completed` with one `--file` entry per newly written plan. Then run the planner child_gate tuple once; all files are readable `${PHASE_DIR}/*-PLAN.md` paths, every file passes `gpd validate plan-contract`, and every file passes the structured plan preflight validator, or the route is `status: blocked`, not `planned_ready` / `gpd:execute-phase`.

## 9b. Handle Planner Checkpoint

**Planner checkpoints are a separate one-shot continuation path**

If the planner returns `gpd_return.status: checkpoint`, present the checkpoint to the user, collect the response, and spawn a fresh `gpd-planner` continuation handoff with the updated context. Keep this path distinct from checker-driven revision.

Before continuing, rerun the planner `child_gate`. If the planner continuation changes the plans, re-run the explicit plan-contract and plan-preflight validation against the refreshed `gpd_return.files_written` set before checker review.

Only after the planner returns `completed` should the workflow advance to checker review.

Next, reload `gpd --raw init plan-phase "$PHASE" --stage checker_revision` and apply the active staged payload instructions.

</process>
