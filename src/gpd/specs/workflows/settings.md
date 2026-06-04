<purpose>
Guided configuration of autonomy, unattended execution budgets, workflow agents,
research profile, qualitative model-cost posture, runtime-specific tier model
overrides, `execution.review_cadence`, git branching, and runtime permission
sync. Use `gpd:set-tier-models` for the narrow direct path for `tier-1`,
`tier-2`, and `tier-3` model ids.
</purpose>

<preset_guidance>
Workflow presets resolve into existing config keys only. Do not create, persist,
or infer a separate `preset` block in `GPD/config.json`.

Preset bundles may set: `autonomy`, `research_mode`,
`execution.review_cadence`, `parallelization`, `planning.commit_docs`,
`workflow.research`, `workflow.plan_checker`, `workflow.verifier`,
`model_profile`, and current `model_overrides` only when the user explicitly
edits tier overrides. A preset does **not** by itself authorize git-backed
hypothesis branches; surface tangent decisions explicitly. Suppress optional
tangents unless the user explicitly requests them, and use an explicit apply or
customize choice for settings changes. For publication / manuscript presets, `paper-build`
remains the manuscript build contract, while LaTeX readiness still drives
readiness for `write-paper` / `peer-review` and can degrade or block `paper-build` / `arxiv-submission`. Preview resolved knobs first, then ask apply or customize.
</preset_guidance>

<required_reading>
Read all files referenced by the invoking prompt's execution_context before
starting.
</required_reading>

<process>

<step name="ensure_and_load_config">
Ensure config exists and load current state:

```bash
gpd config ensure-section
INIT=$(gpd --raw init progress --include state,config --no-project-reentry)
if [ $? -ne 0 ]; then
  echo "ERROR: gpd initialization failed: $INIT"
  # STOP; surface the error.
fi
PROJECT_ROOT=$(echo "$INIT" | gpd json get .project_root --default ".")
```

`--no-project-reentry` disables recent-project auto-selection for this settings
bootstrap only; normal ancestor project resolution still works from nested
folders.
</step>

<step name="read_current">
```bash
cat "$PROJECT_ROOT/GPD/config.json"
```

Parse current values, using the schema defaults noted below when a key is
absent:

- `autonomy` -- `"supervised"` (default), `"balanced"`, `"yolo"`
- `research_mode` -- `"explore"`, `"balanced"` (default), `"exploit"`, `"adaptive"`
- `model_overrides` -- optional runtime-scoped concrete model mapping for
  `tier-1`, `tier-2`, `tier-3`
- `workflow.research`, `workflow.plan_checker`, `workflow.verifier`
- `execution.review_cadence` -- `"dense"` (default), `"adaptive"`, `"sparse"`
- `execution.max_unattended_minutes_per_plan`
- `execution.max_unattended_minutes_per_wave`
- `execution.project_usd_budget`
- `execution.session_usd_budget`
- `execution.checkpoint_after_n_tasks`
- `execution.checkpoint_after_first_load_bearing_result`
- `execution.checkpoint_before_downstream_dependent_tasks`
- `planning.commit_docs`
- `parallelization`
- `model_profile`
- `git.branching_strategy` -- `"branching_strategy": "none" | "per-phase" | "per-milestone"`

`workflow.verifier=false` disables only the generic post-execution verifier;
this does NOT disable mandatory proof red-teaming for `proof_obligation` work.
`execution.review_cadence` is independent of `model_profile` and
`research_mode`: it controls bounded review stop density, not agent tiering or
verification rigor. Sparse cadence does not waive proof red-teaming for
proof-bearing work.

Project conventions do **not** live in `GPD/config.json`. Do not invent or
preserve a `physics` section here. Project conventions still live in `GPD/state.json` (`convention_lock`) with `GPD/CONVENTIONS.md` as the projection/audit surface, not in `GPD/config.json`.
</step>

<step name="determine_runtime_for_model_overrides">
First infer the active runtime identifier or ask before prompting for concrete
model IDs. Record it as `SELECTED_RUNTIME`. Use this same value for
`model_overrides.<SELECTED_RUNTIME>` and every permissions status/sync command;
do not let permissions sync re-detect a different runtime after model overrides
are written.
</step>

<step name="present_settings">

@{GPD_INSTALL_DIR}/references/shared/interactive-choice-fallback.md

Treat this as the guided unattended-use flow. Recommend `Supervised` as the
default advisor cadence; point users at `Balanced` when they want fewer routine
pauses after trust is established.

