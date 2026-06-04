<purpose>
Own the first `respond-to-referees` boundary: resolve the manuscript subject,
report-source policy, publication/review roots, review preflight, conventions,
and response-root binding before report triage or response writing can load.
</purpose>

<stage_boundary>
This is the only first-stage authority for `gpd:respond-to-referees`. Do not
read `workflows/respond-to-referees.md` or downstream stage authorities while
bootstrap is active.

Bootstrap is read-only. It may inspect project/manuscript state, command
context, review preflight output, selected roots, latest round metadata, and
conventions. It must not create response artifacts, edit the manuscript, spawn
child agents, load response templates, or run closeout.
</stage_boundary>

<core_principle>
Responding to referees is collaborative improvement, not argument winning:
address every point, be specific and respectful, separate the response letter
from manuscript edits, and track each change/new calculation/decision.
</core_principle>

<process>

<step name="init">
Run staged init and enter the resolved project root:

```bash
if [ -n "${ARGUMENTS:-}" ]; then INIT=$(gpd --raw init respond-to-referees --stage bootstrap -- "$ARGUMENTS"); else INIT=$(gpd --raw init respond-to-referees --stage bootstrap); fi
if [ $? -ne 0 ]; then echo "ERROR: gpd initialization failed: $INIT"; fi
```

<field_access>
Apply `INIT.staged_loading.field_access_instruction` before reading `INIT`.
Reference bodies stay unavailable.
</field_access>

```bash
PROJECT_ROOT=$(echo "$INIT" | gpd json get .project_root --default "")
if [ -n "$PROJECT_ROOT" ]; then cd "$PROJECT_ROOT" || { echo "ERROR: could not enter resolved project root: $PROJECT_ROOT"; exit 1; }; fi
RESPONSE_ARGUMENTS=$(echo "$INIT" | gpd json get .response_intake_input --default "")
PREFLIGHT_ARGUMENTS="$RESPONSE_ARGUMENTS"
PAPER_DIR=$(echo "$INIT" | gpd json get .manuscript_root --default "")
MANUSCRIPT_ENTRYPOINT=$(echo "$INIT" | gpd json get .manuscript_entrypoint --default "")
MANUSCRIPT_BASENAME="${MANUSCRIPT_ENTRYPOINT##*/}"
RESPONSE_PUBLICATION_ROOT=$(echo "$INIT" | gpd json get .selected_publication_root --default GPD)
RESPONSE_REVIEW_ROOT=$(echo "$INIT" | gpd json get .selected_review_root --default "")
RESPONSE_REVIEW_ROOT="${RESPONSE_REVIEW_ROOT:-${RESPONSE_PUBLICATION_ROOT}/review}"
ROUND_SUFFIX=$(echo "$INIT" | gpd json get .latest_response_round_suffix --default "")
ROUND_SUFFIX="${ROUND_SUFFIX:-$(echo "$INIT" | gpd json get .latest_review_round_suffix --default "")}"
RESPONSE_AUTHOR_PATH=$(echo "$INIT" | gpd json get .latest_author_response --default "")
RESPONSE_AUTHOR_PATH="${RESPONSE_AUTHOR_PATH:-${RESPONSE_PUBLICATION_ROOT}/AUTHOR-RESPONSE${ROUND_SUFFIX}.md}"
RESPONSE_REFEREE_PATH=$(echo "$INIT" | gpd json get .latest_referee_response --default "")
RESPONSE_REFEREE_PATH="${RESPONSE_REFEREE_PATH:-${RESPONSE_REVIEW_ROOT}/REFEREE_RESPONSE${ROUND_SUFFIX}.md}"
```

For nested-cwd launches, use `project_root`, `selected_publication_root`,
`selected_review_root`, and the resolved manuscript root from init/preflight as
authority.
Bootstrap keeps `project_contract_gate`, `project_contract_load_info`, and
`project_contract_validation` visible.

Read mode settings:

```bash
AUTONOMY=$(echo "$INIT" | gpd json get .autonomy --default supervised)
RESEARCH_MODE=$(echo "$INIT" | gpd json get .research_mode --default balanced)
```

Mode behavior:
- `autonomy=supervised`: pause after each referee point for user review.
- `autonomy=balanced`: draft/apply routine changes without forcing parse
  confirmation; pause for ambiguous report source, claim-level changes, new
  calculations, or unresolved referee disagreements. Any spawned agent that
  needs user input uses publication stage-recovery gate checkpoint semantics.
- `autonomy=yolo`: draft response and apply manuscript changes without pausing.

Normalize command intake before preflight:
- Preferred explicit intake: `gpd:respond-to-referees --manuscript path/to/main.tex --report reviews/ref1.md --report reviews/ref2.md`
- Accept the literal `paste` sentinel as an explicit report source.
- Accept `gpd:respond-to-referees path/to/report.md` or `... paste` only when
  the manuscript subject resolves from the current GPD project.
