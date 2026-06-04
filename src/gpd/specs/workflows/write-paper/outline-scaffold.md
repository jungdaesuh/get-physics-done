<purpose>
Own paper scope, journal/builder selection, detailed outline, and manuscript
scaffold generation.
</purpose>

<first_decision>
First choose the target journal, paper type, one-sentence key result, audience,
and evidence lane; if the key result cannot be stated cleanly, narrow before any
scaffold or builder repair.
</first_decision>

<stage_boundary>
This stage may write the managed manuscript scaffold and intake/provenance roots
already allowed by the stage manifest. It does not draft sections, verify
bibliography, run peer review, or spawn downstream child agents.
</stage_boundary>

<init>
Load the staged outline/scaffold payload before using outline-time publication
scaffolding fields or paper schema authorities:

```bash
if [ -n "${ARGUMENTS:-}" ]; then OUTLINE_INIT=$(gpd --raw init write-paper --stage outline_and_scaffold -- "$ARGUMENTS"); else OUTLINE_INIT=$(gpd --raw init write-paper --stage outline_and_scaffold); fi
if [ $? -ne 0 ]; then echo "ERROR: write-paper outline/scaffold init failed: $OUTLINE_INIT"; fi
INIT="$OUTLINE_INIT"
```

Apply `OUTLINE_INIT.staged_loading.field_access_instruction` before reading `OUTLINE_INIT`. This stage is handle/status-first; read specific project, manuscript, or reference files by handle only after the paper target above is selected.

```bash
WRITE_PAPER_ARGUMENTS=$(echo "$INIT" | gpd json get .write_paper_argument_input --default "")
PAPER_DIR=$(echo "$INIT" | gpd json get .publication_bootstrap_root --default "")
PAPER_DIR="${PAPER_DIR:-$(echo "$INIT" | gpd json get .manuscript_root --default "")}"
MANUSCRIPT_ENTRYPOINT=$(echo "$INIT" | gpd json get .manuscript_entrypoint --default "")
MANUSCRIPT_BASENAME="${MANUSCRIPT_ENTRYPOINT##*/}"
AUTONOMY=$(echo "$INIT" | gpd json get .autonomy --default balanced)
RESEARCH_MODE=$(echo "$INIT" | gpd json get .research_mode --default balanced)
```
</init>

<journal_formats>
The builder schema owns exact fields. Current valid `PAPER-CONFIG.json` and
`${PAPER_DIR}/ARTIFACT-MANIFEST.json` journal keys:

- `prl`
- `apj`
- `mnras`
- `nature`
- `jhep`
- `jfm`

These are the only valid `journal` values in `PAPER-CONFIG.json` and
`${PAPER_DIR}/ARTIFACT-MANIFEST.json`.

Read `publication-pipeline-modes.md` only for the selected paper lane's mode
choices; do not infer unsupported builder journal keys from scoring-only
profiles.
</journal_formats>

<scope>
From the validated bootstrap/evidence state, record:

- target journal and formatting requirements
- paper type: new result, new method, comparison, or review
- the one key result or honestly narrowed claim
- target audience
- available evidence and decisive comparison artifacts

Every section must support, contextualize, or explain the key result. If the key
result cannot be stated in one sentence, narrow the paper before scaffolding.
</scope>

<create_outline>
Generate a detailed outline tailored to the journal format.

For each section include:

- purpose in the narrative
- key content, with 3-7 concrete points
- equations to include by source artifact
- figures or tables by source artifact
- citations or citation-source IDs
- length estimate
- dependencies and evidence/proof obligations

The outline must satisfy:

1. A reader of only the Introduction understands what was done and why.
2. A reader of only the Results gets the key finding with evidence.
3. A reader of Abstract + Conclusions gets the full story in miniature.
4. The Discussion interprets the result rather than repeating it.

If `autonomy=supervised`, present the outline for approval before proceeding. If `autonomy=balanced`, treat the outline as a working draft and continue automatically unless it exposes a genuine ambiguity, missing evidence path, or scope-changing decision that needs user judgment. If `autonomy=yolo`, continue automatically after the artifact checks.
</create_outline>

