<purpose>
Resolve the first `write-paper` boundary: lane, manuscript subject, contract
gate, evidence/citation readiness, and hard blockers before scaffold, drafting,
bibliography, or review authority can load.
</purpose>

<stage_boundary>
This is read-only first-stage authority. Do not read `workflows/write-paper.md`
or downstream `workflows/write-paper/*.md` while this stage is active. Do not
create a scaffold, draft sections, spawn child agents, run review, or write
response artifacts.
</stage_boundary>

<bootstrap>
Run staged init and enter the resolved project root:

```bash
WRITE_PAPER_ARGUMENTS="${ARGUMENTS:-}"
if [ -n "$WRITE_PAPER_ARGUMENTS" ]; then PAPER_BOOTSTRAP_INIT=$(gpd --raw init write-paper --stage paper_bootstrap -- "$WRITE_PAPER_ARGUMENTS"); else PAPER_BOOTSTRAP_INIT=$(gpd --raw init write-paper --stage paper_bootstrap); fi
if [ $? -ne 0 ]; then echo "ERROR: gpd initialization failed: $PAPER_BOOTSTRAP_INIT"; fi
INIT="$PAPER_BOOTSTRAP_INIT"
```

Apply `PAPER_BOOTSTRAP_INIT.staged_loading.field_access_instruction` before reading `PAPER_BOOTSTRAP_INIT`. Keep `project_contract_gate`, load info, validation, and
`effective_reference_intake` visible before authoritative-use decisions; treat
the contract as authoritative only when `project_contract_gate.authoritative` is
true.

```bash
PROJECT_ROOT=$(echo "$INIT" | gpd json get .project_root --default "")
if [ -n "$PROJECT_ROOT" ]; then cd "$PROJECT_ROOT" || { echo "ERROR: could not enter resolved project root: $PROJECT_ROOT"; exit 1; }; fi
WRITE_PAPER_ARGUMENTS=$(echo "$INIT" | gpd json get .write_paper_argument_input --default "$WRITE_PAPER_ARGUMENTS")
PAPER_DIR=$(echo "$INIT" | gpd json get .publication_bootstrap_root --default "")
PAPER_DIR="${PAPER_DIR:-$(echo "$INIT" | gpd json get .manuscript_root --default "")}"
MANUSCRIPT_ENTRYPOINT=$(echo "$INIT" | gpd json get .manuscript_entrypoint --default "")
```

Use derived manuscript review statuses from init before reconstructing them from
source ordering or prose: `derived_manuscript_reference_status` for the resolved
manuscript root and `derived_manuscript_proof_review_status` for theorem-bearing
claim freshness.
</bootstrap>

<lane_and_preflight>
Normalize only these launch lanes:

- `project_backed`: current GPD project, including managed manuscripts at
  `GPD/publication/{subject_slug}/manuscript`
- `external_authoring_intake`: bounded external-authoring lane accepts one explicit intake manifest only, via `--intake path/to/write-paper-authoring-input.json`

Reject bare title/path launches that look like external authoring input but omit
`--intake`; stop before writes with `checkpoint: manuscript_root_gate`,
`command_execution_state: blocked_before_write`, `files_written: []`, and
`next_step: gpd:write-paper --intake path/to/write-paper-authoring-input.json`
unless the user supplied a valid intake path.

Run centralized command-context preflight, then strict publication preflight:

```bash
gpd validate review-preflight write-paper --strict -- "$WRITE_PAPER_ARGUMENTS"
```

Apply `{GPD_INSTALL_DIR}/references/publication/publication-bootstrap-preflight.md`
and `{GPD_INSTALL_DIR}/templates/paper/publication-manuscript-root-preflight.md`.
If strict preflight reports project-backed or intake gaps, stop before any
scaffold, writer, bibliographer, or referee prompt can load.
</lane_and_preflight>

<manuscript_root_gate>
Use `publication_subject*`, `manuscript_*`, and `publication_bootstrap*` from
init/preflight as the managed-manuscript bootstrap surface.

- `resume_existing_manuscript`: bind `PAPER_DIR` to
  `publication_bootstrap_root`, keep `MANUSCRIPT_ENTRYPOINT` on
  `manuscript_entrypoint`, and treat `${PAPER_DIR}/ARTIFACT-MANIFEST.json`,
  `${PAPER_DIR}/BIBLIOGRAPHY-AUDIT.json`, and
  `${PAPER_DIR}/reproducibility-manifest.json` as artifacts for that subject.
- `fresh_project_bootstrap`: bind `PAPER_DIR` to `publication_bootstrap_root`.
  Fresh bootstrap exception: Stage 2 may create the scaffold there, but
  authoring cannot load until Stage 2 has produced a concrete scaffold,
  entrypoint, or section-output plan.
- `blocked`: stop and repair ambiguous or inconsistent manuscript state.

