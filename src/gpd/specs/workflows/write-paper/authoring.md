<purpose>
Own figure preparation, section drafting, equation presentation, and section
handoff artifact gates.
</purpose>

<stage_boundary>
This is the first write-paper stage allowed to spawn section-writing child work.
It cannot run unless the outline/scaffold stage produced or resolved
`${PAPER_DIR}` plus a concrete manuscript entrypoint, scaffold, or section-output
plan, and the bootstrap stage cleared citation/evidence blockers for the active
claims.
</stage_boundary>

<init>
Load the staged figure/section authoring payload before generating figures or
spawning paper-writer section agents:

```bash
if [ -n "${ARGUMENTS:-}" ]; then AUTHORING_INIT=$(gpd --raw init write-paper --stage figure_and_section_authoring -- "$ARGUMENTS"); else AUTHORING_INIT=$(gpd --raw init write-paper --stage figure_and_section_authoring); fi
if [ $? -ne 0 ]; then echo "ERROR: write-paper authoring init failed: $AUTHORING_INIT"; fi
INIT="$AUTHORING_INIT"
```

Apply `AUTHORING_INIT.staged_loading.field_access_instruction` before reading `AUTHORING_INIT`.

```bash
WRITE_PAPER_ARGUMENTS=$(echo "$INIT" | gpd json get .write_paper_argument_input --default "")
PAPER_DIR=$(echo "$INIT" | gpd json get .publication_bootstrap_root --default "")
PAPER_DIR="${PAPER_DIR:-$(echo "$INIT" | gpd json get .manuscript_root --default "")}"
MANUSCRIPT_ENTRYPOINT=$(echo "$INIT" | gpd json get .manuscript_entrypoint --default "")
MANUSCRIPT_BASENAME="${MANUSCRIPT_ENTRYPOINT##*/}"
AUTONOMY=$(echo "$INIT" | gpd json get .autonomy --default balanced)
RESEARCH_MODE=$(echo "$INIT" | gpd json get .research_mode --default balanced)
if command -v pdflatex >/dev/null 2>&1; then
  PDFLATEX_AVAILABLE=true
else
  PDFLATEX_AVAILABLE=false
fi
```

This is a body-hydration stage: section drafting may use planning bodies and
reference artifact content. It still does not need rendered
`protocol_bundle_context` or rendered `active_reference_context`; use bundle
IDs/load manifests, reference handles, and specific files for any quoted or
section-local evidence.

Handle-first authoring invariant: before a section-local domain or method
judgment, bind the section claim, choose the relevant selected asset from
`protocol_bundle_load_manifest` (`verification_domains`, `execution_guides`, or
fallback domain/protocol handle), and read that file. Bundle-id acknowledgment is
not enough.
</init>

<writing_principle>
A physics paper has a narrative arc: motivation, setup, development, result, and
significance. Every equation, figure, and paragraph must advance this argument.
Anything that does not support the active claim belongs in an appendix or is cut.
</writing_principle>

<generate_figures>
Ensure the paper directory structure exists before writing figure files:

```bash
mkdir -p "${PAPER_DIR}/figures"
```

Before reading or updating `${PAPER_DIR}/FIGURE_TRACKER.md`, load
`{GPD_INSTALL_DIR}/templates/paper/figure-tracker.md` and treat its
`figure_registry` frontmatter as the schema source of truth. Keep the registry
machine-readable for paper-quality scoring; do not invent ad hoc keys or collapse
it into prose.

For each planned figure:

1. Read `${PAPER_DIR}/FIGURE_TRACKER.md`.
2. Locate source data from manifest-bound or project-backed evidence.
3. Generate or refresh a publication-styled script/output under
   `${PAPER_DIR}/figures/`.
4. Update figure status only after the output file exists.
5. Verify every outline-referenced figure exists as a file.

If figure data is missing for a central claim, stop with a claim/evidence blocker
and name the phase, intake binding, or source artifact that must be repaired.
</generate_figures>

<draft_sections>
Resolve the paper-writer model override before spawning section writers.

Drafting order:

