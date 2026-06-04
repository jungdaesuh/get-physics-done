<purpose>
Verify fresh plans, route structured checker results, revise only blocked plans,
and present final planning status after the active checker/revision event has
resolved.
</purpose>

<stage_boundary>
Final-stage authority is event-local. Start with `checker_handoff`; do not use
return routing until a `CHECKER_RETURN` or spawn error exists. Do not use
revision planner machinery until blocked plan IDs are reconciled. Do not show
max-iteration choices unless the revision limit is exhausted. Do not render the
final offer until a green, override, or skipped checker status has been selected.
</stage_boundary>

<process>

## 10. Event: checker_handoff

Display banner (include iteration count if in revision loop):

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 GPD > VERIFYING PLANS (attempt {iteration_count}/3)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

* Spawning plan checker...
```

Refresh the checker/revision payload before entering the checker loop:

```bash
INIT=$(gpd --raw init plan-phase "$PHASE" --stage checker_revision)
if [ $? -ne 0 ]; then
  echo "ERROR: staged plan-phase init failed: $INIT"
  exit 1
fi
# Apply INIT.staged_loading.field_access_instruction before using this payload.
```

Read each fresh plan artifact into `PLANS_CONTENT` only after the planner gate
passes. Use runtime file-read tooling and the reconciled `FRESH_PLAN_FILES`
list; do not rescan the phase directory or include older plan files that were
not part of the fresh planner return.

Initial checker event exclusions: do not display revision planner prompts,
max-iteration choices, or the final planning offer during `checker_handoff`.
This event only prepares local checker context and spawns the one-shot checker.

Checker prompt:

```markdown
<verification_context>
**Phase:** {phase_number}
**Phase Goal:** {goal from ROADMAP}

**Plans to verify:** {plans_content}
Use `INIT.staged_loading.field_access_instruction` as the prompt inventory. Include the project contract/gate values, `contract_intake`,
`effective_reference_intake`, and selected reference path handles from that
staged payload; do not request rendered reference or artifact body fields.
<protocol_bundle_handoff>
<selected_protocol_bundle_ids>{selected_protocol_bundle_ids}</selected_protocol_bundle_ids>
<protocol_bundle_load_manifest>{protocol_bundle_load_manifest}</protocol_bundle_load_manifest>
<protocol_bundle_verifier_extensions>{protocol_bundle_verifier_extensions}</protocol_bundle_verifier_extensions>
</protocol_bundle_handoff>
Treat reference paths as handles, not preloaded bodies. Read a selected path only
when a checker finding depends on quoting or decisive comparison evidence;
reviewed knowledge docs never override `convention_lock`, `project_contract`,
the PLAN `contract`, or decisive evidence.
Check that any downstream-gateable reliance on a reviewed knowledge doc is
written as explicit `knowledge_deps`, not only implied by background context.

**Phase Context:**
IMPORTANT: Plans MUST honor user decisions. If context is needed, read
`${PHASE_DIR}/*-CONTEXT.md`; locked decisions must be implemented exactly,
discretion areas may be chosen by the plan, and deferred ideas remain out of
scope.
</verification_context>

<local_checker_criteria>
The checker agent owns the full verification dimensions and return structure.
This handoff adds only local plan-phase constraints:

- [ ] **Decisive outputs / acceptance tests:** Plans cover decisive claims and
      deliverables, with executable or reviewable tests, rather than proxy-only
      infrastructure.
- [ ] **Anchor and protocol coverage:** Required references, baselines, prior
      outputs, and protocol bundles are explicit where the plan depends on them.
- [ ] **Physics sanity:** Dimensional consistency, limiting cases,
      approximation validity, conservation/symmetry obligations, independent
      cross-checks, and expected scales are explicit where relevant.
- [ ] **Disconfirming path / forbidden proxies:** Risky plans name what would
      force a rethink and reject proxy-only success conditions.
- [ ] **Proof-obligation audit path:** Proof-bearing plans expose theorem
      targets, named parameters/hypotheses/quantifiers, and a sibling
      `{plan_id}-PROOF-REDTEAM.md` review artifact.
- [ ] **Anti-bypass language:** Plans do not rely on `--skip-verify`, sparse
      cadence, or later human inspection to waive proof red-teaming.
</local_checker_criteria>

<expected_output>

- ## VERIFICATION PASSED -- all checks pass
- ## ISSUES FOUND -- structured issue list
- ## PARTIAL APPROVAL -- some plans approved, others need revision (see partial_approval protocol in your agent instructions)
</expected_output>
```

```
CHECKER_HANDOFF_STARTED_AT=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
CHECKER_RETURN=$(
task(
  prompt="First, read {GPD_AGENTS_DIR}/gpd-plan-checker.md for your role and instructions.\n\n" + checker_prompt + "\n\n<spawn_contract>\nwrite_scope:\n  mode: read_only\n  allowed_paths: []\nexpected_artifacts: []\nshared_state_policy: return_only\n</spawn_contract>",
  subagent_type="gpd-plan-checker",
  model="{checker_model}",
  readonly=false,
  description="Verify Phase {phase} plans"
)
)
```

Keep this local checker gate tuple with the handoff. Run this `child_gate` only
after `CHECKER_RETURN` exists; shared acceptance and continuation rules live in
`references/orchestration/child-artifact-gate.md` and
`references/orchestration/continuation-boundary.md`.

```yaml
child_gate:
  id: "plan_checker_review"
  role: "gpd-plan-checker"
  return_profile: "checker"
  required_status: "completed"
  expected_artifacts: []
  allowed_roots: []
  validators:
    - "approved/blocked plan-ID reconciliation against FRESH_PLAN_FILES"
    - "files_written: []"
    - "blocked_plans empty for completed status"
  applicator: none
  failure_route: "fail_closed_or_manual_review | repair_prompt_once | revision_loop_or_fail_closed"
  status_route:
    checkpoint: "record partial approval then revision loop or fresh continuation"
    blocked: "revision loop or manual review"
    failed: "revision loop or manual review"
```

Non-completed checker returns use `status_route` in `checker_return_routing`.

Stop this event after the checker call. Continue to `checker_return_routing`
only when the runtime has a checker spawn error or a fenced `CHECKER_RETURN`.
At that point load the `checker_return_routing` conditional authority pack.

<conditional_lanes>
Load these only when their trigger is present:

- `checker_return_routing`: `CHECKER_RETURN` or checker spawn error exists.
- `blocked_plan_revision`: return routing produced reconciled `BLOCKED_PLANS`.
- `revision_planner_handoff`: the blocked branch selected retry or manual-guided
  revision.
- `planning_final_offer`: return routing selected `green`, `override`, or
  `skipped`.
</conditional_lanes>

</process>

<success_criteria>

- [ ] Checker prompt uses the fresh `FRESH_PLAN_FILES` set and staged handles.
- [ ] Checker child return is gated through the local `plan_checker_review`
      tuple.
- [ ] Late return routing, revision machinery, max-iteration choices, and final
      offer text are loaded only through conditional lanes.
- [ ] No checker success is accepted before structured plan-ID reconciliation.
</success_criteria>
