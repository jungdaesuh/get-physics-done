# Agent Module Loading

Use this reference when an agent or workflow needs extra prompt guidance without
putting every possible checklist into the first turn. Module loading is a
prompt-level discipline: stages decide what may be loaded, metadata tells the
agent where to load it from, and the agent reads module bodies only when the
active task needs them.

## Core Contract

- Stage first. Always run the workflow's active staged init entrypoint, then
  treat `payload.staged_loading` as the authority map for the current stage.
- Metadata only. Staged init payloads may name selected module ids, roles,
  portable asset paths, reasons, costs, and required/optional status. They must
  not include module bodies, pasted checklists, or transitive markdown content.
- JIT reads only. Load a module body only after the active stage permits it and
  the current task needs it. Do not read everything in a registry or directory.
- Respect negative gates. Anything in `staged_loading.must_not_eager_load` stays
  unread until a later stage makes it eager.
- No invented fields. If `module_load_manifest` is absent, use the staged
  authorities and selected protocol-bundle metadata already present. Do not
  synthesize module selections from memory or prose.

## Loading Order

1. Run the stage-specific init command for the workflow.
2. Inspect `payload.staged_loading.workflow_id`, `stage_id`,
   `required_init_fields`, `eager_authorities`, `must_not_eager_load`, and
   `next_stages`.
3. Read only `staged_loading.eager_authorities` for the active stage.
4. If the payload includes `module_load_manifest`, inspect it as a selected
   loading map, not as content to paste into the prompt.
5. Load only the module assets required by the current task, proof/numerical/
   publication flags, or selected protocol bundle assets.
6. Move to another stage only through `staged_loading.next_stages`, then rerun
   staged init and repeat the selection process.

## Module Manifest Shape

A module-loading manifest is compatible with this reference when it is bounded,
selected, and body-free:

```yaml
module_load_manifest:
  schema_version: 1
  selection_source: staged_context
  workflow_id: execute-phase
  stage_id: wave_planning
  selected_module_ids:
    - proof.redteam
  modules:
    - module_id: proof.redteam
      role: proof_verification
      asset_path: references/verification/core/proof-redteam-protocol.md
      portable_path: "@{GPD_INSTALL_DIR}/references/verification/core/proof-redteam-protocol.md"
      required: true
      reason: proof_flag
      source: module_registry
      cost: medium
```

Allowed prompt-facing metadata: `module_id`, `role`, `asset_path`,
`portable_path`, `required`, `reason`, `source`, `cost`, and bounded depth hints.
Disallowed payload content: markdown bodies, pasted checklists, full catalogs,
transitive include expansion, and unselected module text.

If a future stage exposes a rendered `module_policy_summary`, the corresponding
payload must also expose `module_load_manifest`; the structured manifest remains
authoritative.

## Selector Rules

- Stage is the outer gate. Task kind, task flags, research mode, model profile,
  autonomy, and selected protocol bundles may select within the stage's allowed
  set; none may bypass the stage.
- Proof-bearing tasks require proof/assumption/claim-trace modules in
  verification or publication stages. Exploration stages may load lighter
  variants, but proof gates stay fail-closed once claims are being checked.
- Numerical or computational tasks require convergence, uncertainty,
  reproducibility, benchmark, or analytic-limit modules when numerical claims
  are verified or published.
- Publication tasks may select paper, figure/table, bibliography,
  reproducibility, and referee-response modules only in publication-capable
  stages or explicit publication work.
- Research mode changes breadth versus convergence pressure. It does not change
  the active stage or remove required proof/numerical/publication modules.
- Model profile may bias optional modules and depth. It does not override
  workflow contracts or required task-flag modules.
- Autonomy controls checkpoint and interruption pressure. It must not suppress
  correctness, proof, numerical, or publication modules required by task flags.

## Protocol-Bundle Compatibility

Selected protocol bundles are additive module sources, not a replacement loader.
When `protocol_bundle_load_manifest` is present:

- Treat it as the source of truth for selected bundle assets.
- Compose selected bundle assets into module decisions with
  `source: protocol_bundle`.
- Preserve bundle roles such as `planning_guides`, `checklists`,
  `verifier_extensions`, and `references`.
- Keep `protocol_bundle_context` as a compact summary. It is not a body loader.
- Do not load unselected bundle assets, flat bundle catalogs, or protocol bodies
  just because a bundle registry exists.

If no selected bundle covers the task, fall back to shared staged authorities and
required cross-cutting modules selected by the active task flags.

## Compactness Rules

- Bootstrap stages should normally stay module-free.
- Module fields must appear only when selected by `required_init_fields`.
- Prefer structured manifests over prose summaries.
- Bound or omit omitted-module debug lists.
- Keep transitive references metadata-only unless a later stage or explicit task
  makes a specific body necessary.
