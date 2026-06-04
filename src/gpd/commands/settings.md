---
name: gpd:settings
description: Configure autonomy, unattended execution budgets, runtime permission sync, workflow preset bundles, model-cost posture, runtime-specific tier model overrides, review cadence, and git preferences
context_mode: projectless
allowed-tools:
  - file_read
  - file_write
  - shell
  - ask_user
help:
  group: Configuration and maintenance
  order: 650
  compact_description: Guided autonomy, permissions, and runtime configuration after your first successful start or later
  display_signature: gpd:settings
  notes:
    - 'Autonomy vocabulary: Supervised, Max quality, Balanced, Budget-aware, runtime defaults, YOLO.'
    - Configuration keys include `execution.review_cadence`, `planning.commit_docs`, `git.branching_strategy`, and statuses such as `needs-calculation`; model tiers are `tier-1`, `tier-2`, and `tier-3`.
    - Use `gpd observe execution` and `gpd cost` from the normal terminal for read-only status and usage review.
  root_detail_order: 300
---


<objective>
Run the guided GPD settings flow.

Keep this wrapper thin: follow the workflow and let it own option vocabulary,
user-facing explanations, and confirmation copy.
</objective>

<execution_context>
@{GPD_INSTALL_DIR}/workflows/settings.md
</execution_context>

<process>
1. Read and follow the included settings workflow.
2. Do not invent a parallel settings flow or duplicate the workflow's option-by-option guidance here.
3. Do not create separate `preset` or `physics` blocks in `GPD/config.json`; the workflow owns those rules.
4. Let the workflow own preset, model-posture, tier-model, budget, permission-sync, and local CLI bridge wording.
5. Convention work stays outside settings; use `gpd convention set <key> <value>` or `gpd:validate-conventions` for project convention updates.
</process>
