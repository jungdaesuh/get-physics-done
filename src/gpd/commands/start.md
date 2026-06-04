---
name: gpd:start
description: Choose the right first GPD action for this folder and route into the real workflow
argument-hint: "[optional short goal]"
context_mode: projectless
allowed-tools:
  - file_read
  - shell
  - ask_user
help:
  group: Starter commands
  order: 20
  compact_description: Guided first-run router for the safest first path in the current folder
  display_signature: gpd:start
---


<objective>
Provide a beginner-friendly first-run entry point for GPD.

Inspect the current folder, show the safest next step first, then explain the broader options in plain language. Keep the language novice-friendly, explain official terms the first time they appear, and do not invent a parallel onboarding state machine.
</objective>

<execution_context>
@{GPD_INSTALL_DIR}/workflows/start.md
</execution_context>

<arguments>
Requested choice or short goal: $ARGUMENTS
</arguments>

<inline_guidance>

@{GPD_INSTALL_DIR}/references/onboarding/beginner-command-taxonomy.md

`gpd resume` remains the local read-only current-workspace recovery snapshot; `gpd resume --recent` remains the normal-terminal advisory recent-project picker; choose the workspace there, then `gpd:resume-work` reloads canonical state in the reopened project. `gpd:suggest-next` is the fastest post-resume next command when you only need the next action. `gpd:suggest-next`, `gpd:quick`, `gpd:explain`, and `gpd:help` remain separate downstream entry points.

</inline_guidance>

<process>
Follow the included start workflow end-to-end. Preserve the routing-first rule: detect the folder state, show plain-language choices, then hand off to the real existing workflow instead of duplicating its logic here.

In one-shot or headless runtime prompts, render the first chooser as plain text and stop instead of calling a structured input tool that cannot receive a reply. If the same user message that invokes `gpd:start` already includes an explicit choice such as `tour`, `fast start`, `full guided setup`, or the matching choice number after the command label, treat that text as the user's answer and route once through the normal choice mapping instead of stopping at the chooser. Add `Reply with the number or the option name.` and do not choose an option, infer approval, create files, or route into a downstream command until the user answers. A same-message explicit choice counts only as the chooser answer. It is not downstream write approval and not approval for downstream intake, scope approval, file creation, git initialization, state repair, map creation, mapper spawning, progress writes, or executing a recommended next action. Surrounding automation instructions, goals, or explanations do not count as chooser answers or downstream approval.
</process>