1. Wave 1: Results + Methods in parallel when independent.
2. Wave 2: Introduction after Results is framed.
3. Wave 3: Discussion after Results + Methods.
4. Wave 4: Conclusions.
5. Wave 5: Abstract last.
6. Wave 6: Appendices as needed.

After each drafting wave, optionally run a local compilation smoke check if a
compiler is available:

```bash
cd "${PAPER_DIR}"
pdflatex -interaction=nonstopmode "${MANUSCRIPT_BASENAME}" 2>&1 | tail -20
```

Skip this check if `PDFLATEX_AVAILABLE` is false. `gpd paper-build` remains the
source of build truth either way.

Before spawning each wave, check whether expected `.tex` outputs already exist.
Existing `.tex` files can make a resumed wave current, but they are not fresh
child handoff success. Treat the emitted `.tex` file as the success artifact gate
for each section only after the tuple passes.

For each section, load the manifest conditional
`{GPD_INSTALL_DIR}/references/orchestration/runtime-delegation-note.md` when
`writer_spawn_needed`, then spawn a writer agent:

```
task(
  prompt="First, read {GPD_AGENTS_DIR}/gpd-paper-writer.md for your role and instructions.\n\n<autonomy_mode>{AUTONOMY}</autonomy_mode>\n<research_mode>{RESEARCH_MODE}</research_mode>\n" + section_prompt,
  subagent_type="gpd-paper-writer",
  model="{writer_model}",
  readonly=false,
  description="Draft: {section_name}"
)
```

Section writer child gate:

```yaml
child_gate:
  id: "write_paper_section_writer"
  role: "gpd-paper-writer"
  return_profile: "paper_writer"
  required_status: "completed"
  expected_artifacts:
    - "${PAPER_DIR}/{section_path}.tex"
  allowed_roots:
    - "${PAPER_DIR}"
  freshness_marker: "after $SECTION_WRITER_HANDOFF_STARTED_AT"
  validators:
    - "gpd validate handoff-artifacts - --expected ${PAPER_DIR}/{section_path}.tex --allowed-root ${PAPER_DIR} --required-suffix=.tex --require-status completed --require-files-written --fresh-after $SECTION_WRITER_HANDOFF_STARTED_AT"
    - "readable section file"
    - "claim/proof scope does not exceed passed proof-redteam artifacts"
  applicator: "none"
  failure_route: "stage-recovery-gate -> retry writer | main-context section drafting | stop or leave incomplete"
```

Run this tuple under `{GPD_INSTALL_DIR}/references/publication/stage-recovery-gate.md`;
section authoring is complete only after the emitted `.tex` path passes this
callsite tuple.

Each writer receives the paper context, section brief, narrative continuity,
evidence paths, active decisive-comparison artifacts, relevant
`${PAPER_DIR}/FIGURE_TRACKER.md` entries, passed proof-redteam artifacts for
theorem-style claims, and selected protocol-bundle handles as additive guidance
only.
If a tensor-network or other method-specific section needs a caveat, benchmark,
normalization, or scope judgment, the writer opens the relevant selected handle
first and drafts only from that bounded source.

Writer agents must not strengthen, generalize, or rhetorically smooth
theorem-style claims beyond passed proof-redteam scope. If a brief implies a
stronger theorem, stop and route to proof review.
</draft_sections>

<equation_presentation>
Equations in a published paper must be numbered when referenced, define every
symbol at first appearance, stay dimensionally consistent, use LaTeX best
practices, and be contextualized before and after the display.
</equation_presentation>

<figure_preparation>
Each figure must make exactly one point, be self-contained, use labeled axes with
units, include uncertainty where available, use manuscript notation, remain
readable in grayscale, and prefer vector formats for line plots.
</figure_preparation>

<handoff>
After section drafting, reload:

```bash
if [ -n "$WRITE_PAPER_ARGUMENTS" ]; then CONSISTENCY_INIT=$(gpd --raw init write-paper --stage consistency_and_references -- "$WRITE_PAPER_ARGUMENTS"); else CONSISTENCY_INIT=$(gpd --raw init write-paper --stage consistency_and_references); fi
```

Do not mark authoring complete until expected section files exist on disk and the
section child gates have passed.
</handoff>
