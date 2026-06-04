<purpose>
Own peer-review prerequisite validation and manuscript-root readiness checks.
</purpose>

<stage_boundary>
Preflight validates that the selected target mode has enough evidence for review.
It does not launch panel agents, classify final recommendations, run proof-redteam
protocols, author referee decisions, or route author-response work.
</stage_boundary>

<load_specialized_review_context>
Read the staged payload from:

```bash
if [ -n "${ARGUMENTS:-}" ]; then PREFLIGHT_INIT=$(gpd --raw init peer-review --stage preflight -- "$ARGUMENTS"); else PREFLIGHT_INIT=$(gpd --raw init peer-review --stage preflight); fi
if [ $? -ne 0 ]; then echo "ERROR: gpd peer-review preflight init failed: $PREFLIGHT_INIT"; fi
INIT="$PREFLIGHT_INIT"
```

Apply `PREFLIGHT_INIT.staged_loading.field_access_instruction` before reading it. Keep target mode, selected roots, manuscript paths, blockers, contract gate, and derived status visible.

```bash
REVIEW_TARGET=$(echo "$INIT" | gpd json get .review_target_input --default "")
PUBLICATION_ROOT=$(echo "$INIT" | gpd json get .selected_publication_root --default GPD)
REVIEW_ROOT=$(echo "$INIT" | gpd json get .selected_review_root --default "")
REVIEW_ROOT="${REVIEW_ROOT:-${PUBLICATION_ROOT}/review}"
```

Apply the canonical manuscript-root publication preflight from the loaded
manifest authority `{GPD_INSTALL_DIR}/templates/paper/publication-manuscript-root-preflight.md`.

On the normal path, rely on centralized validators for artifact freshness,
bibliography, reproducibility, and review integrity. If strict preflight
surfaces recovery or manual schema validation, load only the matching
`conditional_authorities` entry from `staged_loading` before continuing:

- `review_integrity_recovery_needed` for
  `{GPD_INSTALL_DIR}/references/publication/peer-review-reliability.md`
- `manual_publication_artifact_validation` for the paper config, artifact
  manifest, bibliography audit, and reproducibility manifest schemas
</load_specialized_review_context>

<preflight>
Run command context and strict review preflight before reading or writing review
artifacts:

```bash
if [ -n "$REVIEW_TARGET" ]; then CONTEXT=$(gpd --raw validate command-context peer-review -- "$REVIEW_TARGET"); else CONTEXT=$(gpd --raw validate command-context peer-review); fi
if [ $? -ne 0 ]; then
  echo "$CONTEXT"
  # STOP; surface the command-context error.
fi

if [ -n "$REVIEW_TARGET" ]; then REVIEW_PREFLIGHT=$(gpd validate review-preflight peer-review --strict -- "$REVIEW_TARGET"); else REVIEW_PREFLIGHT=$(gpd validate review-preflight peer-review --strict); fi
if [ $? -ne 0 ]; then
  echo "$REVIEW_PREFLIGHT"
  # STOP; surface the strict review-preflight blockers.
fi
```

command-context preflight must run before strict review preflight.

Project-backed manuscript review is strict on project state, roadmap, conventions,
research artifacts, verification reports, artifact manifest, clean bibliography audit,
and reproducibility readiness. Fail closed for missing project state, missing roadmap,
missing conventions, no research artifacts, missing verification reports, missing
`ARTIFACT-MANIFEST.json`, failed or unverified `BIBLIOGRAPHY-AUDIT.json`, or missing
`reproducibility-manifest.json`.
Keep `bibliography_audit_clean` and `reproducibility_ready` visible as strict
review fields.
The manuscript-root bibliography audit must be review-ready, not merely present.

Standalone explicit-artifact review requires one accepted readable target. Treat
project and manuscript-root artifacts as optional supporting context unless the
selected target mode makes them authoritative.

Do not copy manuscript-local artifacts into `GPD/` to satisfy strict review gates.
Do not write a managed-subject review bundle to global `GPD/review`; use
`selected_review_root`.

Do not hydrate protocol bundles, active-reference bodies, citation-source bodies,
or full reference artifacts during preflight. Those are artifact-discovery and
panel-stage inputs. Preflight only preserves the selected roots, resolved
manuscript paths, strict validator output, compact reference/proof status, and
visible blockers needed to decide whether review may proceed.

Carry forward a compact `REVIEW_CARRY_FORWARD` packet containing the selected
target, roots, compact readiness status, and blockers instead of reloading broad
bootstrap state before spawning panel stages.
Carry-forward packet: {REVIEW_CARRY_FORWARD}
Do not repeat broad bootstrap prose in panel-stage prompts.
Do not repeat full contract/reference payloads in every child prompt.
</preflight>

<handoff>
When preflight passes, reload before artifact discovery:

```bash
if [ -n "$REVIEW_TARGET" ]; then ARTIFACT_DISCOVERY_INIT=$(gpd --raw init peer-review --stage artifact_discovery -- "$REVIEW_TARGET"); else ARTIFACT_DISCOVERY_INIT=$(gpd --raw init peer-review --stage artifact_discovery); fi
if [ $? -ne 0 ]; then
  echo "ERROR: gpd peer-review artifact-discovery init failed: $ARTIFACT_DISCOVERY_INIT"
  # STOP; surface the error.
fi
```
</handoff>