**Checkpoint keystrokes.** Most supervised checkpoints render a one-line
summary and resume with `[Y/n/e]`: Enter or `Y` accepts, `n` rejects, `e` edits
or gives freeform feedback. A few physics-bearing or destructive checkpoints
intentionally stay more explicit; see
`{GPD_INSTALL_DIR}/references/orchestration/checkpoint-ux-convention.md`.

For normal-terminal follow-up around these settings:

- use `gpd --help` when you need the broader local CLI entrypoint
- use `gpd validate unattended-readiness --runtime <runtime> --autonomy <mode>` for the unattended or overnight verdict after autonomy and permissions changes
- use `gpd permissions sync --runtime <runtime> --autonomy <mode>` when runtime-owned permission settings need explicit alignment
- use `gpd cost` after runs for advisory local usage / cost, optional USD budget guardrails, and the current profile tier mix

Broader local references stay outside this settings-specific list: `gpd doctor`,
`gpd integrations status wolfram`, and `gpd validate plan-preflight <PLAN.md>`.

Before detailed questions, offer preset preview choices:

- Core research (Recommended): preview the supervised default bundle over the existing knobs, then apply or customize
- Theory: preview the derivation-heavy bundle over the existing knobs, then apply or customize
- Numerics: preview the computation-heavy bundle over the existing knobs, then apply or customize
- Publication / manuscript: preview the paper-writing bundle over the existing knobs, then apply or customize
- Full research: preview core-research plus publication readiness over the existing knobs, then apply or customize
- Customize settings: skip preset preview and ask detailed questions

Use `ask_user` with current values pre-selected. Every group is single-select
and preserves these labels/mappings:

| Header | Question | Options and mapping |
| --- | --- | --- |
| `Autonomy` | How much autonomy should the AI have? | `Supervised (Recommended)` -> `autonomy=supervised`; `Balanced` -> `autonomy=balanced`; `YOLO` -> `autonomy=yolo`. |
| `Research Mode` | Research strategy? | `Explore` -> `research_mode=explore`; `Balanced (Recommended)` -> `research_mode=balanced`; `Exploit` -> `research_mode=exploit`; `Adaptive` -> `research_mode=adaptive`. |
| `Research Profile` | Which research profile for agents? | `Deep Theory` -> `model_profile=deep-theory`; `Numerical` -> `model_profile=numerical`; `Exploratory` -> `model_profile=exploratory`; `Review (Recommended)` -> `model_profile=review`; `Paper Writing` -> `model_profile=paper-writing`. |
| `Model Cost Posture` | What model-cost posture should GPD optimize for? | `Max Quality`; `Balanced (Recommended)`; `Budget-aware`. Qualitative only: no persisted key, billing promise, or spend enforcement. |
| `Tier Models` | How should GPD handle concrete tier models for the active runtime? | `Leave current setting unchanged` preserves `model_overrides.<SELECTED_RUNTIME>` exactly; `Use runtime defaults` clears that runtime's tier map; `Configure explicit tier models` asks for runtime-native `tier-1`, `tier-2`, and `tier-3` strings. |
| `Research` | Spawn Plan Researcher? | `Yes` -> `workflow.research=true`; `No` -> `workflow.research=false`. |
| `Plan Check` | Spawn Plan Checker? | `Yes` -> `workflow.plan_checker=true`; `No` -> `workflow.plan_checker=false`. |
| `Verifier` | Spawn Execution Verifier? | `Yes` -> `workflow.verifier=true`; `No` -> `workflow.verifier=false` for only the generic post-execution verifier; this does NOT disable mandatory proof red-teaming for proof-bearing or `proof_obligation` work. |
| `Cadence` | How aggressively should execution inject review gates? | `Dense (Recommended)` -> `execution.review_cadence=dense`; `Adaptive` -> `execution.review_cadence=adaptive`; `Sparse` -> `execution.review_cadence=sparse`. Sparse cadence does not waive proof red-teaming for proof-bearing work. |
| `Planning Commit Docs` | Should planning artifacts be committed to git? | `Commit planning docs` -> `planning.commit_docs=true`; `Keep planning docs local-only` -> `planning.commit_docs=false`. |
| `Parallel` | Execute plans within a wave in parallel? | `Yes (Recommended)` -> `parallelization=true`; `No` -> `parallelization=false`. |
| `Branching` | Git branching strategy? | `none (Recommended)` -> `git.branching_strategy=none`; `per-phase` -> `git.branching_strategy=per-phase`; `per-milestone` -> `git.branching_strategy=per-milestone`. |

After the ask_user responses, ask one compact inline follow-up for unattended
execution budgets and checkpoint controls using current values as defaults:

