<purpose>
Bootstrap `gpd:research-phase`: validate the requested phase, gather only
phase-level context, resolve model/depth, and reload `research_handoff` before
spawning the researcher.
</purpose>

<process>

## Step 0: Initialize Context

**Load phase context and resolve model:**

```bash
load_research_phase_stage() {
  local stage_name="$1"
  local phase_arg="$2"
  local init_payload=""

  init_payload=$(gpd --raw init research-phase "${phase_arg}" --stage "${stage_name}" 2>/dev/null)
  if [ $? -ne 0 ] || [ -z "$init_payload" ]; then
    echo "ERROR: staged gpd initialization failed for stage '${stage_name}': ${init_payload}"
    return 1
  fi

  printf '%s' "$init_payload"
  return 0
}

BOOTSTRAP_INIT=$(load_research_phase_stage phase_bootstrap "${PHASE}")
if [ $? -ne 0 ]; then
  echo "ERROR: gpd initialization failed: $BOOTSTRAP_INIT"
  # STOP; surface the error.
fi
```

Apply `BOOTSTRAP_INIT.staged_loading.field_access_instruction` before reading
`BOOTSTRAP_INIT`.

Extract from init JSON: `phase_dir`, `phase_number`, `phase_name`,
`phase_found`, `autonomy`, `research_mode`, and the contract gate fields.

```bash
RESEARCH_MODE=$(echo "$BOOTSTRAP_INIT" | gpd json get .research_mode --default balanced)
```

The init-derived `RESEARCH_MODE` is the single source of truth for depth; do not re-query config later in the workflow.

**If `phase_found` is false:** Error and exit.

**Mode-aware behavior:** explore broadens methods and literature; exploit uses
direct methods only; balanced uses standard depth; adaptive narrows only after
decisive prior evidence or an explicit approach lock. Supervised reviews
`RESEARCH.md`; balanced/yolo accept only after the artifact gate passes.

@{GPD_INSTALL_DIR}/references/orchestration/model-profile-resolution.md

```bash
RESEARCHER_MODEL=$(gpd resolve-model gpd-phase-researcher)
```

## Step 1: Validate Phase

```bash
PHASE_INFO=$(gpd --raw roadmap get-phase "${phase_number}")
```

If `found` is false: Error and exit. Extract `goal` and `section` from JSON.

## Step 2: Check Existing Research

```bash
ls "${phase_dir}/"*-RESEARCH.md 2>/dev/null
```

If exists: Offer update/view/skip options.

## Step 3: Gather Phase Context

```bash
# Phase section from roadmap (already loaded in PHASE_INFO)
echo "$PHASE_INFO" | gpd json get .section --default ""
cat GPD/REQUIREMENTS.md 2>/dev/null
cat "${phase_dir}/"*-CONTEXT.md 2>/dev/null
# Decisions from gpd state snapshot (structured JSON)
gpd --raw state snapshot | gpd json get .decisions --default "[]"
```
## Stage Handoff: Research Handoff

After phase validation, existing-research routing, and context gathering are complete, reload `research_handoff` before assembling the child prompt:

```bash
HANDOFF_INIT=$(load_research_phase_stage research_handoff "${phase_number}")
if [ $? -ne 0 ]; then
  echo "ERROR: gpd initialization failed: $HANDOFF_INIT"
  exit 1
fi
```

Apply `HANDOFF_INIT.staged_loading.field_access_instruction` before reading
`HANDOFF_INIT`.

Read only `HANDOFF_INIT.staged_loading.eager_authorities`, primarily
`workflows/research-phase/research-handoff.md`, plus the listed references. Do
not continue from bootstrap memory into the researcher handoff.

</process>
