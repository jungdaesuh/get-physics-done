<quick_durability_minimum>
Every completed quick task must leave durable local evidence:

- A task directory under `GPD/quick/NNN-slug/`.
- A planner artifact at `GPD/quick/NNN-slug/NNN-PLAN.md`.
- An executor summary at `GPD/quick/NNN-slug/NNN-SUMMARY.md`.
- A structured child `gpd_return` naming the local artifact in `gpd_return.files_written`.
- The executor child-return effects applied with `gpd apply-return-updates`.
- Structured state updates through `gpd state add-decision` and `gpd state update`.
- A pre-commit check over the quick artifacts and state files.
- A final `gpd commit` containing the quick plan, summary, and state update.

Never treat an agent message, partial commit, or stale file as success unless the child artifact gate passes for the expected local artifact.
</quick_durability_minimum>
