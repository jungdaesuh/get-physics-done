<purpose>
Author `GPD/REQUIREMENTS.md` from the approved scope, project context, and any
available literature survey artifacts.
</purpose>

<stage_boundary>
This stage owns the requirements artifact only. It must not spawn
`gpd-roadmapper`, must not write `GPD/ROADMAP.md`, must not write
`GPD/CONVENTIONS.md`, and must not establish notation conventions. Scope intake,
scope approval, contract validation, and contract persistence are already owned
by earlier stages.
</stage_boundary>

<bootstrap>
Run a fresh staged init before authoring:

```bash
REQUIREMENTS_INIT=$(gpd --raw init new-project --stage requirements_authoring)
if [ $? -ne 0 ]; then
  echo "ERROR: requirements init failed: $REQUIREMENTS_INIT"
  exit 1
fi
```

Follow `REQUIREMENTS_INIT.staged_loading.field_access_instruction`; `<INIT>` there means `REQUIREMENTS_INIT`. Roadmap and convention authorities remain unavailable.

If `project_contract_gate.authoritative` is false,
`project_contract_load_info.status` starts with `blocked`, or
`project_contract_validation.valid` is false, stop and route back to
`scope_approval`. Do not repair or reinterpret the contract in this stage.
</bootstrap>

<context_loading>
Read `GPD/PROJECT.md` and `GPD/state.json`, then extract:

- the one core research question;
- stated constraints, explicit scope boundaries, and open questions;
- the approved `project_contract`;
- decisive outputs, deliverables, forbidden proxies, must-read references,
  prior outputs, known baselines, and weak assumptions from the contract.

If a literature survey exists, read `GPD/literature/METHODS.md` and
`GPD/literature/PRIOR-WORK.md` for approaches and prior-work constraints. Do not
require literature artifacts when the survey was explicitly skipped.

Load `{GPD_INSTALL_DIR}/templates/requirements.md` only in this stage when
writing `GPD/REQUIREMENTS.md`.
</context_loading>

<authoring_rules>
In auto mode:

- include essential requirements that directly answer the core question and
  satisfy the approved contract;
- include requirements explicitly mentioned in the provided document or approved
  scope;
- defer tangential investigations not mentioned in the document or contract;
- skip per-category `ask_user` loops, the additions question, and the final
  approval gate;
- write and commit `GPD/REQUIREMENTS.md` directly.

In interactive mode, present requirements by category. Use `ask_user` for each
category to decide current, future, or out-of-scope requirements, then ask
whether the literature survey missed calculations specific to the user's
approach. If no literature survey exists, gather requirements through
conversation first by asking: "What are the key results you need to establish?"

For each objective, ask enough clarifying questions to make it precise, group it
into analytical, numerical, phenomenological, or project-specific categories,
and reject vague requirements.
</authoring_rules>

<requirements_quality>
Good research requirements are specific, testable, result-oriented, atomic, and
as independent as the project allows.

Push vague requirements to concrete form:

- "Study the phase transition" -> "Determine the critical exponent nu for the
  [model] phase transition using [method]"
- "Compute correlators" -> "Compute the two-point correlation function G(r) in
  the [regime] and extract the correlation length"

REQ IDs use `[CATEGORY]-[NUMBER]`, for example `ANAL-01`, `NUMR-02`, or
`PHENO-03`.
</requirements_quality>

<requirements_artifact>
Create `GPD/REQUIREMENTS.md` with:

- current requirements grouped by category with checkboxes and REQ IDs;
- future requirements for deferred but plausible work;
- out-of-scope items with the reason for exclusion;
- a Contract Coverage section mapping requirements to decisive outputs,
  anchors, baselines, and false-progress risks;
- a Traceability section left empty for the roadmapper to fill.

Interactive mode must display the full requirements list, not only counts, and
ask:

```text
Does this capture the research program? (yes / adjust)
```

If the user chooses `adjust`, return to category scoping. If gaps remain between
the requirements and the core research question, surface the gaps before asking
for approval.
</requirements_artifact>

<commit_and_checkpoint>
Pre-check `GPD/REQUIREMENTS.md`, then commit it:

```bash
gpd commit "docs: define research requirements" --files GPD/REQUIREMENTS.md
```

Checkpoint step 7 by recording the current UTC timestamp and description
`REQUIREMENTS.md created and committed` in `GPD/init-progress.json`.

After the checkpoint, reload `roadmap_authoring`. Do not continue by inlining
roadmapper authority in this stage.
</commit_and_checkpoint>
