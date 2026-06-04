<purpose>
Prepare a completed paper for arXiv submission.

Stages: `bootstrap` -> `manuscript_preflight` -> `review_gate` -> `package` -> `finalize`.

Bootstrap owns command-context, strict review-preflight, manuscript-root
resolution, and arXiv-only routing. Later stages own build, review gate,
package, and final checklist. Output: `arxiv-submission.tar.gz` under
`GPD/publication/<subject_slug>/arxiv/`.
</purpose>

<required_reading>
Read all files referenced by the invoking prompt's `execution_context` before
starting. Also apply the shared publication bootstrap reference from the loaded
manifest authority `{GPD_INSTALL_DIR}/references/publication/publication-bootstrap-preflight.md`
before resolving the manuscript target.
</required_reading>

<process>

<step name="bootstrap" priority="first">
Load bootstrap and enter the resolved project root:

```bash
if [ -n "${ARGUMENTS:-}" ]; then BOOTSTRAP_INIT=$(gpd --raw init arxiv-submission --stage bootstrap -- "$ARGUMENTS"); else BOOTSTRAP_INIT=$(gpd --raw init arxiv-submission --stage bootstrap); fi
if [ $? -ne 0 ]; then echo "ERROR: arxiv-submission bootstrap init failed: $BOOTSTRAP_INIT"; exit 1; fi
INIT="$BOOTSTRAP_INIT"
```

Apply `BOOTSTRAP_INIT.staged_loading.field_access_instruction` before reading `BOOTSTRAP_INIT`.

```bash
PROJECT_ROOT=$(echo "$INIT" | gpd json get .project_root --default "")
if [ -n "$PROJECT_ROOT" ]; then cd "$PROJECT_ROOT" || { echo "ERROR: could not enter resolved project root: $PROJECT_ROOT"; exit 1; }; fi
PAPER_DIR=$(echo "$INIT" | gpd json get .manuscript_root --default "")
MAIN_SOURCE=$(echo "$INIT" | gpd json get .manuscript_entrypoint --default "")
MAIN_BASENAME="${MAIN_SOURCE##*/}"
MAIN_STEM="${MAIN_BASENAME%.*}"
SUBJECT_SLUG=$(echo "$INIT" | gpd json get .publication_subject_slug --default "")
PUBLICATION_ROOT=$(echo "$INIT" | gpd json get .managed_publication_root --default "")
[ -n "$PUBLICATION_ROOT" ] || [ -z "$SUBJECT_SLUG" ] || PUBLICATION_ROOT="GPD/publication/${SUBJECT_SLUG}"
REVIEW_ROOT=$(echo "$INIT" | gpd json get .selected_review_root --default GPD/review)
PACKAGE_ROOT="${PUBLICATION_ROOT}/arxiv"
SUBMISSION_DIR="${PACKAGE_ROOT}/submission"
PACKAGE_TARBALL="${PACKAGE_ROOT}/arxiv-submission.tar.gz"
```

Run centralized command context and strict review preflight:

```bash
if [ -n "${ARGUMENTS:-}" ]; then CONTEXT=$(gpd --raw validate command-context arxiv-submission -- "${ARGUMENTS}"); else CONTEXT=$(gpd --raw validate command-context arxiv-submission); fi
if [ $? -ne 0 ]; then echo "$CONTEXT"; exit 1; fi
```

```bash
if [ -n "${ARGUMENTS:-}" ]; then REVIEW_PREFLIGHT=$(gpd --raw validate review-preflight arxiv-submission --strict -- "${ARGUMENTS}"); else REVIEW_PREFLIGHT=$(gpd --raw validate review-preflight arxiv-submission --strict); fi
if [ $? -ne 0 ]; then echo "$REVIEW_PREFLIGHT"; exit 1; fi
```

Parse `REVIEW_PREFLIGHT` for `publication_subject_slug`, `publication_lane_kind`,
`managed_publication_root`, `selected_publication_root`, `selected_review_root`,
`manuscript_root`, and `manuscript_entrypoint`. The shared publication bootstrap
reference remains the source of truth for manuscript-root resolution,
latest-review/latest-response discovery, and paired response gating.