- `execution.max_unattended_minutes_per_plan`
- `execution.max_unattended_minutes_per_wave`
- `execution.checkpoint_after_n_tasks`
- `execution.checkpoint_after_first_load_bearing_result`
- `execution.checkpoint_before_downstream_dependent_tasks`

Then ask one compact inline follow-up for optional advisory USD budget
guardrails using current values as defaults:

- `execution.project_usd_budget`
- `execution.session_usd_budget`

These guardrails are advisory only, may stay partial or estimated when telemetry
is missing, and never stop work automatically. To clear a configured USD budget, use literal JSON `null`. Blank means preserve the current value. Do not advertise or pass `none` or an empty string as a clearing value.
</step>

<step name="configure_model_overrides">
Handle concrete tier model overrides for the active runtime:

- **Leave current setting unchanged:** preserve
  `model_overrides.<SELECTED_RUNTIME>` exactly.
- **Use runtime defaults:** clear `model_overrides.<SELECTED_RUNTIME>` so GPD
  falls back to runtime defaults.
- **Configure explicit tier models:** ask one compact freeform follow-up for
  active-runtime `tier-1`, `tier-2`, and `tier-3` strings. Ask for the exact model string the active runtime accepts.

Preserve runtime-native model identifiers exactly except for trimming
surrounding whitespace. Preserve any provider prefixes and slash-delimited ids.
Treat blank / `runtime default` / `none` as "no override for this tier". Treat literal `default` as a real model alias only when the
active runtime supports it and the user explicitly intends that alias.
</step>

<step name="update_config">
Apply each selected setting through the config CLI. This keeps storage canonical
and avoids writing nested alias blocks by hand.

Before applying, map responses into these variables only:

- `SELECTED_AUTONOMY`
- `SELECTED_RESEARCH_MODE`
- `SELECTED_MODEL_PROFILE`
- `SELECTED_PARALLELIZATION`
- `SELECTED_COMMIT_DOCS`
- `SELECTED_WORKFLOW_RESEARCH`
- `SELECTED_WORKFLOW_PLAN_CHECKER`
- `SELECTED_WORKFLOW_VERIFIER`
- `SELECTED_REVIEW_CADENCE`
- `SELECTED_MAX_UNATTENDED_MINUTES_PER_PLAN`
- `SELECTED_MAX_UNATTENDED_MINUTES_PER_WAVE`
- `SELECTED_CHECKPOINT_AFTER_N_TASKS`
- `SELECTED_CHECKPOINT_AFTER_FIRST_RESULT`
- `SELECTED_CHECKPOINT_BEFORE_DEPENDENTS`
- `SELECTED_BRANCHING_STRATEGY`
- `SELECTED_PROJECT_USD_BUDGET`
- `SELECTED_SESSION_USD_BUDGET`
- `SELECTED_RUNTIME`

For optional USD budgets, valid write values are a positive number or literal
JSON `null`; blank preserves the current value by skipping that `gpd config set`
call. Preserve `git.phase_branch_template` and `git.milestone_branch_template`
exactly as the current config stores them; this guided flow changes only
`git.branching_strategy`.

Run `gpd config set <key> "$<selected variable>"` for each row; skip only blank
USD-budget rows:

| Config key | Selected variable |
| --- | --- |
| `autonomy` | `SELECTED_AUTONOMY` |
| `research_mode` | `SELECTED_RESEARCH_MODE` |
| `model_profile` | `SELECTED_MODEL_PROFILE` |
| `parallelization` | `SELECTED_PARALLELIZATION` |
| `planning.commit_docs` | `SELECTED_COMMIT_DOCS` |
| `workflow.research` | `SELECTED_WORKFLOW_RESEARCH` |
| `workflow.plan_checker` | `SELECTED_WORKFLOW_PLAN_CHECKER` |
| `workflow.verifier` | `SELECTED_WORKFLOW_VERIFIER` |
| `execution.review_cadence` | `SELECTED_REVIEW_CADENCE` |
| `execution.max_unattended_minutes_per_plan` | `SELECTED_MAX_UNATTENDED_MINUTES_PER_PLAN` |
| `execution.max_unattended_minutes_per_wave` | `SELECTED_MAX_UNATTENDED_MINUTES_PER_WAVE` |
| `execution.checkpoint_after_n_tasks` | `SELECTED_CHECKPOINT_AFTER_N_TASKS` |
| `execution.checkpoint_after_first_load_bearing_result` | `SELECTED_CHECKPOINT_AFTER_FIRST_RESULT` |
| `execution.checkpoint_before_downstream_dependent_tasks` | `SELECTED_CHECKPOINT_BEFORE_DEPENDENTS` |
| `git.branching_strategy` | `SELECTED_BRANCHING_STRATEGY` |
| `execution.project_usd_budget` | `SELECTED_PROJECT_USD_BUDGET` |
| `execution.session_usd_budget` | `SELECTED_SESSION_USD_BUDGET` |

