# Planner Tangent Decision Model

When multiple viable approaches or optional side questions appear, do not
silently widen scope, create branch-like alternative plans, or assume every
alternative should be explored now.

Use this four-way decision model:

1. `Branch as alternative hypothesis` -> route through `gpd:tangent` or
   `gpd:branch-hypothesis`.
2. `Run a bounded side investigation now` -> route through `gpd:quick`.
3. `Capture and defer` -> route through `gpd:add-todo`.
4. `Stay on the main line` -> create plans only for the selected primary
   approach.

If the context does not already contain an explicit tangent choice and more
than one viable path remains live, return `gpd_return.status: checkpoint` with
the four options above instead of silently branching.

Create the recommended main-line plan only and set `gpd_return.status:
checkpoint` when multiple live alternatives still matter.

Explore mode widens analysis and comparison, not branch creation. Hypothesis
branches remain an explicit tangent outcome, not the default consequence of
finding alternatives.

If the user is already on an active hypothesis branch, continue serving that
branch. Re-open this model only when a new independent tangent appears and the
user has not chosen how to handle it.

## Checkpoint Example

```markdown
## CHECKPOINT REACHED

Multiple viable approaches remain:
1. Branch as alternative hypothesis -> gpd:tangent or gpd:branch-hypothesis
2. Run a bounded side investigation now -> gpd:quick
3. Capture and defer -> gpd:add-todo
4. Stay on the main line -> plan the recommended perturbative approach only
```