Strict preflight reads `ARTIFACT-MANIFEST.json`, `BIBLIOGRAPHY-AUDIT.json`, and
`reproducibility-manifest.json` from the resolved manuscript root; it is the
strict preflight source of truth for packaging and proof review. Use
`derived_manuscript_proof_review_status` as first-pass theorem-proof freshness;
must not persist `PROOF-REVIEW-MANIFEST.json` beside the manuscript root while
validating.

Packaging gates:
- Same-round/newer `gpd:respond-to-referees` artifacts require newer staged
  `gpd:peer-review` before packaging; response-only rounds are not clearance.
- Response-freshness mapping: failed `response_freshness` check or
  `latest_response_requires_fresh_review=true` checkpoint as `response_gate`,
  not `review_gate`; older target-bound review pair => `review_state: stale`,
  `response_state: requires_fresh_review`; no typed pair => `review_state:
  missing`; response gate before materialization => `command_execution_state:
  blocked_before_write` and `claim_state: not_applicable`.
- For nested-cwd launches, trust `project_root`, `manuscript_root`,
  `selected_publication_root`, and `selected_review_root` from init/preflight.
  Never infer package roots from launch cwd.

Resolve manuscript target from raw preflight plus `$ARGUMENTS`:

1. Set `resolved_main_tex` from `manuscript_entrypoint` and `resolved_dir` from
   `manuscript_root` in `REVIEW_PREFLIGHT`.
2. If `$ARGUMENTS` specifies a `.tex` file, it must match that resolved
   entrypoint and already live under `paper/`, `manuscript/`, `draft/`, or
   `GPD/publication/<subject_slug>/manuscript/`.
3. If `$ARGUMENTS` specifies a directory, the centralized preflight-resolved entrypoint under that directory is authoritative.
4. Otherwise inspect only `paper/`, `manuscript/`, `draft/`, and a unique
   `GPD/publication/<subject_slug>/manuscript/` lane when preflight resolves it.
5. If manuscript root is ambiguous/missing, STOP for an explicit manuscript path
   or repaired manuscript-root state.
6. Do not accept arbitrary external directories or standalone `.tex` entrypoints
   outside those supported roots.
7. Do not fall back to `find` or arbitrary wildcard matching outside the
   documented default roots.

If latest review artifacts are missing, incomplete, stale, or blocked, or if
manuscript-root gates fail, stop before packaging. Set `SUBJECT_SLUG` from
`publication_subject_slug`; if missing, STOP. Package outputs are always rooted
at `GPD/publication/${SUBJECT_SLUG}/arxiv/`; treat `selected_publication_root`
as validation context only. Do not write proof-review manifests, package staging
trees, or tarballs beside the manuscript root itself.

The same-stage bindings above own the package paths:

```bash
PACKAGE_ROOT="${PUBLICATION_ROOT}/arxiv"
SUBMISSION_DIR="${PACKAGE_ROOT}/submission"
PACKAGE_TARBALL="${PACKAGE_ROOT}/arxiv-submission.tar.gz"
```
</step>

<step name="handoff_to_manuscript_preflight">
After bootstrap, command-context, strict review preflight, and manuscript target
resolution pass, reload `manuscript_preflight` before refreshing the build
contract:

```bash
if [ -n "${ARGUMENTS:-}" ]; then
  MANUSCRIPT_PREFLIGHT_INIT=$(gpd --raw init arxiv-submission --stage manuscript_preflight -- "$ARGUMENTS")
else
  MANUSCRIPT_PREFLIGHT_INIT=$(gpd --raw init arxiv-submission --stage manuscript_preflight)
fi
if [ $? -ne 0 ]; then
  echo "ERROR: arxiv-submission manuscript_preflight init failed: $MANUSCRIPT_PREFLIGHT_INIT"
  exit 1
fi
```

Start manuscript preflight from `MANUSCRIPT_PREFLIGHT_INIT`. Do not continue from bootstrap memory into packaging or finalization.
</step>

</process>
