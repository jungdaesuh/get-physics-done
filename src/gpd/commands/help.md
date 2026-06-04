---
name: gpd:help
description: Show available GPD commands and usage guide
argument-hint: "[--all | --command <name>]"
context_mode: global
help:
  group: Starter commands
  order: 10
  compact_description: Show the quick start or command index
  display_signature: gpd:help
---


<objective>
Display GPD help by delegating to the renderer-backed local CLI help bridge, with the workflow-owned help surface and generated detail reference as marker fallbacks.

Return only reference content. Do not add project analysis, git status, next steps, or commentary.
</objective>

Shared wrapper rule: use the bridge first; fallback extracts preserve workflow marker text without rewriting or invented wording.
Use the workflow-owned help surface as the marker fallback when the bridge is unavailable.

Bridge command rule: run local CLI raw help for the requested mode, parse JSON, and return renderer-backed markdown/fields.

- `@{GPD_INSTALL_DIR}/workflows/help.md` - Fallback marker source path; do not inline it here.
- `@{GPD_INSTALL_DIR}/references/help/detailed-command-reference.md` - Fallback full detail source path for `--command <name>`; do not inline it here.

Use the workflow-owned stable markers as the extraction boundaries for fallback mode:

- `<!-- gpd-help:default:start -->` / `<!-- gpd-help:default:end -->`
- `<!-- gpd-help:quick-start:start -->` / `<!-- gpd-help:quick-start:end -->`
- `<!-- gpd-help:command-index:start -->` / `<!-- gpd-help:command-index:end -->`
- `<!-- gpd-help:detailed-command-reference:start -->` / `<!-- gpd-help:detailed-command-reference:end -->`

Return marker contents only; never print the HTML marker comments themselves. Visible headings inside marker ranges are output labels only.

Runtime command-surface note: refer to the command that invoked this wrapper as "this help command"; do not print adapter-specific examples.

<process>

## Step 1: Parse Arguments

Check whether the user passed `--command <name>` or `--all`.

- If `$ARGUMENTS` contains `--command <name>`: display the **Single Command Detail Extract** (step 4).
- If `$ARGUMENTS` contains `--all` and does not contain `--command <name>`: display the **Compact Command Index** (step 3).
- If `$ARGUMENTS` is empty or contains neither `--all` nor `--command <name>`: display the **Quick Start Extract** (step 2) only.

## Step 2: Quick Start Extract (Default Output)

Preferred bridge path:

```bash
gpd --raw help
```

- Parse JSON field `quick_start.markdown`.
- Output ONLY that markdown.
- Append this one wrapper-owned line: `Run this help command with --all for the compact command index.`

Workflow-owned reference fallback:

- Extract from `<!-- gpd-help:default:start -->` through `<!-- gpd-help:default:end -->`.
- Exclude the marker comment lines themselves.
- Do not output adapter-specific examples.
- Append this one wrapper-owned line: `Run this help command with --all for the compact command index.`

Then STOP.

## Step 3: Compact Command Index (--all)

Preferred bridge path:

```bash
gpd --raw help --all
```

- Parse JSON fields `quick_start.markdown`, `command_index_markdown`, and `detailed_help_follow_up`.
- Output the quick-start markdown, then the command-index markdown.
- Replace the generic detailed-help follow-up with this one wrapper-owned line: `Run this help command with --command <name> for detailed help on one command.`

Workflow-owned reference fallback:

- Extract from `<!-- gpd-help:quick-start:start -->` through `<!-- gpd-help:command-index:end -->`.
- Exclude the marker comment lines themselves.
- Do not output adapter-specific examples.
- Append this one wrapper-owned line: `Run this help command with --command <name> for detailed help on one command.`

Then STOP.

## Step 4: Single Command Detail Extract (--command <name>)

- Parse the command name after `--command`.
- Accept bare names, canonical runtime commands, and the current runtime's native command label.
- If lookup includes inline flags or arguments such as `gpd:new-project --minimal`, split them and normalize to the base command block.

Preferred bridge path:

```bash
gpd --raw help --command <name>
```

- Pass through the normalized command name after `--command`.
- If the bridge returns `ok: false` with `error: "unknown_command"`, output this one line and STOP: `Unknown command. Run this help command with --all for the compact command index.`
- If the bridge returns `detail_markdown`, output that renderer-owned markdown without rewriting it.
- Otherwise render a compact detail block from `canonical_command`, `description`, `argument_hint`, `context_mode`, `project_reentry_capable`, `requires`, and `allowed_tools`.
- Include command-context preflight fields when present, including the read-only runtime-owned permission snapshot / runtime-owned permission alignment metadata projected from canonical command policy.

Workflow-owned reference fallback:

- Prefer the generated detail reference file. Normalize to the matching canonical command inside its detailed-command marker range (`<!-- gpd-help:detailed-command-reference:start -->` / `<!-- gpd-help:detailed-command-reference:end -->`), whose visible heading is `## Detailed Command Reference`.
- If the generated detail reference file is unavailable, use the root workflow help marker with the same detailed-command marker range as a compact fallback slice.
- Output ONLY the smallest matching detailed command block.
- Include the nearest containing section heading (for example `### Phase Planning`) plus the matching command block.
- Include matching `Flags:`, `Usage:`, and `Result:` lines that belong to that command when present.
- Stop before the next command block begins.
- If no command matches after normalization, output this one line and STOP: `Unknown command. Run this help command with --all for the compact command index.`
</process>
