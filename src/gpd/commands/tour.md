---
name: gpd:tour
description: Show a guided beginner walkthrough of the core GPD commands without taking action
argument-hint: "[optional short goal | --all | --reference]"
context_mode: projectless
allowed-tools:
  - file_read
help:
  group: Starter commands
  order: 30
  compact_description: Show a read-only overview of the main commands
  display_signature: gpd:tour
---


<objective>
Provide a safe beginner walkthrough of the core GPD command paths. Keep default
output short; use `--all` or `--reference` for the longer reference view. Do
not create project artifacts, create files, or silently route into another
workflow.
</objective>

<execution_context>
@{GPD_INSTALL_DIR}/workflows/tour.md
</execution_context>

<inline_guidance>

@{GPD_INSTALL_DIR}/references/onboarding/beginner-command-taxonomy.md

- `gpd:tour` is a teaching surface, not a chooser
- `gpd:tour --all` and `gpd:tour --reference` show the longer guided tour/reference table
- `gpd:help --all` is the canonical compact command index
- Common follow-ups: `gpd:progress`, `gpd:suggest-next`, `gpd:explain`, `gpd:quick`, `gpd:set-tier-models`, `gpd:settings`, `gpd:help`

</inline_guidance>

<process>
Follow the included tour workflow and its mode split: default/non-flag context
is short; `--all` or `--reference` is the longer table. Start with this exact
opener: `This is a read-only tour of the main GPD commands. It will not change
your files.` Use runtime-native command labels, including `gpd:start`,
`gpd:tour`, and `gpd:help` after projection. Reference mode points to
`gpd:help --all` for the complete command index. Do not answer a chooser, infer
setup, hand off, create artifacts, or route into a follow-up command.
</process>
