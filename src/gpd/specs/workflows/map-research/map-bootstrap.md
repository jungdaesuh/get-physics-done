<purpose>
Bootstrap `gpd:map-research`: resolve project-rooted `GPD/research-map/`, route
existing maps, create/update the output directory, then reload
`mapper_authoring` before mapper fanout. Mapper agents write the 7 map documents.
</purpose>

<philosophy>
Bootstrap only routes and prepares the project-rooted output directory; mapper
authoring handles quality, templates, path discipline, and coverage.
</philosophy>

<process>

Runtime label: Show `gpd:` as native labels; keep local CLI `gpd ...` unchanged.

<step name="init_context" priority="first">
Load research mapping context:

```bash
load_map_research_stage() {
  local stage_name="$1"
  local init_payload=""
  local target_cwd="${PROJECT_ROOT:-$PWD}"

  if [ -n "${ARGUMENTS:-}" ]; then
    init_payload=$(gpd --raw --cwd "$target_cwd" init map-research --stage "${stage_name}" -- "${ARGUMENTS:-}" 2>/dev/null)
  else
    init_payload=$(gpd --raw --cwd "$target_cwd" init map-research --stage "${stage_name}" 2>/dev/null)
  fi
  if [ $? -ne 0 ] || [ -z "$init_payload" ]; then
    echo "ERROR: staged gpd initialization failed for stage '${stage_name}': ${init_payload}"
    return 1
  fi

  printf '%s' "$init_payload"
  return 0
}

BOOTSTRAP_INIT=$(load_map_research_stage map_bootstrap)
if [ $? -ne 0 ]; then
  echo "ERROR: gpd initialization failed: $BOOTSTRAP_INIT"
  # STOP; surface the error.
fi

PROJECT_ROOT=$(echo "$BOOTSTRAP_INIT" | gpd json get .project_root --default "")
WORKSPACE_ROOT=$(echo "$BOOTSTRAP_INIT" | gpd json get .workspace_root --default "")
RESEARCH_MAP_DIR=$(echo "$BOOTSTRAP_INIT" | gpd json get .research_map_dir --default "GPD/research-map")
RESEARCH_MAP_DIR_ABS=$(echo "$BOOTSTRAP_INIT" | gpd json get .research_map_dir_absolute --default "")
if [ -z "$PROJECT_ROOT" ] || [ -z "$RESEARCH_MAP_DIR_ABS" ]; then
  echo "ERROR: map-research init did not return project_root and research_map_dir_absolute"
  # STOP; surface the error.
fi
```

Apply `BOOTSTRAP_INIT.staged_loading.field_access_instruction` before reading `BOOTSTRAP_INIT`; it is the canonical bootstrap field policy, including `project_contract_gate`.
`{GPD_INSTALL_DIR}/references/orchestration/contract-authority-gate.md`

Filesystem gate: use `PROJECT_ROOT` / `RESEARCH_MAP_DIR_ABS` from staged init for create, archive, verify, delete, or commit actions. Never target `GPD/research-map` relative to the launch cwd; nested launches still target the resolved project root.

**Read mode settings:**

```bash
RESEARCH_MODE=$(echo "$BOOTSTRAP_INIT" | gpd json get .research_mode --default balanced)
```

`RESEARCH_MODE` controls depth. Preserve contract-critical anchors, prior
baselines, and user-mandated references. Contract gate: `project_contract` is
authoritative only when `project_contract_gate.authoritative` is true; otherwise
keep gate/load/validation visible. If `map_focus_provided` is true, keep
`map_focus` visible and bias slices without losing required coverage. Map focus:
{map_focus}

Mapper handoff gate: each mapper is one-shot and file-producing. Route on
`gpd_return.status`, then verify `gpd_return.files_written` against expected
artifacts before accepting the run.
</step>

<step name="check_existing">
Use `has_maps` and `research_map_dir_exists` from init context.

If `research_map_dir_exists` is true:

```bash
ls -la "$RESEARCH_MAP_DIR_ABS/"
```

**If exists:**

```
GPD/research-map/ already exists at:
{research_map_dir_absolute}

Existing documents:
[List files found]

What's next?
- option_id: refresh_archive - archive existing map beside it, create a new empty map, remap.
- option_id: update_selected - keep existing files and update selected documents.
- option_id: skip_existing - use existing research map as-is.
```

Wait for user response and route by exact `option_id`, not option number or label.

Routes:
- `refresh_archive`: archive, create a fresh directory, then continue to
  `create_structure`.
- `update_selected`: ask for explicit document IDs from only `FORMALISM.md`,
  `REFERENCES.md`, `ARCHITECTURE.md`, `STRUCTURE.md`, `CONVENTIONS.md`,
  `VALIDATION.md`, `CONCERNS.md`; require at least one valid ID and store
  `UPDATE_SELECTED_DOCS`.
- `skip_existing`: exit workflow.

```bash
RESEARCH_MAP_ARCHIVE_DIR="${RESEARCH_MAP_DIR_ABS}.archive-$(date +%Y%m%d-%H%M%S)"
if [ -e "$RESEARCH_MAP_ARCHIVE_DIR" ]; then
  RESEARCH_MAP_ARCHIVE_DIR="${RESEARCH_MAP_ARCHIVE_DIR}-$$"
fi
mv "$RESEARCH_MAP_DIR_ABS" "$RESEARCH_MAP_ARCHIVE_DIR"
mkdir -p "$RESEARCH_MAP_DIR_ABS"
echo "Archived previous research map at: $RESEARCH_MAP_ARCHIVE_DIR"
```

For `update_selected`, spawn only slices owning selected documents; intersect
each selected mapper's `allowed_paths`, `expected_artifacts`, and accepted
`gpd_return.files_written` with `UPDATE_SELECTED_DOCS`. Keep unselected map
documents byte-for-byte unchanged; fail closed on any unexpected write.

**If doesn't exist:**
Continue to create_structure.
</step>

<step name="create_structure">
Create the project-rooted research-map directory:

```bash
mkdir -p "$RESEARCH_MAP_DIR_ABS"
```

Expected output files: `FORMALISM.md`, `REFERENCES.md`, `ARCHITECTURE.md`,
`STRUCTURE.md`, `CONVENTIONS.md`, `VALIDATION.md`, `CONCERNS.md`.

Continue to spawn_agents.
</step>
<step name="handoff_to_mapper_authoring">
When existing-map routing and directory setup are complete, reload `mapper_authoring` before spawning mapper agents.

```bash
MAPPER_AUTHORING_INIT=$(load_map_research_stage mapper_authoring)
if [ $? -ne 0 ]; then
  echo "ERROR: gpd initialization failed: $MAPPER_AUTHORING_INIT"
  exit 1
fi
```

Apply `MAPPER_AUTHORING_INIT.staged_loading.field_access_instruction`, then follow `workflows/map-research/mapper-authoring.md`; do not continue from bootstrap memory into mapper fanout.
</step>

</process>
