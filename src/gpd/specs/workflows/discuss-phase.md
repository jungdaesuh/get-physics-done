<purpose>
Capture phase approach decisions that downstream research and planning agents
need: method choices, assumptions, anchors, falsifiers, limiting behaviors, and
stop conditions.
</purpose>

<downstream_awareness>
`CONTEXT.md` feeds `gpd-phase-researcher` and `gpd-planner`. It must preserve
the user's load-bearing guidance in recognizable language: decisive
observables, deliverables, prior output, benchmark, reference, and stop
conditions. It should make decisions clear enough that downstream agents do not
ask the user the same questions again.
</downstream_awareness>

<scope_guardrail>
The phase boundary from `ROADMAP.md` is fixed. Discussion clarifies how to
approach the scoped physics, not whether to add new physics or deliverables. If
the user suggests scope creep, note it under deferred ideas and return to the
current phase.
</scope_guardrail>

<gray_area_identification>
Gray areas are methodological decisions that could change the physics or the
result. Generate phase-specific areas, not generic categories. Examples:
formalism, approximation regime, boundary conditions, observables, benchmark or
anchor selection, numerical tolerance, error treatment, and deliverable shape.
</gray_area_identification>

<process>

<step name="initialize" priority="first">
Phase number is required. Detect `--auto` and `--compact` as mutually exclusive
mode flags. Use the runtime-provided command context if present; otherwise parse
only these two flags and the remaining phase token.

```bash
AUTO_MODE=false
COMPACT_MODE=false
if echo "$ARGUMENTS" | grep -q "\-\-auto"; then
  AUTO_MODE=true
fi
if echo "$ARGUMENTS" | grep -q "\-\-compact"; then
  COMPACT_MODE=true
fi
if [ "$AUTO_MODE" = "true" ] && [ "$COMPACT_MODE" = "true" ]; then
  echo "ERROR: --auto and --compact are mutually exclusive"
  exit 1
fi
PHASE=$(echo "$ARGUMENTS" | sed -E 's/\-\-(auto|compact)//g' | tr -s ' ' | xargs)

INIT=$(gpd --raw init phase-op "${PHASE}")
if [ $? -ne 0 ]; then
  echo "ERROR: gpd initialization failed: $INIT"
  # STOP; surface the error.
fi
```

Parse `commit_docs`, `phase_found`, `phase_dir`, `phase_number`, `phase_name`,
`phase_slug`, `padded_phase`, `has_context`, `roadmap_exists`, and
`planning_exists`.

If `phase_found` is false, check the roadmap before exiting:

```bash
ROADMAP_INFO=$(gpd --raw roadmap get-phase "${PHASE}")
if [ "$(echo "$ROADMAP_INFO" | gpd json get .found --default false)" != "true" ]; then
  echo "Phase ${PHASE} not found in ROADMAP.md."
  echo ""
  echo "Use gpd:progress to see available phases."
  exit 1
fi

phase_name=$(echo "$ROADMAP_INFO" | gpd json get .phase_name --default "")
phase_slug=$(gpd slug "$phase_name")
padded_phase=$(gpd phase normalize "${PHASE}")
phase_dir="GPD/phases/${padded_phase}-${phase_slug}"
```

Continue to check_existing using either init-provided phase metadata or
roadmap-derived phase metadata.

Mode behavior:

- `--auto`: generate 2-3 critical gray areas, ask one question per area, skip
  follow-up rounds, write lightweight context, and suggest `gpd:plan-phase`.
- `--compact`: skip gray-area discovery and use the one-screen form in
  `compact_form`.
</step>

<step name="check_existing">
If `has_context` is true or `${phase_dir}/*-CONTEXT.md` exists:

- `--auto`: reuse it and suggest planning.
- normal mode: ask whether to update, view, or skip.
- `--compact`: pre-fill the compact form from existing context where possible.

If no context exists, proceed to `compact_form` when `COMPACT_MODE=true`, else
to `analyze_phase`.
</step>

<step name="compact_form" condition="COMPACT_MODE=true">
Render one form with phase goal, current defaults, and an intent field. The
knobs are:

- `formalism`
- `conventions`
- `method`
- `precision`
- `deliverable`
- `skeptical_review`

Read exactly one response containing `knob=value` lines, optional `intent: ...`,
or `go` to accept defaults. Do not loop. Use submitted values as the
`CONTEXT.md` payload.
</step>

