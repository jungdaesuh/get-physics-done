<purpose>
Create the minimal-mode core project artifacts after explicit scope approval
and approved-contract persistence.
</purpose>

<stage_boundary>
This stage starts only after `scope_approval` has validated and persisted the
approved `project_contract`.

Do not perform intake, scope repair, approval, validation, or contract
persistence here. If `project_contract_gate.authoritative` is false,
`project_contract_load_info.status` starts with `blocked`, or
`project_contract_validation.valid` is false, stop and route back to
`scope_approval`.
</stage_boundary>

<bootstrap>
Load this stage before artifact creation:

```bash
MINIMAL_ARTIFACTS_INIT=$(gpd --raw init new-project --stage minimal_artifacts)
if [ $? -ne 0 ]; then
  echo "ERROR: minimal-artifacts init failed: $MINIMAL_ARTIFACTS_INIT"
  # STOP; surface the error.
fi
```

Follow `MINIMAL_ARTIFACTS_INIT.staged_loading.field_access_instruction`; `<INIT>` there means `MINIMAL_ARTIFACTS_INIT`. Use approved contract/runtime fields only.
</bootstrap>

<artifact_scope>
Create only these minimal startup artifacts:

- `GPD/PROJECT.md`
- `GPD/config.json`
- `GPD/REQUIREMENTS.md`
- `GPD/ROADMAP.md`
- `GPD/STATE.md`
- `GPD/state.json`

Minimal mode promises no additional startup artifacts. Preserve the approved
contract and the user's named observables, deliverables, anchors, prior outputs,
stop conditions, rethink triggers, and unresolved gaps. When the contract lacks
detail, say so explicitly instead of inventing anchors, references, phase
structure, tools, or benchmarks.
</artifact_scope>

<artifact_authoring>
## M2. Create PROJECT.md

Load `templates/project.md` at write time and populate `GPD/PROJECT.md` from
the persisted approved contract. Do not inline or recreate the template body in
this workflow.

Keep requirements in `GPD/REQUIREMENTS.md`; `PROJECT.md` should mirror the
contract-critical anchors, readable project context, scope boundaries, and
known unresolved questions.

If the project may rely on Wolfram capability, distinguish a local Mathematica
or Wolfram Language install from the shared optional Wolfram integration config.
Executable probes such as `wolframscript -version`, `pdflatex --version`, or
`pdftotext -v` belong to `gpd doctor --live-executable-probes`, not to this
artifact write.

## M3. Create REQUIREMENTS.md

Generate compact REQ-IDs from the approved contract's decisive outputs,
confirmed work chunks, or first investigation chunk. Use this structure:

```markdown
# Research Requirements

## Current Requirements

### Phase-Derived Requirements

- [ ] **REQ-01**: [specific, testable goal]
- [ ] **REQ-02**: [specific, testable goal if supported by the contract]

## Future Work

(To be identified as project progresses)

## Out of Scope

(To be refined as the project matures)

## Traceability

| REQ-ID | Phase | Status  |
| ------ | ----- | ------- |
| REQ-01 | 1     | Planned |
```

If only one grounded work chunk exists, create one requirement and carry later
decomposition as future work.

## M4. Create ROADMAP.md

Write a lightweight local `GPD/ROADMAP.md` directly from the approved contract.
Do not delegate this file to a later roadmap authority in minimal mode.

Use the coarsest decomposition the contract supports. If only one grounded
stage is known, keep the roadmap to one phase and record later decomposition as
an open question.

Use this structure:

```markdown
# Roadmap: [Research Project Title]

## Overview

[One paragraph from the approved contract]

## Phases

- [ ] **Phase 1: [Phase name]** - [one-line description]

## Phase Details

### Phase 1: [Phase name]

**Goal:** [contract-grounded goal]
**Depends on:** Nothing (first phase)
**Requirements:** REQ-01

**Success Criteria** (what must be TRUE):

1. [concrete observable outcome]

Plans:

- [ ] 01-01: TBD - created during `gpd:plan-phase 1`

## Progress

| Phase     | Plans Complete | Status      | Completed |
| --------- | -------------- | ----------- | --------- |
| 1. [Name] | 0/TBD          | Not started | -         |
```

## M5. Create STATE.md, state.json, and config.json

Load `templates/state.md` only when writing `GPD/STATE.md`; do not inline the
template body here.

Initialize `GPD/STATE.md` with the project reference, core research question,
Phase 1 ready-to-plan position, empty active calculations and intermediate
results, approved-contract unresolved questions, and no pending todos or
blockers unless the user supplied them. Record last activity as
`Project initialized (minimal)`.

Preserve the existing `project_contract` in `GPD/state.json`. Refresh only the
minimal initialization metadata and canonical continuity fields needed by
`gpd:resume-work`:

- `continuation.handoff.recorded_at`: current ISO timestamp
- `continuation.handoff.stopped_at`: `Project initialized (minimal)`
- `continuation.handoff.resume_file`: `null`
- `continuation.machine.recorded_at`: current ISO timestamp
- `continuation.machine.hostname`: current hostname
- `continuation.machine.platform`: current platform

Create `GPD/config.json` with these defaults:

```json
{
  "autonomy": "supervised",
  "research_mode": "balanced",
  "execution": {
    "review_cadence": "dense"
  },
  "parallelization": true,
  "planning": {
    "commit_docs": true
  },
  "model_profile": "review",
  "workflow": {
    "research": true,
    "plan_checker": true,
    "verifier": true
  }
}
```
</artifact_authoring>

<commit_and_handoff>
Ensure `GPD/` exists. If `has_git` is false, initialize git before the commit
and do not perform any broader setup.

Before committing, pre-check exactly the six minimal artifacts listed in
`artifact_scope`; stop if any is missing, empty, or contradicts the approved
contract. Commit them together with message:

```text
docs: initialize research project (minimal)
```

After the commit, reload the completion stage for the final display and next
step:

```bash
gpd --raw init new-project --stage completion
```

The completion stage should present `gpd:discuss-phase 1` as the primary next
step, with `gpd:plan-phase 1` and `gpd:suggest-next` as secondary options.
</commit_and_handoff>