- Treat a bare positional path as a referee-report source only.
- Project-backed response rounds keep the current global `GPD/` / `GPD/review/`
  ownership. Explicit external or managed publication subjects use the
  subject-owned publication root under `GPD/publication/{subject_slug}` and its
  selected review root.
- Set `PREFLIGHT_ARGUMENTS` to the validator-safe normalized intake string
  before shelling out. For `--manuscript ... --report ...`, keep the normalized
  payload in that one variable.

Run centralized context preflight:

```bash
if [ -n "$PREFLIGHT_ARGUMENTS" ]; then
  CONTEXT=$(gpd --raw validate command-context respond-to-referees -- "$PREFLIGHT_ARGUMENTS")
else
  CONTEXT=$(gpd --raw validate command-context respond-to-referees "$ARGUMENTS")
fi
if [ $? -ne 0 ]; then
  echo "$CONTEXT"
  exit 1
fi
```

Run centralized review preflight:

```bash
if [ -n "$PREFLIGHT_ARGUMENTS" ]; then
  REVIEW_PREFLIGHT=$(gpd validate review-preflight respond-to-referees --strict -- "$PREFLIGHT_ARGUMENTS")
elif [ -n "$ARGUMENTS" ]; then
  REVIEW_PREFLIGHT=$(gpd validate review-preflight respond-to-referees "$ARGUMENTS" --strict)
else
  REVIEW_PREFLIGHT=$(gpd validate review-preflight respond-to-referees --strict)
fi
if [ $? -ne 0 ]; then
  echo "$REVIEW_PREFLIGHT"
  exit 1
fi
```

When normalized payload begins with `--`, the end-of-options marker is mandatory.
Never pass the raw pasted referee report body as `$ARGUMENTS` or
`PREFLIGHT_ARGUMENTS`; pass only the literal `paste` sentinel. If preflight
reports missing project state, missing manuscript, missing referee report source,
degraded review integrity, or missing required conventions, STOP before drafting.
In explicit external-manuscript mode, `project_state` and `conventions` are
advisory only; hard blockers are the resolved manuscript subject, report-source
set, and review-integrity failures.

Apply the shared publication bootstrap preflight exactly from the loaded
manifest authority `{GPD_INSTALL_DIR}/references/publication/publication-bootstrap-preflight.md`.

Treat the project contract as authoritative only when `project_contract_gate.authoritative` is true.
Bootstrap carries gate and load/validation status, not the full contract body. If response planning needs
contract text, wait for a later stage that selects it. Use
`derived_manuscript_reference_status` and
`derived_manuscript_proof_review_status` as quick status summaries only; the
manuscript-root `BIBLIOGRAPHY-AUDIT.json`, artifact manifest, review ledger, and
proof-redteam artifacts stay authoritative for strict response decisions.

Bind `PAPER_DIR` to the current init payload's manuscript root and
`MANUSCRIPT_BASENAME` to the current init payload's resolved entrypoint. Rebind
these from each later stage's own init payload instead of carrying bootstrap
shell variables forward.
Resolved section files such as `${PAPER_DIR}/{section}.tex` remain rooted under
the manuscript tree.

If no paper is found, stop with:

```
No paper directory found. Searched the canonical manuscript roots `paper/`, `manuscript/`, and `draft/` via the manuscript resolver

Run gpd:write-paper first to generate a manuscript from research results.
```

Check conventions before drafting:

```bash
CONV_CHECK=$(gpd --raw convention check 2>/dev/null)
if [ $? -ne 0 ]; then
  echo "WARNING: Convention verification failed - resolve before drafting referee responses"
  echo "$CONV_CHECK"
fi
```

Use `selected_publication_root` and `selected_review_root` from the target-aware
stage payload as the response roots. Later stages must rebind the response paths
from their own payloads:

```bash
if [ -d "${RESPONSE_REVIEW_ROOT}" ]; then
  find "${RESPONSE_REVIEW_ROOT}" -maxdepth 1 -type f -name 'REFEREE_RESPONSE*.md' -print
  find "${RESPONSE_REVIEW_ROOT}" -maxdepth 1 -type f -name 'REVIEW-LEDGER*.json' -print
  find "${RESPONSE_REVIEW_ROOT}" -maxdepth 1 -type f -name 'REFEREE-DECISION*.json' -print
fi
if [ -d "${RESPONSE_PUBLICATION_ROOT}" ]; then
  find "${RESPONSE_PUBLICATION_ROOT}" -maxdepth 1 -type f -name 'AUTHOR-RESPONSE*.md' -print
fi
```

Use the staged report-triage references for `round_suffix`, sibling-artifact
discovery, and active-round selection. `${RESPONSE_PUBLICATION_ROOT}/REFEREE-REPORT{round_suffix}.md`
is the canonical issue-ID source; review ledger and decision artifacts identify
blocking issues, unsupported-claim findings, recommendation floors, and stated
rationale. Keep full contract/reference bodies for later stages that select
them; bootstrap stays handle/status-only.
</step>

</process>