Exact command forms that must remain valid include
`gpd config set autonomy "$SELECTED_AUTONOMY"`,
`gpd config set workflow.research "$SELECTED_WORKFLOW_RESEARCH"`,
`gpd config set execution.review_cadence "$SELECTED_REVIEW_CADENCE"`, and
`gpd config set git.branching_strategy "$SELECTED_BRANCHING_STRATEGY"`.

For runtime model overrides, merge the new `<SELECTED_RUNTIME>` tier map with
existing `model_overrides` for other runtimes, then write the whole object:
`gpd config set model_overrides "$MODEL_OVERRIDES_JSON"`.

Immediately sync runtime-owned permission settings against selected autonomy:

```bash
PERMISSIONS_SYNC=$(gpd --raw permissions sync --runtime "$SELECTED_RUNTIME" --autonomy "$SELECTED_AUTONOMY" 2>/dev/null || true)
echo "$PERMISSIONS_SYNC"
```

Always surface `message`. If `requires_relaunch` is true, surface `next_step`
verbatim and state that unattended use is not ready yet under the newly selected
autonomy. This syncs the runtime to the selected autonomy, including the most
autonomous permission mode when YOLO is selected. This sync handles
runtime-owned permission settings only, not install health or workflow/tool readiness.
</step>

<step name="confirm">
Display a compact confirmation table for active runtime, research profile, model
cost posture, tier models, workflow toggles, review cadence, USD budget
guardrails, planning commits, parallelization, git branching, and runtime
permissions.

| Runtime Permissions  | {aligned / changed / manual follow-up required} |

Terminal follow-ups for these settings: reuse the normal-terminal follow-up list from the `present_settings` step (`gpd --help`,
`gpd validate unattended-readiness`, `gpd permissions sync`, `gpd cost`). Keep
`gpd doctor`, `gpd integrations status wolfram`, and
`gpd validate plan-preflight <PLAN.md>` as broader references outside this
settings-owned follow-up list.

Model-cost posture is qualitative guidance only. It maps onto existing
`model_profile` and `model_overrides`, not a new persisted config key, pricing
system, or billing promise. Optional USD budget guardrails are checked by
`gpd cost`; they stay advisory and never stop work automatically.

Runtime sync:
- `{permissions_sync.message}`
- `{permissions_sync.next_step if present}`
- If relaunch is still required, say clearly that unattended use is not ready
  yet under the newly selected autonomy setting.

Project conventions still live in `GPD/state.json` (`convention_lock`) with
`GPD/CONVENTIONS.md` as the projection/audit surface, not in `GPD/config.json`.

Quick commands:
- gpd:set-profile <profile> -- switch research profile
- gpd:set-tier-models -- direct concrete `tier-1` / `tier-2` / `tier-3` model-id setup
- gpd:settings -- revisit interactive model/tier setup
- gpd:validate-conventions -- verify convention consistency across the project
- gpd convention set <key> <value> -- update the locked project conventions directly
- gpd:plan-phase --research -- force research
- gpd:plan-phase --skip-research -- skip research
- gpd:plan-phase --skip-verify -- skip plan check
</step>

<step name="runtime_guidance">
Refer to `{GPD_INSTALL_DIR}/references/tooling/runtime-config-guide.md` for
minimal runtime configuration, extension compatibility, portable multi-machine
patterns, permission alignment, and troubleshooting.
</step>

</process>

<downstream_consumption>
Workflow config from `GPD/config.json` is consumed by planners/orchestrators,
executors, `gpd cost`, runtime hints, hooks, and runtime adapters. Project
conventions propagate separately through `GPD/state.json` (`convention_lock`)
and the `GPD/CONVENTIONS.md` projection, with the lock as source of truth.
</downstream_consumption>

<success_criteria>
- [ ] Current config read.
- [ ] Active runtime inferred or confirmed before model override guidance.
- [ ] User presented with autonomy, unattended time budgets, optional advisory
  USD guardrails, profile, model-cost posture, tier-model handling, workflow
  toggles, review cadence, git branching, and runtime permission sync.
- [ ] Config updated with model_profile, optional model_overrides, workflow,
  execution, and git sections.
- [ ] Runtime permissions sync attempted after autonomy is written, with
  relaunch guidance surfaced when required.
- [ ] No stale `physics` section written into `GPD/config.json`.
- [ ] Concrete tier model strings stored in runtime-native format when chosen.
- [ ] Changes confirmed to user.
</success_criteria>
