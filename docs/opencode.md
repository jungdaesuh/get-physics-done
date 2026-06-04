# OpenCode Quickstart for GPD

This guide uses the simplest path to get started. OpenCode's official docs may
list additional install, auth, or platform-specific options.

Back to the onboarding hub: [GPD Onboarding Hub](./README.md).

## Choose this runtime if

Use OpenCode if you want GPD inside OpenCode and prefer the `/gpd-...` command
style.

If you are on Windows, OpenCode's official docs recommend using WSL for the
best experience.

## What must already be true

- You already have OpenCode installed and can launch `opencode` from your
  normal terminal.
- Node.js 20+ and Python 3.11+ with `venv` are installed.
- You are in the folder where you want this research project to live.
- This guide uses `--local`, so GPD is installed only for the current folder.

## 1) Confirm OpenCode works

Run this in your normal terminal:

```bash
opencode --help
```

If you see OpenCode help instead of `command not found`, the CLI is available.
If `opencode` is missing, install the runtime first with:

```bash
npm install -g opencode-ai
```

## 2) Install, start, and use GPD

<!-- gpd-public-surface:runtime-quickstart-opencode:start -->
From your normal terminal:

```bash
npx -y get-physics-done --opencode --local
opencode
```

Inside OpenCode:

```text
/gpd-help
/gpd-start
/gpd-tour
/gpd-new-project --minimal
/gpd-map-research
/gpd-resume-work
```

Suggested order for beginners: `/gpd-help`, `/gpd-start`, `/gpd-tour`, then either `/gpd-new-project --minimal`, `/gpd-map-research`, or `/gpd-resume-work`.

Return to work from your normal terminal with `gpd resume` or `gpd resume --recent`, then reopen `opencode` in the right folder and run `/gpd-resume-work`.

After your first successful start or later, use `/gpd-settings` to review autonomy, workflow defaults, model-cost posture, runtime permission sync, and preset/tier overrides. The safest starting point is `review` plus runtime defaults. Favor scientific rigor and explicit uncertainty over agreement-seeking, and keep missing evidence or artifacts explicit instead of inventing them.
<!-- gpd-public-surface:runtime-quickstart-opencode:end -->

If you are not signed in yet, run `/connect` inside OpenCode, choose your provider, and finish that provider's API-key or billing setup.

## What success looks like

- `opencode --help` works.
- GPD installation finishes without errors.
- Inside OpenCode, `/gpd-help` returns a GPD help screen.
- `/gpd-start` routes a beginner to the right entry point.
- `/gpd-tour` gives a read-only walkthrough of the main commands.
- `/gpd-new-project --minimal`, `/gpd-map-research`, or `/gpd-resume-work` starts the right GPD flow for new work, an existing research folder, or an existing project.

## Quick troubleshooting

- Missing `opencode`: install OpenCode first or add it to `PATH`, then reopen your terminal.
- Missing `/gpd-...` commands: rerun the install command above, then restart OpenCode.
- Not signed in: start `opencode`, run `/connect`, finish the provider setup, then reopen OpenCode and try `/gpd-help` again.

## Official docs

- OpenCode: [Intro and install](https://opencode.ai/docs/)
- OpenCode: [CLI reference](https://opencode.ai/docs/cli/)
- OpenCode: [Windows with WSL](https://opencode.ai/docs/windows-wsl/)
