<purpose>
Prepare blocked-plan revision only after checker return routing has reconciled
the blocked plan IDs.
</purpose>

<process>

## 12. Event: blocked_plan_revision_branch

Enter this branch only after `checker_return_routing` has isolated blocked plan
IDs or a fail-closed mismatch. Revision planner machinery is branch-local here;
do not build a revision prompt until the blocked subset and the user's
exhaustion choice, if needed, are known.
The branch invariant is that blocked plan IDs are reconciled before planner
machinery appears.

Before any revision handoff:

1. Build revision `PLANS_CONTENT` from the reconciled fresh plan set.
2. For partial approval, include only the readable plan files whose IDs are
   listed in `BLOCKED_PLANS`.
3. For a full rejection, include every readable file in `FRESH_PLAN_FILES`.
4. Do not rescan the phase directory or accept an ambiguous ID match.
5. Confirm that every `plan_id` in `BLOCKED_PLANS` maps to exactly one readable
   `*-PLAN.md` file in `FRESH_PLAN_FILES`. If any blocked ID is missing or
   ambiguous, stop and report the reconciliation failure rather than inventing a
   fallback mapping.

Maximum iterations: 3. Track `iteration_count` (starts at 1 after initial plan
+ check).

**If iteration_count >= 3:**

Display: `Max iterations reached. {N} issues remain:` + issue list.

Ask only now: "The plan-checker has rejected this plan 3 times. Would you like
to: (a) proceed anyway, (b) modify the plan manually, or (c) abandon this
phase?"

- Force proceed: route to `planning_final_offer` with checker status `override`
  and include the remaining objections.
- Modify manually / provide guidance and retry: collect the user's guidance,
  keep the reconciled `BLOCKED_PLANS`, and then continue to
  `revision_planner_handoff`.
- Abandon: stop with the current checker objections and no execute-phase offer.

Do NOT loop indefinitely.

**If iteration_count < 3:** Display
`Checker found issues, revising plan (attempt {N}/3)...` and continue directly
to `revision_planner_handoff`.

</process>
