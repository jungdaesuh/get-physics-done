<purpose>
Create executable PLAN.md files for a phase through staged authorities. This root file is an index only; active instructions live in the stage files below.
</purpose>

<process>

## Staged Authority Index

Load exactly one active stage authority at a time from `plan-phase-stage-manifest.json`. The command wrapper starts with `workflows/plan-phase/phase-bootstrap.md`; later stage loading is manifest-owned by each active staged payload.

| Order | Stage id | Active authority | Purpose | Next stage |
| ---: | --- | --- | --- | --- |
| 1 | `phase_bootstrap` | `workflows/plan-phase/phase-bootstrap.md` | Phase lookup, required gates, and bootstrap routing. | `research_routing` |
| 2 | `research_routing` | `workflows/plan-phase/research-routing.md` | Research reuse, refresh, gap routing, and researcher handoff. | `planner_authoring` |
| 3 | `planner_authoring` | `workflows/plan-phase/planner-authoring.md` | Planner handoff, plan artifact gate, and checkpoint routing. | `checker_revision` |
| 4 | `checker_revision` | `workflows/plan-phase/checker-revision.md` | Checker handoff plus conditional return, revision, and final-offer lanes. | none |

Stage authorities and the manifest own required fields, allowed tools, write
scopes, checkpoints, lifecycle gates, and fail-closed routing. This root is only the stage map.

</process>
