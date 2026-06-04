<purpose>
Finish `new-project` initialization by cleaning up init progress and rendering
the final full-mode or minimal-mode next-step display.
</purpose>

<stage_boundary>
This is the only stage that owns final branded completion UX. Earlier stages may
report local progress, but they must not duplicate the final initialized-project
display or the `## > Next Up` route. If a shared UI branding reference is needed,
load `references/ui/ui-brand.md` only for this completion stage.
</stage_boundary>

<bootstrap>
Run a fresh staged init before completion:

```bash
COMPLETION_INIT=$(gpd --raw init new-project --stage completion)
if [ $? -ne 0 ]; then
  echo "ERROR: completion init failed: $COMPLETION_INIT"
  exit 1
fi
```

Follow `COMPLETION_INIT.staged_loading.field_access_instruction`; `<INIT>` there means `COMPLETION_INIT`. Summarize only after the chosen initialization path has landed.
</bootstrap>

<cleanup>
Delete `GPD/init-progress.json` only after all selected initialization artifacts
and commits have landed.

Minimal mode may reach completion directly after `minimal_artifacts`. Full mode
may reach completion only after project artifacts, workflow preferences,
requirements, roadmap, and conventions are complete, with literature included
only if selected.
</cleanup>

<full_completion>
Render this full-mode completion display:

```text
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 GPD >>> RESEARCH PROJECT INITIALIZED
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

**[Project Name]**

| Artifact       | Location                    |
|----------------|-----------------------------|
| Project        | `GPD/PROJECT.md`            |
| Config         | `GPD/config.json`           |
| Literature     | `GPD/literature/`           |
| Requirements   | `GPD/REQUIREMENTS.md`       |
| Roadmap        | `GPD/ROADMAP.md`            |
| Conventions    | `GPD/CONVENTIONS.md`        |

**[N] phases** | **[X] requirements** | Ready to investigate

## > Next Up

**Phase 1: [Phase Name]** - [Goal from ROADMAP.md]

`gpd:discuss-phase 1`

<sub>Start a fresh context window, then run `gpd:discuss-phase 1`.</sub>

Discuss first; plan after context is clear. Phase stubs stay lean; expand them
with `gpd:plan-phase N` when reached.

---

**Also available:**
- `gpd:plan-phase 1` - skip discussion only when Phase 1 is already clear enough to plan
- `gpd:suggest-next` - confirm the next action
```
</full_completion>

<minimal_completion>
Render this minimal-mode completion display:

```text
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 GPD >>> MINIMAL RESEARCH PROJECT INITIALIZED
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

**[Project Name]**

| Artifact       | Location                    |
|----------------|-----------------------------|
| Project        | `GPD/PROJECT.md`            |
| Config         | `GPD/config.json`           |
| Requirements   | `GPD/REQUIREMENTS.md`       |
| Roadmap        | `GPD/ROADMAP.md`            |
| State          | `GPD/STATE.md`              |

No literature survey or notation convention artifact has been promised in
minimal mode.

## > Next Up

`gpd:discuss-phase 1`

**Also available:**
- `gpd:plan-phase 1` - skip discussion only when Phase 1 is already clear enough to plan
- `gpd:suggest-next` - confirm the next action
```
</minimal_completion>

<output>
Full mode output:

- `GPD/PROJECT.md`
- `GPD/config.json`
- `GPD/literature/` if literature survey was selected:
  - `PRIOR-WORK.md`
  - `METHODS.md`
  - `COMPUTATIONAL.md`
  - `PITFALLS.md`
  - `SUMMARY.md`
- `GPD/REQUIREMENTS.md`
- `GPD/ROADMAP.md`
- `GPD/STATE.md`
- `GPD/state.json` with `project_contract`
- `GPD/CONVENTIONS.md`

Minimal mode output:

- `GPD/PROJECT.md`
- `GPD/config.json`
- `GPD/REQUIREMENTS.md`
- `GPD/ROADMAP.md`
- `GPD/STATE.md`
- `GPD/state.json` with `project_contract`
</output>

<success_criteria>
Full mode:

- [ ] approved scoping contract persisted in `GPD/state.json`;
- [ ] `PROJECT.md`, `config.json`, `REQUIREMENTS.md`, `ROADMAP.md`, `STATE.md`,
  `state.json`, and `CONVENTIONS.md` are committed;
- [ ] literature files are committed if the survey was selected;
- [ ] `ROADMAP.md` maps requirements to phases and exposes Phase 1 success
  criteria plus compact stub identity for later phases;
- [ ] convention lock is populated through `gpd convention set`;
- [ ] user sees `gpd:discuss-phase 1` as the primary next step.

Minimal mode:

- [ ] `GPD/` was created and the repo initialized;
- [ ] structured intake captured the core question, decisive outputs, anchors,
  and known gaps;
- [ ] scoping contract was approved, validated, and persisted before artifact
  generation;
- [ ] `PROJECT.md`, `config.json`, `REQUIREMENTS.md`, `ROADMAP.md`, `STATE.md`,
  and `state.json` were created and committed;
- [ ] no promise is made that `GPD/literature/` or `GPD/CONVENTIONS.md` exists;
- [ ] user sees a concrete phase-1 next step.

Atomic commits: each initialization stage commits its artifacts immediately so
work persists if context is lost.
</success_criteria>