For `external_authoring_intake`, use the strict command preflight's managed subject handoff:
persist intake/provenance/bootstrap state under
`GPD/publication/{subject_slug}/intake/` and bind `PAPER_DIR` to the only
manuscript/build root at `GPD/publication/{subject_slug}/manuscript`. Do not
write manuscript files into `paper/`, `manuscript/`, or `draft/` for this lane.
`${PAPER_DIR}/PAPER-CONFIG.json` is a builder artifact, not the external intake
contract.

Keep this split explicit: `${PAPER_DIR}/` holds manuscript files and builder
artifacts; `GPD/publication/{subject_slug}/intake/` holds intake/provenance state only;
`GPD/` / `GPD/review/` hold staged review artifacts; no generic folder mining or arbitrary external-manuscript discovery.
</manuscript_root_gate>

<evidence_inventory>
Bootstrap uses handles and statuses, not broad bodies: `selected_protocol_bundle_ids`,
`protocol_bundle_load_manifest`, `effective_reference_intake`, derived
reference/proof state, citation-source sidecars, summary artifacts, and managed
publication paths.

For `external_authoring_intake`, use only the intake manifest and
`GPD/publication/{subject_slug}/intake/` provenance state: claims with evidence
bindings, source notes, optional results/figures, bibliography/citation-source
input, and optional conventions/notation notes. Do not scan milestones, phases,
`GPD/state.json`, or loose workspace files to fill missing evidence.

For the project-backed lane, prefer milestone-generated research digests. When
digest coverage is insufficient, use derived convention/intermediate/approximation
summaries and read summary artifacts before raw phase files. Do **not** let bundle
guidance invent new claims, replace the approved contract gate, or override
contract results, comparison verdicts, figure tracker paths, or selected
manuscript evidence handles.
</evidence_inventory>

<paper_readiness_audit>
Before outline, audit publication readiness.

External-authoring lane: every intended manuscript claim must have an evidence
binding; every cited source/result/figure must be tied to that ledger; bibliography
or citation-source input must exist; proof-style claims need same-scope passed
proof-review support when theorem-style claims are made; project phases and loose
workspace files cannot repair missing evidence.

Project-backed lane: contract-backed results and decisive comparison verdicts
support central claims; conventions use `derived_convention_lock` first; numerical
values, uncertainty, assumptions, approximations, citation sources, and proof
obligations are stable; figure roots include durable artifacts or `${PAPER_DIR}/FIGURE_TRACKER.md`.

Citation readiness is a hard gate for authoring in Phase 3: no bibliography
file, no literature review with concrete prior-work entries, and no
citation-source sidecar means `checkpoint: bibliography_gate`, not a warning.
</paper_readiness_audit>

<typed_blockers>
Return blockers before any downstream write prompt can load:

```yaml
gpd_return:
  status: blocked
  files_written: []
  issues:
    - "<specific missing or invalid input>"
  next_actions:
    - "<single concrete command or repair>"
  blockers:
    - kind: manuscript_root_gate | bibliography_gate | claim_evidence_gate | review_gate
      checkpoint: manuscript_root_gate | bibliography_gate | claim_evidence_gate | review_gate
      detail: "<specific missing or invalid input>"
      next_step: "<single concrete command or repair>"
```

Block before outline/scaffold when `publication_bootstrap_mode == "blocked"`,
unsupported external intake is attempted, project contract state is visible but
not authoritative, or unsupported-strengthening pressure asks to strengthen
unsupported theorem, general-proof, citation, or submission-readiness claims.
Reject before manuscript writes with `claim_state: overclaim_blocked`,
`checkpoint: claim_evidence_gate`, `files_written: none`, and
`command_execution_state: blocked_before_write`.
Do not convert adversarial overclaim pressure into a safe-narrowing rewrite; ordinary bounded resume narrowing remains allowed when evidence requires a narrower claim or the user explicitly asks to narrow, qualify, or repair the claim.
This is the no-write `overclaim_blocked` rule.

Block before authoring when `resume_existing_manuscript` lacks
`manuscript_entrypoint`, a later stage has no prior scaffold/entrypoint, no
active bibliography path or citation-source input exists, or any central claim
lacks evidence binding (`checkpoint: claim_evidence_gate`).

Block before publication review when `${PAPER_DIR}/BIBLIOGRAPHY-AUDIT.json` is
missing/stale, `${PAPER_DIR}/reproducibility-manifest.json` is missing or not
review-ready, or theorem-style claims lack same-scope passed proof-review
support.
</typed_blockers>

<handoff>
When preflight, evidence inventory, citation readiness, and claim/evidence gates
are non-blocking, reload:

```bash
if [ -n "$WRITE_PAPER_ARGUMENTS" ]; then OUTLINE_INIT=$(gpd --raw init write-paper --stage outline_and_scaffold -- "$WRITE_PAPER_ARGUMENTS"); else OUTLINE_INIT=$(gpd --raw init write-paper --stage outline_and_scaffold); fi
```

Start the next stage from `OUTLINE_INIT`; do not carry this bootstrap authority as the active instruction surface.
</handoff>