<generate_files>
Create or repair the manuscript directory under the manifest-resolved
`${PAPER_DIR}`:

```text
${PAPER_DIR}/
+-- {topic_specific_stem}.tex
+-- abstract.tex
+-- introduction.tex
+-- model.tex or setup.tex
+-- methods.tex or derivation.tex
+-- results.tex
+-- discussion.tex
+-- conclusions.tex
+-- appendix_A.tex
+-- references.bib
+-- figures/
+-- Makefile
```

Prefer the canonical builder whenever a real machine-readable paper spec exists:

```bash
mkdir -p "${PAPER_DIR}"
gpd paper-build "${PAPER_DIR}/PAPER-CONFIG.json" --output-dir "${PAPER_DIR}"
```

This emits `${PAPER_DIR}/{topic_specific_stem}.tex` and the manuscript-root
artifact manifest at `${PAPER_DIR}/ARTIFACT-MANIFEST.json`; builder output
defines manuscript build truth and local compiler runs are smoke checks. For
`fresh_project_bootstrap` or explicit builder-regeneration, create/repair
`${PAPER_DIR}/PAPER-CONFIG.json` from
`templates/paper/paper-config-schema.md`, set a short underscore
`output_filename`, and run `gpd paper-build` before drafting.

For fresh bootstrap, pre-fill `authors` via `gpd.core.profile.load_profile()`
(reads `~/.gpd/profile.json`; `GPD_DATA_DIR` env overrides the base dir). Map
each `AuthorProfile` to an `authors[]` entry: `name`/`email` directly,
`affiliations` joined with `"; "` into the singular `affiliation`. Prompt the
user only when the profile is empty.

For `resume_existing_manuscript`, do not probe the builder with throwaway `/tmp`
configs or create optional `${PAPER_DIR}/PAPER-CONFIG.json` when an accepted
entrypoint exists. Read the schema only for real builder repair; if unclear or
audits cannot refresh, stop at `checkpoint: command_failed` or
`checkpoint: bibliography_gate`.

Schema authorities own full config and artifact-manifest details. Local
constraints: keep `journal` to a supported builder key, keep list fields as JSON
arrays, and do not reuse `${PAPER_DIR}/PAPER-CONFIG.json` as the external intake
contract.

Keep this split explicit:

- `${PAPER_DIR}` is the manuscript-local scaffold root for the current subject
- `GPD/publication/{subject_slug}/intake/` stores intake/provenance only
- builder-owned manuscript artifacts remain beside that manuscript root
- GPD-owned review and response auxiliaries remain under `GPD/` / `GPD/review/`

After `gpd paper-build` runs, treat the `.tex` artifact recorded in
`${PAPER_DIR}/ARTIFACT-MANIFEST.json` as the canonical manuscript entrypoint and
refer to its basename as `MANUSCRIPT_BASENAME` in later smoke checks.
</generate_files>

<compiler_probe>
Detect `pdflatex` on PATH for later smoke checks. If unavailable, warn that
local compilation smoke checks are skipped; `.tex` generation still proceeds and
`gpd paper-build` remains the canonical manuscript scaffold contract. Do not
install TeX automatically.
</compiler_probe>

<handoff>
Before handing off to authoring, confirm:

- `${PAPER_DIR}` exists under the manifest-resolved publication root
- a concrete manuscript entrypoint, scaffold plan, or section-output plan exists
- `${PAPER_DIR}/ARTIFACT-MANIFEST.json` exists when the builder ran
- active bibliography path or citation-source input is known
- no open evidence blocker remains for central claims

Then reload:

```bash
if [ -n "$WRITE_PAPER_ARGUMENTS" ]; then AUTHORING_INIT=$(gpd --raw init write-paper --stage figure_and_section_authoring -- "$WRITE_PAPER_ARGUMENTS"); else AUTHORING_INIT=$(gpd --raw init write-paper --stage figure_and_section_authoring); fi
```
</handoff>
