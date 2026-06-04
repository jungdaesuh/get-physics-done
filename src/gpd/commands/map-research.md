---
name: gpd:map-research
description: Map existing research project — theoretical framework, computations, conventions, and open questions
argument-hint: "[optional: specific area to map, e.g., 'hamiltonian' or 'numerics' or 'perturbation-theory']"
context_mode: projectless
allowed-tools:
  - file_read
  - ask_user
  - shell
  - find_files
  - search_files
  - file_write
  - task
help:
  group: Starter commands
  order: 60
  compact_description: Map an existing research folder before planning
  display_signature: gpd:map-research
  detail_signature: gpd:map-research
  root_detail_order: 20
---

<objective>
Map an existing physics research project using parallel gpd-research-mapper agents.

Orchestrator role: validate the focus area, then hand off to the workflow-owned staged init, mapper fanout, and artifact gating. The workflow init stays bound to the current workspace: if the user is inside a nested verified GPD project, it walks up to that nearest project root; it does not auto-reenter a different recent project.
</objective>

<execution_context>
@{GPD_INSTALL_DIR}/workflows/map-research/map-bootstrap.md
</execution_context>

<context>
Focus area: $ARGUMENTS (optional - if provided, tells the workflow which subsystem, theory sector, or computational domain to emphasize)

Project state is loaded by the workflow from the current workspace or its nearest verified ancestor project root if one exists; this wrapper does not duplicate discovery logic or recent-project recovery.
</context>

<process>
Follow the included map-research bootstrap authority. Mapper authoring and artifact routing are manifest-owned by the active workflow stages; do not duplicate staged init, mapper fanout, or return routing here.
</process>
