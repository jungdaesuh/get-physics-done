---
name: gpd:new-project
description: Initialize a new physics research project with deep context gathering and PROJECT.md
argument-hint: "[--auto] [--minimal [@file.md]]"
context_mode: projectless
allowed-tools:
  - file_read
  - shell
  - file_write
  - task
  - ask_user
help:
  group: Starter commands
  order: 40
  compact_description: Create a full GPD project
  display_signature: gpd:new-project
  variants:
    - command: gpd:new-project --minimal
      description: Create a GPD project through the shortest setup path
  detail_signature: gpd:new-project
  examples:
    - gpd:new-project --minimal
    - gpd:new-project --minimal @file.md
    - gpd:new-project --auto
  notes:
    - All modes build a scoping contract before downstream artifacts.
    - Blocking gaps get one targeted repair prompt, and scope must be explicitly approved before requirements or roadmap generation.
    - '`--minimal @file.md` still repairs blocking gaps and asks for scoping approval.'
    - '`--auto` follows the configured autonomy gates.'
    - '`GPD/state.json.bak` and `GPD/state.json.lock` are local recovery/coordination files.'
  root_detail_order: 10
---

<context>
**Flags:**
- `--auto` — Automatic mode. Synthesizes a scoping contract from the supplied document, asks for one explicit scope approval, then runs research → requirements → roadmap with minimal follow-up interaction. Expects a research proposal document via @ reference.
- `--minimal` — Fast staged-init mode. Uses one structured intake plus one scoping approval gate, then creates the core project artifacts with lean content. Scope, anchors, and decisive outputs are still required.
- `--minimal @file.md` — Create project directly from a markdown file describing your research and staged continuation path. Parses research question, anchors, and key work chunks from the file.

Mode-specific artifact lists, output displays, and completion checklists are
owned by the staged authorities, especially `completion`.
</context>

<objective>
Initialize a new physics research project through staged authorities: intake,
scoping contract approval, selected artifact generation, and completion.

**Minimal mode creates only the core startup set:** `GPD/PROJECT.md`, `GPD/config.json`, `GPD/REQUIREMENTS.md`, `GPD/ROADMAP.md`, `GPD/STATE.md`, and `GPD/state.json` with the approved `project_contract`. It does not promise `GPD/literature/` or `GPD/CONVENTIONS.md`.
Full mode may create `GPD/literature/` and `GPD/CONVENTIONS.md` only through
their owning later stages. roadmap generation and the staged roadmap/conventions handoff
happen only after the scoping approval gate.

**After this command:** Run `gpd:discuss-phase 1`.
</objective>

<execution_context>
@{GPD_INSTALL_DIR}/workflows/new-project/scope-intake.md
</execution_context>

<process>
**CRITICAL: First, read the included stage authority using the file_read tool:**
Start from the included `scope_intake` authority. It owns read-only setup,
recovery routing, existing-work routing, and the first narrow scope/anchor
question.
Start with physics questioning and do not surface a preset choice before
workflow preferences. In full/auto mode, `workflow_preferences` may ask for the
preset before the first project-artifact commit because `project_artifacts`
requires `GPD/config.json`.

Later stage loading is manifest/stage-owned. `scope_approval` owns `templates/project-contract-schema.md`, `templates/project-contract-grounding-linkage.md`, and canonical schema discipline. Never load `workflows/new-project.md` as authority; it is an index.

Execute the workflow end-to-end. Preserve all workflow gates (validation, approvals, routing).

## Flag Detection

Check `$ARGUMENTS` for flags:

- **`--auto`** → Structured synthesis + scope approval
- **`--minimal`** → Fast staged-init with scope approval
- **`--minimal @file.md`** → Minimal mode with input file

**If both `--auto` and `--minimal` are detected:** stop before any writes with:

```text
Error: --auto and --minimal cannot be combined.

Choose either `gpd:new-project --auto @proposal.md` for full auto intake or
`gpd:new-project --minimal [@file.md]` for the lean core-artifact path.
```

This conflict stop happens before git initialization, `GPD/` creation, or state/progress writes.

**If `--minimal` detected:** After Setup and existing-work routing, route to the **minimal staged initialization path**. It keeps intake to one response, still requires a scoping contract with decisive outputs and anchors, and creates the lean core artifact set without promising literature or convention files.

**If `--auto` detected:** After Setup, synthesize context from the provided document, repair blocking gaps only, present the scoping contract for approval, then run research → requirements → roadmap with smart defaults.

Do not initialize git in Setup. The workflow initializes git only at its first mutation gate after invalid arguments, existing-work routing, recovery routing, and explicit scope approval have all passed.
</process>

<success_criteria>

Stage-owned success criteria live in the active authority, with final display in
`workflows/new-project/completion.md`.

- [ ] invalid flag combinations stop before writes
- [ ] scoping contract is explicitly approved, validated, and persisted before downstream artifact generation
- [ ] User told the next step is `gpd:discuss-phase 1`

**Minimal mode success criteria (if `--minimal`):**

- [ ] Minimal output is limited to the documented core startup set; no literature or conventions artifact is promised
- [ ] User offered "Discuss phase 1 now?"

</success_criteria>
