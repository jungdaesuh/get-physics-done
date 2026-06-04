<purpose>
Provide a beginner-friendly read-only tour. Teach what the main commands do, when to use them, and what GPD can do before choosing a setup path. Default is short; `--all` and `--reference` are the longer guided tour/reference view. In every mode, this tour does not create files, change project state, or route into another workflow.
</purpose>

<process>

<step name="parse_arguments">
Inspect `$ARGUMENTS`.

- If `$ARGUMENTS` contains `--all` or `--reference`, render `all_reference_tour`.
- If `$ARGUMENTS` is empty, render `default_contextual_tour`.
- Other text: render `default_contextual_tour` and show one context line.

Do not narrow the command list, select a path, or route based on non-flag context. Unknown flags are context only unless they are exactly `--all` or `--reference`.
</step>

<step name="shared_orientation">
Open with this exact sentence:

`This is a read-only tour of the main GPD commands. It will not change your files.`

Explain terminal vs runtime: normal terminal for install/setup; the runtime, where you use the GPD command prefix provided for that runtime. Runtime label: Show `gpd:` as native labels; keep local CLI `gpd ...` unchanged.

Keep the shared beginner ladder visible. `gpd:start` owns folder state, actual path, and setup routing; `gpd:tour` only explains.

@{GPD_INSTALL_DIR}/references/shared/onboarding-command-boundaries.md
</step>

<step name="default_contextual_tour">
Use this mode for empty `$ARGUMENTS` and for non-flag context.

Hard limits: 80 lines or fewer, 4500 characters or fewer, no full command reference, and no 12-row core-path table.

After the exact read-only opener and optional context line, include a compact section titled `Which path fits?` with at most this five-row table:

| Command | Use this when | Example |
| --- | --- | --- |
| `gpd:start` | you are unsure or just opened a workspace | "What now?" |
| `gpd:tour` | you want the map without action | "Explain first." |
| `gpd:new-project --minimal` | genuinely new folder, fast setup | "Start from this idea." |
| `gpd:map-research` | the folder already has papers, notes, or code | "Map this first." |
| `gpd:resume-work` | this is already a GPD project | "Continue saved work." |

Add a short `Terminal vs runtime` note: runtime commands look like `gpd:start`; local terminal commands look like `gpd doctor`, `gpd --version`, or `gpd resume`; Use `gpd resume` first before `gpd:resume-work` if reopening is needed.

Add three `After startup` bullets:

- Status and next step: `gpd:progress`, then `gpd:suggest-next`.
- Preferences/models: `gpd:settings` after your first successful start or later, or `gpd:set-tier-models` for direct tier ids.
- References: `gpd:tour --all` for the longer guided tour, and `gpd:help --all` for the compact command index.

Close with:

- "If you are still unsure, run `gpd:start`."
- "If you want the longer tour/reference table, run `gpd:tour --all`."
- "If you want the complete command index, run `gpd:help --all`."
</step>

<step name="all_reference_tour">
Use this mode only for `--all` or `--reference`. Keep the exact read-only opener. State that this is the longer guided tour/reference view and that `gpd:help --all` remains the canonical complete command index.
</step>

<step name="explain_the_core_paths">
Only use this step in `all_reference_tour`.

Use a compact table with four columns:

- Command
- Use this when
- Do not use this when
- Example

Include these entries:

- `gpd:start`
- `gpd:new-project --minimal`
- `gpd:new-project`
- `gpd:map-research`
- `gpd:resume-work`
- `gpd:progress`
- `gpd:suggest-next`
- `gpd:explain <topic>`
- `gpd:quick`
- `gpd:set-tier-models`
- `gpd:settings`
- `gpd:help`

Keep this table runtime-facing only. Do not include normal-terminal-only commands such as `gpd resume`; explain them later in the terminal/runtime distinction. Keep examples short.
</step>

<step name="show_broader_capabilities">
Only use this step in `all_reference_tour`.

Add `What comes later after startup`. These are later capability groups:

- project work: `gpd:discuss-phase`, `gpd:plan-phase`, `gpd:execute-phase`, `gpd:verify-work`
- writing and review: `gpd:write-paper`, `gpd:peer-review`, `gpd:respond-to-referees`, `gpd:arxiv-submission`
- side investigations/preferences: `gpd:tangent`, `gpd:branch-hypothesis`, `gpd:set-profile`, and the settings/model commands from the startup table

Keep this high-level, not a second full command reference.
</step>

<step name="distinguish_terminal_and_runtime">
Add `Normal terminal vs runtime`. Explain:

- The normal terminal is where you install GPD, run `gpd --help`, and run checks like `gpd doctor`.
- The runtime is the AI terminal app for runtime-specific GPD commands.
- `gpd resume` is the normal-terminal recovery step for reopening the right workspace; `gpd:resume-work` continues inside it.
- `gpd:settings` changes preferences; `gpd:set-tier-models` pins concrete `tier-1`, `tier-2`, and `tier-3` model ids.
- `gpd:tour` only explains; it does not run `gpd:start`, `gpd:new-project`, `gpd:map-research`, `gpd:resume-work`, or configuration commands for you.
- `Use \`gpd resume\` first if you need to reopen the project before using \`gpd:resume-work\`.`
</step>

<step name="highlight_common_mistakes">
Only use this step in `all_reference_tour`.

Call out beginner traps plainly:

- Use `gpd:start` when you are still deciding, not `gpd:new-project`
- Use `gpd:new-project` only for genuinely new folders
- Use `gpd:map-research` for an existing folder with papers, notes, or code, not an empty folder
- Use `gpd:resume-work` only when the project already has GPD state
- Use `gpd:set-profile` when you want to change the abstract research profile
- Use `gpd:help` when you want the command reference, not a setup wizard
</step>

<step name="explain_advanced_terms">
Only use this step in `all_reference_tour`.

Add `A few terms in plain English`.

- `runtime` - the AI terminal app receiving GPD commands
- `GPD project` - a folder where GPD saved project files and state
- `research map` - GPD's summary of existing work before full setup
- `map-research` - examine an existing research folder before planning
- `phase` - one chunk of the project plan
- `resume-work` - continue an existing GPD project from where it left off
- `read-only` - it explains things without making changes
</step>

<step name="close_with_next_steps">
Only use this step in `all_reference_tour`.

End with:

- "If you are still unsure, run `gpd:start`."
- "If you want the shorter contextual tour again later, run `gpd:tour`."
- "If you want the complete command index, run `gpd:help --all`."
- "If you already know your path, use the matching command from the table above."

Do not ask the user to pick a branch and do not continue into another workflow.
</step>

<success_criteria>
- [ ] Default response is under 80 lines and 4500 characters
- [ ] `--all` and `--reference` use the longer guided tour/reference mode
- [ ] `gpd:help --all` remains the canonical complete command index
- [ ] The response is read-only, non-routing, and ends with simple next-step guidance
</success_criteria>
