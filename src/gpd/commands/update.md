---
name: gpd:update
description: Update GPD to latest version with changelog display
context_mode: global
allowed-tools:
  - shell
  - ask_user
help:
  group: Configuration and maintenance
  order: 710
  compact_description: Update GPD to the latest version
  display_signature: gpd:update
  notes:
    - Runs the public bootstrap update command for the active runtime.
    - Preserves local modifications via patch backups.
  root_detail_order: 340
---


<objective>
Check for GPD updates, install if available, and display what changed.
  </objective>

<execution_context>
@{GPD_INSTALL_DIR}/workflows/update.md
</execution_context>

<process>
Follow the included update workflow exactly.
   </process>