<step name="analyze_phase" condition="COMPACT_MODE=false">
Read the phase goal from `ROADMAP.md` and identify:

1. the domain boundary: the research question this phase answers;
2. 3-4 phase-specific gray areas in normal mode, or 2-3 in `--auto`;
3. visible user anchors: observables, deliverables, prior output, benchmark,
   reference, false-progress proxy, and what would make the approach look wrong
   or incomplete early.

Do not ask about implementation details, file organization, library APIs, or
parallelization mechanics.
</step>

<step name="present_gray_areas" condition="COMPACT_MODE=false">
Present the phase boundary and gray areas. In `--auto`, announce the selected
top areas and continue. In normal mode, use multi-select `ask_user` with 3-4
specific choices and no skip option.
</step>

<step name="discuss_areas" condition="COMPACT_MODE=false">
For each selected area:

- ask concrete physics/method questions, not generic labels;
- in normal mode ask four questions before offering "More questions" or "Next
  area"; maximum eight question rounds per area;
- in `--auto`, ask one decisive question per area and continue;
- ask at least once per phase for decisive deliverable, must-stay-visible
  anchor, fast falsifier, and stop/rethink condition;
- capture deferred ideas without acting on them.

If context pressure exceeds 50 percent during a long discussion, summarize and
suggest a fresh context reset followed by `gpd:resume-work`.
</step>

<step name="write_context">
Create the phase directory when needed:

```bash
mkdir -p "${phase_dir}"
```

Write `${phase_dir}/${padded_phase}-CONTEXT.md`. Read
`{GPD_INSTALL_DIR}/templates/context.md` only now if the runtime needs the full
template.

Required sections:

```markdown
# Phase [X]: [Name] - Context

**Gathered:** [date]
**Status:** Ready for planning

## Phase Boundary
[Scope anchor]

## Contract Coverage
- [Claim / deliverable]: [What counts as success]
- [Acceptance signal]: [Benchmark match, proof obligation, figure, dataset, or note]
- [False progress to reject]: [Proxy that must not count]

## User Guidance To Preserve
- **User-stated observables:** [...]
- **User-stated deliverables:** [...]
- **Must-have references / prior outputs:** [...]
- **Stop / rethink conditions:** [...]

## Methodological Decisions
### [Physics Category]
- [Decision]
- [Physical justification]
- [Regime or limitation]

### Agent's Discretion
[Where the user delegated judgment and constraints]

## Physical Assumptions
- [Assumption]: [Justification] | [What breaks if wrong]

## Expected Limiting Behaviors
- [Limit]: When [parameter] -> [value], result should -> [expected behavior]

## Active Anchor Registry
- [Anchor or artifact]
  - Why it matters: [constraint]
  - Carry forward: [planning | execution | verification | writing]
  - Required action: [read | use | compare | cite | avoid]

## Skeptical Review
- **Weakest anchor:** [...]
- **Unvalidated assumptions:** [...]
- **Competing explanation:** [...]
- **Disconfirming check:** [...]
- **False progress to reject:** [...]

## Deferred Ideas
[Ideas outside this phase, or "None -- discussion stayed within phase scope"]
```

Preserve explicit user wording for named observables, deliverables, references,
and stop conditions.
</step>

<step name="confirm_creation">
Present created file, captured decisions, assumptions, limiting cases, deferred
ideas, and the primary next command `gpd:plan-phase ${PHASE}`. In `--auto`, ask
whether to plan now, review context first, or stop.
</step>

<step name="git_commit">
Commit phase context when docs commits are enabled:

```bash
PRE_CHECK=$(gpd pre-commit-check --files "${phase_dir}/${padded_phase}-CONTEXT.md" 2>&1) || true
echo "$PRE_CHECK"

gpd commit "docs(${padded_phase}): capture phase context" --files "${phase_dir}/${padded_phase}-CONTEXT.md"
```
</step>

</process>

<success_criteria>
- [ ] Phase validated against init or roadmap-only phase resolution.
- [ ] Gray areas are physics-aware and phase-specific.
- [ ] Dialogue probes assumptions, approximations, anchors, falsifiers, and stop
  conditions.
- [ ] Scope creep routed to deferred ideas.
- [ ] `CONTEXT.md` captures actual methodological decisions with physical
  justification.
- [ ] User knows next steps.
</success_criteria>
