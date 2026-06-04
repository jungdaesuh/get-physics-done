<purpose>
Own the first staged `peer-review` boundary: target-aware intake, manuscript
routing, contract-gate visibility, and handoff to strict review preflight.
</purpose>

<stage_boundary>
This is the only bootstrap authority for `gpd:peer-review`. Do not read
`workflows/peer-review.md` or downstream authorities while bootstrap is active.
Do not load panel prompts, reliability rules, proof-redteam protocols, schemas,
final-adjudication rules, or response routing in bootstrap.

Bootstrap is read-only. It resolves which target is being reviewed and which
selected publication/review roots later stages must use.
</stage_boundary>

<bootstrap_init>
Run staged init before any review decision:

```bash
if [ -n "${ARGUMENTS:-}" ]; then BOOTSTRAP_INIT=$(gpd --raw init peer-review --stage bootstrap -- "$ARGUMENTS"); else BOOTSTRAP_INIT=$(gpd --raw init peer-review --stage bootstrap); fi
if [ $? -ne 0 ]; then echo "ERROR: gpd peer-review bootstrap init failed: $BOOTSTRAP_INIT"; fi
INIT="$BOOTSTRAP_INIT"
```

Apply `BOOTSTRAP_INIT.staged_loading.field_access_instruction` before reading `BOOTSTRAP_INIT`; keep `project_contract_gate`, `project_contract_load_info`, and `project_contract_validation` visible.

```bash
REVIEW_TARGET=$(echo "$INIT" | gpd json get .review_target_input --default "")
PUBLICATION_ROOT=$(echo "$INIT" | gpd json get .selected_publication_root --default GPD)
REVIEW_ROOT=$(echo "$INIT" | gpd json get .selected_review_root --default "")
REVIEW_ROOT="${REVIEW_ROOT:-${PUBLICATION_ROOT}/review}"
```

AUTONOMY=$(echo "$BOOTSTRAP_INIT" | gpd json get .autonomy --default balanced)
RESEARCH_MODE=$(echo "$BOOTSTRAP_INIT" | gpd json get .research_mode --default balanced)
Pass `<autonomy_mode>{AUTONOMY}</autonomy_mode>` and
`<research_mode>{RESEARCH_MODE}</research_mode>` to reviewers.

Keep `project_contract_gate` visible. If `project_contract_gate.authoritative`
is false, use `contract_intake` and `effective_reference_intake` only as
diagnostics/context carry-forward evidence. Do not hydrate full reference or
active-reference bodies in bootstrap. If contract loading is blocked, repair it
before retrying.
</bootstrap_init>

<target_routing>
`$ARGUMENTS` can be empty, a paper directory, a manuscript path, or an explicit
external artifact path.

Peer review supports:
- `project-backed manuscript review`: strict publication-pipeline review of the
  current GPD project manuscript under `paper/`, `manuscript/`, `draft/`, or
  `GPD/publication/{subject_slug}/manuscript`.
- `standalone explicit-artifact review`: path-driven review of one explicit
  manuscript artifact or accepted target. Nearby project/manuscript-root
  artifacts are additive unless the selected mode makes them authoritative.

Explicit external artifact intake points at one artifact path and must not widen
into default root discovery. If no argument is provided, ask whether to review an
explicit artifact or the current GPD project's active manuscript when available.

Use centralized target-aware init and the authoritative manuscript resolver:
explicit argument first, otherwise manuscript-root `ARTIFACT-MANIFEST.json`,
then `PAPER-CONFIG.json`, then canonical current manuscript entrypoint rules for
supported roots. Do not use ad hoc wildcard discovery.

If no manuscript or explicit target resolves, STOP at `manuscript_required` with
`command_execution_state: blocked_before_write`, `files_written: []`, and
`next_step: none`.
</target_routing>

<root_binding>
Use centralized preflight's selected publication/review roots for GPD-authored
review artifacts. Never write managed-subject review artifacts to global
`GPD/review` fallback.

Keep `publication_subject_slug`, `publication_lane_kind`,
`managed_publication_root`, `selected_publication_root`, and
`selected_review_root` visible for later review-stage payloads. Set
`REVIEW_ROOT` = `selected_review_root`.

The default in-project manuscript family is `paper/`, `manuscript`, and `draft`.
A project-managed `GPD/publication/{subject_slug}/manuscript` lane writes staged
review outputs to `GPD/publication/{subject_slug}/review`, not beside the
manuscript and not under default global `GPD/review`.
</root_binding>

<stage_map>
Before spawning any reviewer, the panel stage gives the user a concise stage map.
Preserve these stage ids:

1. `bootstrap` resolves target mode, root bindings, contract-gate visibility, and prior-round snapshot state.
2. `preflight` validates mode-aware prerequisites and manuscript-root readiness.
3. `artifact_discovery` loads manuscript artifacts, target-aware round state, and proof-bearing routing state without launching panel agents.
4. `panel_stages` runs claim extraction, specialist review, stage validation, and the conditional proof critic.
5. `final_adjudication` runs the Stage 6 referee over persisted upstream artifacts.
6. `finalize` summarizes the completed review and routes the next action.
</stage_map>

<handoff>
When bootstrap target routing is resolved, reload before strict checks:

```bash
if [ -n "$REVIEW_TARGET" ]; then
  PREFLIGHT_INIT=$(gpd --raw init peer-review --stage preflight -- "$REVIEW_TARGET")
else
  PREFLIGHT_INIT=$(gpd --raw init peer-review --stage preflight)
fi
if [ $? -ne 0 ]; then
  echo "ERROR: gpd peer-review preflight init failed: $PREFLIGHT_INIT"
  # STOP; surface the error.
fi
```

Do not continue from bootstrap memory into preflight. Later stages must start
from their staged init payloads and persisted artifacts.
</handoff>
