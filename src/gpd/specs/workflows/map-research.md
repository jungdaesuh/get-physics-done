<purpose>
Compatibility index for the staged `map-research` workflow.
</purpose>

<stage_authority_index>
The active authority is selected by `map-research-stage-manifest.json`. Do not load this index as a stage authority.

- `map_bootstrap` -> `workflows/map-research/map-bootstrap.md`
  Project-root discovery, optional focus handling, existing-map routing, selected-document update routing, and project-rooted `GPD/research-map/` directory setup.
- `mapper_authoring` -> `workflows/map-research/mapper-authoring.md`
  Runtime delegation, contract/reference context, four parallel `gpd-research-mapper` handoffs, artifact verification, secret scanning, commit, and completion summary.
</stage_authority_index>

<stage_loading_rule>
The public command includes only `workflows/map-research/map-bootstrap.md`; mapper-authoring loading is manifest-owned by the active staged payload.
</stage_loading_rule>

<canonical_references>
Mapper agents use `{GPD_INSTALL_DIR}/references/templates/research-mapper/` for the document templates:
`FORMALISM.md`, `REFERENCES.md`, `ARCHITECTURE.md`, `STRUCTURE.md`, `CONVENTIONS.md`, `VALIDATION.md`, and `CONCERNS.md`.
</canonical_references>
