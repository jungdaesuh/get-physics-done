<purpose>
Present the final arXiv submission checklist after package validation has passed.
</purpose>

<stage_boundary>
This authority starts only after package materialization succeeds or, on resume, after the same arXiv package validator passes without materializing.
</stage_boundary>

<process>
<step name="finalize">
**Create the tarball and present the submission checklist.**

```bash
if [ -n "${ARGUMENTS:-}" ]; then
  FINALIZE_INIT=$(gpd --raw init arxiv-submission --stage finalize -- "$ARGUMENTS")
else
  FINALIZE_INIT=$(gpd --raw init arxiv-submission --stage finalize)
fi
if [ $? -ne 0 ]; then
  echo "ERROR: arxiv-submission finalize init failed: $FINALIZE_INIT"
  exit 1
fi
INIT="$FINALIZE_INIT"
```

Apply `FINALIZE_INIT.staged_loading.field_access_instruction` before reading `FINALIZE_INIT`.

```bash
SUBJECT_SLUG=$(echo "$INIT" | gpd json get .publication_subject_slug --default "")
PUBLICATION_ROOT=$(echo "$INIT" | gpd json get .managed_publication_root --default "")
[ -n "$PUBLICATION_ROOT" ] || [ -z "$SUBJECT_SLUG" ] || PUBLICATION_ROOT="GPD/publication/${SUBJECT_SLUG}"
PACKAGE_ROOT="${PUBLICATION_ROOT}/arxiv"
SUBMISSION_DIR="${PACKAGE_ROOT}/submission"
PACKAGE_TARBALL="${PACKAGE_ROOT}/arxiv-submission.tar.gz"
if [ -z "$SUBJECT_SLUG" ] || [ -z "$PUBLICATION_ROOT" ]; then
  echo "ERROR: arxiv-submission finalize missing publication_subject_slug"
  exit 1
fi
if [ -n "${ARGUMENTS:-}" ]; then
  PACKAGE_VALIDATION=$(gpd --raw validate arxiv-package --submission-dir "$SUBMISSION_DIR" --tarball "$PACKAGE_TARBALL" -- "$ARGUMENTS")
else
  PACKAGE_VALIDATION=$(gpd --raw validate arxiv-package --submission-dir "$SUBMISSION_DIR" --tarball "$PACKAGE_TARBALL")
fi
VALIDATION_STATUS=$?
echo "$PACKAGE_VALIDATION"
if [ $VALIDATION_STATUS -ne 0 ]; then
  exit 1
fi
```

Use `PACKAGE_VALIDATION` from this finalize-stage non-materializing validator as the authoritative resume-safe tarball proof before reporting success. Package materialization must already have succeeded in the package stage. Present a final checklist with:

- package path and size
- figure count
- quality score / status, if available
- LaTeX smoke-check status
- bibliography source/material status
- figure compatibility status
- placeholder scan status
- TeX processing compatibility status
- manual submission steps still required

Do not treat prose-only success as complete. The tarball must be under `GPD/publication/${SUBJECT_SLUG}/arxiv/`, the executable arXiv package validator must pass, and manuscript-root / latest-review gates must hold.
</step>

<community_contribution>
After the arXiv package is finalized, mention that public papers can be added to the README.md "Papers Using GPD" list at https://github.com/psi-oss/get-physics-done#papers-using-gpd with a short problem/approach summary, workflow used, and optional key result or figure. This prompt is informational only; do not block the submission workflow on it.
</community_contribution>

</process>
