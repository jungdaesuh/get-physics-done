# GPD Onboarding Hub

Use this page as the single first-stop for new users.

Use it to pick one OS guide and one runtime guide. The exact install,
startup, and return-to-work commands live in those guides.
Use the next section for the beginner preflight and caveats before you choose.

## Before you open the guides

Make sure these are already true:

<!-- gpd-public-surface:beginner-preflight:start -->
- One supported runtime is already installed and can open from your normal terminal.
- Node.js 20+ is available in that same terminal.
- Python 3.11+ with the standard `venv` module is available there too.
<!-- gpd-public-surface:beginner-preflight:end -->

- Use `--local` while learning so GPD only affects the current folder.
- Normal installs and `--reinstall` use the PyPI pinned release first, with tagged GitHub release sources only as fallback. `--upgrade` opts into the latest unreleased GitHub `main` source.

<details>
<summary>What this hub does not do</summary>

<!-- gpd-public-surface:beginner-caveats:start -->
- GPD is not a standalone app.
- GPD does not install your runtime for you.
- GPD does not include model access, billing, or API credits.
- This hub is the beginner path, not the full reference.
- If evidence, references, or artifacts are missing, say so explicitly; GPD should not invent them.
<!-- gpd-public-surface:beginner-caveats:end -->

</details>

<details>
<summary>Show the full beginner path on one page</summary>

Use this one-line path:

<!-- gpd-public-surface:beginner-startup-ladder:start -->
`help -> start -> tour -> new-project / map-research -> resume-work`
<!-- gpd-public-surface:beginner-startup-ladder:end -->

Treat the new-work choice as distinct from the existing-work choice; pick one of them, not both.

Follow one linear path:

1. Open the OS guide for your machine.
2. Open the runtime guide you actually plan to use.
3. Install GPD with the runtime command shown there.
4. Open that runtime from your normal terminal and run `help`.
5. Run `start` if you are not sure what fits this folder.
6. Run `tour` if you want a read-only overview of what GPD can do before choosing.
7. Then choose `new-project`, `map-research`, or `resume-work`.

If you already have a GPD project, use the generated recovery ladder:

<!-- gpd-public-surface:recovery-note:start -->
Recovery ladder: use `gpd resume` for the current-workspace read-only recovery snapshot. If that is the wrong workspace, use `gpd resume --recent` to find the workspace first, then continue inside that workspace with `resume-work`. After resuming, `suggest-next` is the fastest next command. Before stepping away mid-phase, run `pause-work` so that ladder has an explicit handoff to restore later. Fresh context resets are for context management, not as a recovery step; run `gpd resume` in your normal terminal only when workspace rediscovery is needed.
<!-- gpd-public-surface:recovery-note:end -->

</details>

GPD favors scientific rigor and explicit uncertainty. Treat preferred answers as hypotheses to test, and if a citation, result, or artifact cannot be found or produced, keep that gap explicit instead of guessing.

## First: terminal vs runtime

You will use two different places: your normal terminal and your runtime.

<!-- gpd-public-surface:terminal-runtime-bridge:start -->
Use your normal terminal for installs, local `gpd ...` diagnostics, and runtime launchers such as `claude`, `gemini`, `codex`, `opencode`, `gh copilot`.
Use the opened runtime for the installed GPD command ladder (`help -> start -> tour -> new-project / map-research -> resume-work`); start with `/gpd:help`, `$gpd-help`, `/gpd-help`.
<!-- gpd-public-surface:terminal-runtime-bridge:end -->

<details>
<summary>Common beginner terms</summary>

- **Runtime**: the AI terminal app you talk to, such as Claude Code, Codex, Gemini CLI, GitHub Copilot CLI, or OpenCode.
- **API credits**: paid model usage from the provider behind your runtime.
- **`--local`**: install GPD for just this project or folder.
- **`gpd resume`**: the terminal-side recovery step.
- **`resume-work`**: the in-runtime command you use after reopening the right workspace.
- **`settings`**: after your first successful start or later, use the runtime `settings` command to review autonomy, workflow defaults, model-cost posture, runtime permission sync, and preset/tier overrides. The safest model-cost starting point is `review` plus runtime defaults.
- **`set-tier-models`**: the direct runtime command for pinning concrete `tier-1`, `tier-2`, and `tier-3` model ids.

</details>

## Choose your OS

Open only the guide that matches your computer.

<details>
<summary>macOS</summary>

Use this if you are on a Mac.

- [macOS guide](./macos.md)

</details>

<details>
<summary>Windows</summary>

Use this if you are on Windows 10 or 11.

- [Windows guide](./windows.md)

</details>

<details>
<summary>Linux</summary>

Use this if you are on Linux.

- [Linux guide](./linux.md)

</details>

## Choose your runtime

Open only the runtime guide you actually plan to use.
Use `--local` while learning so GPD only affects the current folder.

<details>
<summary>Claude Code</summary>

Use this if you want GPD inside Claude Code. Inside the runtime, GPD commands use `/gpd:...`.

- Install: `npx -y get-physics-done --claude --local`
- [Claude Code quickstart](./claude-code.md)

</details>

<details>
<summary>Codex</summary>

Use this if you want GPD inside Codex. Inside the runtime, GPD commands use `$gpd-...`.

- Install: `npx -y get-physics-done --codex --local`
- [Codex quickstart](./codex.md)

</details>

<details>
<summary>Gemini CLI</summary>

Use this if you want GPD inside Gemini CLI. Inside the runtime, GPD commands use `/gpd:...`.

- Install: `npx -y get-physics-done --gemini --local`
- [Gemini CLI quickstart](./gemini-cli.md)

</details>

<details>
<summary>GitHub Copilot CLI</summary>

Use this if you want GPD inside GitHub Copilot CLI. Inside the runtime, GPD commands use `/gpd-...`.

- Install: `npx -y get-physics-done --copilot --local`
- [GitHub Copilot CLI quickstart](./github-copilot-cli.md)

</details>

<details>
<summary>OpenCode</summary>

Use this if you want GPD inside OpenCode. Inside the runtime, GPD commands use `/gpd-...`.

- Install: `npx -y get-physics-done --opencode --local`
- [OpenCode quickstart](./opencode.md)

</details>

## After the guides

1. Finish the OS and runtime guide you opened.
2. Inside the runtime, use `help` for the command menu, `start` if you are not sure what fits this folder, or `tour` if you want a read-only orientation first.
3. Then choose `new-project`, `map-research`, or `resume-work`.
4. Review settings after the first successful start:

<!-- gpd-public-surface:post-start-settings:start -->
After your first successful start or later, use the runtime `settings` command to review autonomy, workflow defaults, model-cost posture, runtime permission sync, and preset/tier overrides. The safest starting point is `review` plus runtime defaults. Favor scientific rigor and explicit uncertainty over agreement-seeking, and keep missing evidence or artifacts explicit instead of inventing them.
<!-- gpd-public-surface:post-start-settings:end -->

5. Come back to this hub only when you need a different OS guide or runtime guide.
