<purpose>
Route checker returns through structured fields after the checker handoff
returns or fails.
</purpose>

<process>

## 11. Event: checker_return_routing

Checker presentation headings are non-authority. Route through a valid fenced
`gpd_return.status`, structured `approved_plans`, structured `blocked_plans`,
`issues`, and the `plan_checker_review` child gate tuple. Do not treat file
existence, logs, headings, or old artifacts as checker success.

**If the plan-checker agent fails to spawn or returns an error:** Proceed
without plan verification only for non-proof-bearing plan sets. Plans are still
executable, but note that verification was skipped and recommend manual review
before execution. If any plan is proof-bearing, do NOT waive this gate: run an
equivalent main-context proof-plan audit against the checker criteria above or
STOP and report that proof-obligation planning could not be cleared safely.

**Plan-ID reconciliation is required before accepting any checker route:**

1. Build the candidate ID set only from structured `approved_plans` and `blocked_plans`; headings and tables are display-only.
2. Every candidate ID must map to exactly one readable `*-PLAN.md` artifact in
   `FRESH_PLAN_FILES`.
3. Reject overlaps between approved and blocked IDs.
4. Reject any listed ID that is missing, ambiguous, unreadable, or outside the
   fresh returned plan set.
5. Reject any checker `files_written` value other than `[]`.
6. Preserve approved IDs only after these checks pass.

- **`gpd_return.status: completed`:** Treat as a full pass only after plan-ID
  reconciliation succeeds. Before accepting the success state, verify:

  1. `approved_plans` names only readable `*-PLAN.md` artifacts in `FRESH_PLAN_FILES`
  2. `blocked_plans` is empty
  3. every approved plan file still exists and matches the approved plan IDs
  4. the approved set covers every fresh plan file that must proceed to execution
  5. the checker's `files_written` value does not claim unrelated artifacts

  If any check fails, reject the success state and send the checker output to
  `blocked_plan_revision_branch` as a fail-closed mismatch. If reconciliation
  passes, display:

  ```
  Plan passed checker (attempt {iteration_count}/3)
  ```

- **`gpd_return.status: checkpoint`:** Record approved plans from the structured
  `approved_plans` list only and blocked plans from the structured
  `blocked_plans` list only. Reject the return if any listed plan ID does not
  map to a readable `*-PLAN.md` file in `FRESH_PLAN_FILES`. Display:

     ```
     Partial approval (attempt {iteration_count}/3): {N_approved} plans approved, {N_blocked} need revision
     ```

  Send ONLY the blocked plans from the fresh returned plan set to
  `blocked_plan_revision_branch`. Pass `{structured_issues_from_checker}`. Do
  NOT re-check already-approved plans unless their inputs change during
  revision, and do not treat preexisting blocked-plan files as revised unless
  `planner_revision` passes. Approved plans from partial approval are final only
  after the plan-ID reconciliation checks pass.

- **`gpd_return.status: blocked`:** The checker found a blocker that prevents
  accepting the current plan set as-is. If `approved_plans` is empty, treat this
  as a full rejection and set `BLOCKED_PLANS` to every current fresh plan ID. If
  `approved_plans` is non-empty, preserve the approved subset only after
  plan-ID reconciliation passes, then send the blocked subset to
  `blocked_plan_revision_branch` with the structured issues.

- **`gpd_return.status: failed`:** Display iteration-aware status, show issues,
  and set `BLOCKED_PLANS` to the reconciled blocked IDs if present, otherwise to
  every current fresh plan ID:

  ```
  Checker found {N} issues (attempt {iteration_count}/3). Revising plan...
  ```

After this event, either load `planning_final_offer` with a green, skipped, or
override status, or load `blocked_plan_revision` with reconciled
`BLOCKED_PLANS` and `{structured_issues_from_checker}`.

</process>
