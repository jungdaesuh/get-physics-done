---
name: gpd:decisions
description: Display and search the cumulative decision log
argument-hint: "[phase number or keyword]"
context_mode: project-required
requires:
  files: ["GPD/STATE.md"]
allowed-tools:
  - file_read
  - shell
  - search_files
  - find_files
help:
  group: Tangents, memory, and exports
  order: 560
  compact_description: Search the decision log
  display_signature: gpd:decisions [phase or keyword]
---


<objective>
Display the cumulative decision log from `GPD/DECISIONS.md`, optionally filtered by phase number or keyword.
  </objective>

<execution_context>
@GPD/STATE.md
@{GPD_INSTALL_DIR}/workflows/decisions.md
</execution_context>

<process>
Follow the included decisions workflow exactly.
   </process>
