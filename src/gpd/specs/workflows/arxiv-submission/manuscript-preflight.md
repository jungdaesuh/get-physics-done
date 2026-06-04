<purpose>
Refresh the manuscript-root build contract before arXiv packaging.
</purpose>

<stage_boundary>
This authority starts only after `bootstrap` has resolved the GPD-owned manuscript target and strict review preflight has passed. Do not read `workflows/arxiv-submission.md`; it is only a staged-file index.
</stage_boundary>

<process>
<step name="manuscript_preflight">
**Refresh the manuscript-root build contract before packaging.**

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

Apply `MANUSCRIPT_PREFLIGHT_INIT.staged_loading.field_access_instruction` before reading the payload. Bind only this stage's manuscript root:

```bash
INIT="$MANUSCRIPT_PREFLIGHT_INIT"
# gpd --raw stage field-access arxiv-submission --stage manuscript_preflight --style shell --payload-var INIT --alias PAPER_DIR=manuscript_root
PAPER_DIR=$(echo "$INIT" | gpd json get .manuscript_root --default "")
if [ -z "$PAPER_DIR" ]; then
  echo "ERROR: arxiv-submission manuscript_preflight missing manuscript_root"
  exit 1
fi
```

Treat `gpd paper-build` as authoritative for `ARTIFACT-MANIFEST.json` and `BIBLIOGRAPHY-AUDIT.json`. If `${PAPER_DIR}/PAPER-CONFIG.json` exists, refresh the manuscript before packaging:

```bash
gpd paper-build "${PAPER_DIR}/PAPER-CONFIG.json" --output-dir "${PAPER_DIR}"
```

The build result must report the emitted `ARTIFACT-MANIFEST.json` and `BIBLIOGRAPHY-AUDIT.json` paths explicitly.
If bibliography input comes from a literature-review citation-source sidecar, pass that file with `--citation-sources` rather than relying on an unrelated single sidecar under `GPD/literature/`.

In strict mode, `bibliography_audit_clean` and `reproducibility_ready` must pass before the workflow continues. Do not package stale audit artifacts.
Strict preflight also requires `ARTIFACT-MANIFEST.json` and `BIBLIOGRAPHY-AUDIT.json` beside the resolved manuscript entry point.

If `pdflatex` is available, run a local smoke check after the refreshed manuscript is in place. Any LaTeX error, undefined control sequence, missing reference, or missing figure is a hard stop. If `pdflatex` is not available, report that the smoke check was skipped and continue only if the manuscript-root contract remains clean.
</step>

<step name="handoff_to_review_gate">
After manuscript preflight succeeds, reload `review_gate` and start from its staged payload.
</step>

</process>
