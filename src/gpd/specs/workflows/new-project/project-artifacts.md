<purpose>
Create the full-mode `GPD/PROJECT.md` artifact from the approved and persisted
scope.
</purpose>

<stage_boundary>
This stage does not author, approve, validate, or persist the scoping contract.
Use the already persisted `project_contract` as the source of truth.

If `project_contract_gate.authoritative` is false,
`project_contract_load_info.status` starts with `blocked`, or
`project_contract_validation.valid` is false, stop and route back to
`scope_approval`.
</stage_boundary>

<bootstrap>
Load this stage before writing `PROJECT.md`:

```bash
PROJECT_ARTIFACTS_INIT=$(gpd --raw init new-project --stage project_artifacts)
if [ $? -ne 0 ]; then
  echo "ERROR: project-artifacts init failed: $PROJECT_ARTIFACTS_INIT"
  # STOP; surface the error.
fi
```

Follow `PROJECT_ARTIFACTS_INIT.staged_loading.field_access_instruction`; `<INIT>` there means `PROJECT_ARTIFACTS_INIT`. Later literature, roadmap, and convention authorities stay unloaded.
</bootstrap>

<config_gate>
If `GPD/config.json` is missing, do not generate or commit `PROJECT.md` yet.
Reload and complete workflow preferences first; that is the only pre-`PROJECT.md`
setup detour for the full/auto path:

```bash
gpd --raw init new-project --stage workflow_preferences
```

After `GPD/config.json` exists, reload `project_artifacts` and continue here.
</config_gate>

<project_authoring>
Load `templates/project.md` at write time and populate `GPD/PROJECT.md` from
the approved contract plus any context preserved in `project_contract`.
Do not inline or recreate template-owned skeletons in this workflow.

For fresh projects:

- initialize active research questions from the approved scope
- say no questions are answered yet unless the contract or mapped work proves
  otherwise
- preserve out-of-scope items with the user's reason when available

For continuation projects with an existing research map:

- read `GPD/research-map/ARCHITECTURE.md` and `GPD/research-map/FORMALISM.md`
  when they exist
- infer answered questions only from established existing work
- keep uncertain claims as unresolved, not answered

`PROJECT.md` must visibly summarize the approved contract: contract coverage,
user guidance to preserve, scope boundaries, active anchors, carry-forward
inputs, skeptical-review items, and open contract questions. Preserve named
observables, deliverables, prior outputs, references, stop conditions, and
rethink triggers in wording the user would recognize.

Capture the physical system, theoretical framework, key parameters and scales,
known results, novelty, target venue when known, and computational environment.
When a field is unknown, mark it unresolved rather than inventing a plausible
value.

Record the date and initialization trigger in the template footer.
</project_authoring>

<commit_and_checkpoint>
Ensure `GPD/` exists. If `has_git` is false, initialize git before the commit
and do not perform any broader setup.

Pre-check `GPD/PROJECT.md`, `GPD/state.json`, and `GPD/config.json`. Stop if
`PROJECT.md` omits the approved contract summary or if `state.json` no longer
contains the approved contract.

Commit `GPD/PROJECT.md` and the persisted state with message:

```text
docs: initialize research project
```

Record checkpoint step `4` with the current UTC timestamp and description
`Approved project contract and PROJECT.md created and committed`, using only the
checkpoint path declared for the active stage.

After the checkpoint, reload `literature_survey` for the next full-mode stage.
</commit_and_checkpoint>
