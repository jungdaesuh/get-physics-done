<purpose>
Create and validate the arXiv submission tree under the managed GPD publication root.
</purpose>

<stage_boundary>
This authority starts only after `review_gate` has accepted latest staged review evidence and any required proof-review clearance.
</stage_boundary>

<process>
<step name="package">
**Create the arXiv submission tree.**

```bash
if [ -n "${ARGUMENTS:-}" ]; then
  PACKAGE_INIT=$(gpd --raw init arxiv-submission --stage package -- "$ARGUMENTS")
else
  PACKAGE_INIT=$(gpd --raw init arxiv-submission --stage package)
fi
if [ $? -ne 0 ]; then
  echo "ERROR: arxiv-submission package init failed: $PACKAGE_INIT"
  exit 1
fi
```

Apply `PACKAGE_INIT.staged_loading.field_access_instruction` before reading the payload. Bind package paths from this stage's init payload:

```bash
INIT="$PACKAGE_INIT"
# gpd --raw stage field-access arxiv-submission --stage package --style shell --payload-var INIT --alias PAPER_DIR=manuscript_root --alias SUBJECT_SLUG=publication_subject_slug --alias PUBLICATION_ROOT=managed_publication_root
PAPER_DIR=$(echo "$INIT" | gpd json get .manuscript_root --default "")
SUBJECT_SLUG=$(echo "$INIT" | gpd json get .publication_subject_slug --default "")
PUBLICATION_ROOT=$(echo "$INIT" | gpd json get .managed_publication_root --default "")
if [ -z "$PUBLICATION_ROOT" ] && [ -n "$SUBJECT_SLUG" ]; then
  PUBLICATION_ROOT="GPD/publication/${SUBJECT_SLUG}"
fi
if [ -z "$PAPER_DIR" ] || [ -z "$SUBJECT_SLUG" ] || [ -z "$PUBLICATION_ROOT" ]; then
  echo "ERROR: arxiv-submission package missing manuscript_root or publication_subject_slug"
  exit 1
fi
PACKAGE_ROOT="${PUBLICATION_ROOT}/arxiv"
SUBMISSION_DIR="${PACKAGE_ROOT}/submission"
PACKAGE_TARBALL="${PACKAGE_ROOT}/arxiv-submission.tar.gz"
```

Keep the packaging rules arXiv-specific and deterministic:

1. Keep `\input{}` / `\include{}` chains only if every source file is packaged; flatten only as repair.
2. Include bibliography material as packaged `.bib`, packaged `.bbl`, or inlined `thebibliography`; do not require `.bbl` inlining for a complete `.bib` workflow.
3. Copy or convert figures into arXiv-compatible formats only.
4. Reject unresolved placeholders (`RESULT PENDING`, `\cite{MISSING:...}`, `TODO`, `FIXME`).
5. Package ancillary files only when they are present and relevant.
6. Remove LaTeX auxiliary files, editor backups, and metadata noise from the submission tree.
7. Generate `00README.XXX` only when the submission contains more than one file.

Keep the submission tree itself under `${SUBMISSION_DIR}`. Do not create a sibling `arxiv-submission/` directory beside the manuscript or place GPD-authored package manifests there.

Use these arXiv-specific checks:

| Issue | Action |
|---|---|
| TIFF figures | Convert to PNG before packaging |
| PDF figures | Keep for PDFLaTeX-compatible processing; do not require `\pdfoutput=1` |
| EPS figures | Warn if fonts are not embedded |
| Abstract too long | Warn if the abstract exceeds the arXiv metadata limit |
| Total package size | Fail if the package exceeds the arXiv limit |
| Missing bibliography material | Fail if citation-bearing TeX lacks packaged `.bib`, packaged `.bbl`, or inlined bibliography |

If the manuscript root is not already `paper/`, stage the package in a temporary submission tree that preserves the resolved manuscript root as the upload entrypoint and keeps the root-level file layout flat. The managed package root still remains `${PACKAGE_ROOT}` under `GPD/`.

Then materialize and validate with the executable package boundary. It reruns strict `arxiv-submission` review preflight, keeps `${SUBMISSION_DIR}` and `${PACKAGE_TARBALL}` under `${PACKAGE_ROOT}`, rejects unsafe tar paths, symlinks, aux files, placeholders, empty cites/refs, missing bibliography material, and requires the main `.tex` at tar root:

```yaml
executable_gate:
  id: arxiv_package_validator
  role: arxiv-package-validator
  expected_artifacts:
    - GPD/publication/${SUBJECT_SLUG}/arxiv/arxiv-submission.tar.gz
    - ${PAPER_DIR}/ARTIFACT-MANIFEST.json
    - ${PAPER_DIR}/BIBLIOGRAPHY-AUDIT.json
    - latest REVIEW-LEDGER and REFEREE-DECISION pair
    - current PROOF-REDTEAM artifact when theorem-bearing
  allowed_root: GPD/publication/${SUBJECT_SLUG}/arxiv
  freshness_marker: PACKAGE_VALIDATION from current package/finalize stage
  validators:
    - gpd --raw validate arxiv-package --materialize
    - strict manuscript preflight
    - review_gate latest-round checks
    - paper-build manuscript-root refresh
  applicator: arxiv-package validator materialization
  failure_route: response_gate/review_gate/manuscript_preflight/package stop; route response freshness back to gpd:peer-review
```

```bash
if [ -n "${ARGUMENTS:-}" ]; then
  PACKAGE_VALIDATION=$(gpd --raw validate arxiv-package --materialize --submission-dir "$SUBMISSION_DIR" --tarball "$PACKAGE_TARBALL" -- "$ARGUMENTS")
else
  PACKAGE_VALIDATION=$(gpd --raw validate arxiv-package --materialize --submission-dir "$SUBMISSION_DIR" --tarball "$PACKAGE_TARBALL")
fi
if [ $? -ne 0 ]; then
  echo "$PACKAGE_VALIDATION"
  exit 1
fi
```
</step>

<step name="handoff_to_finalize">
After `gpd --raw validate arxiv-package --materialize` succeeds, reload `finalize` and start from its staged payload.
</step>

</process>
