<purpose>
Render the final planning offer only after checker routing has selected a final
green, override, or skipped status.
</purpose>

<process>

## 13. Event: planning_final_offer

Route here only after `checker_return_routing` has selected one of these final
checker states:

- `green`: checker completed, plan-ID reconciliation passed, blocked set empty
- `override`: max iterations exhausted and the user chose to proceed anyway
- `skipped`: checker was unavailable for a non-proof-bearing plan set and the
  user-visible status records the skip

Do not render the final offer from initial checker handoff state, from a pending
checkpoint, from unreconciled blocked IDs, or from a failed revision planner.

**Structured final status convention:** For clean bounded non-autonomous planning
that creates or updates the expected `*-PLAN.md` artifact, has `checkpoint: none`,
and has no stale verification, proof-audit, dirty-git,
contract, preflight, convention, or checker gate, report `status: green`.
Execution remaining as the next command is not by itself a yellow condition. The
`PHASE PLANNED` offer and `gpd:execute-phase` route require the fresh-plan
validator gate above and one of the final checker states listed in this event.

Route to `<offer_next>`.

</process>

<offer_next>
Output a compact `GPD > PHASE {X} PLANNED` offer directly, not as a code block.
Include phase name, plan/wave count, research status, final checker status, and
`## > Next Up` with primary `gpd:execute-phase {X}`. Also list plan review and
`gpd:plan-phase {X} --research` as secondary options.

</offer_next>

<success_criteria>

- [ ] Fresh plan validator gate passed before any execute-phase offer.
- [ ] Final checker status is exactly `green`, `override`, or `skipped`.
- [ ] Pending checkpoints, unreconciled blocked IDs, and failed revision planner
      returns do not render the final offer.
- [ ] The user sees the next command and secondary review/research options.
</success_criteria>
