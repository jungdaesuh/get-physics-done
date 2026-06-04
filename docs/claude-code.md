# Claude Code Quickstart for GPD

Use this if you want to run GPD inside Claude Code.

This guide shows the simplest path to get started. Anthropic's official Claude
Code docs may list additional install and platform-specific options.

Back to the onboarding hub: [GPD Onboarding Hub](./README.md).

## Choose this runtime if

Use Claude Code if you want GPD inside Claude's terminal app and prefer the
direct `/gpd:...` command style.

If you are on Windows, Claude Code's official docs say you need Git for Windows
or WSL. If you are on Linux and `claude` is missing, Anthropic recommends the
native installer. Anthropic's npm install path is now deprecated.

## What must already be true

- You already have Claude Code installed and can launch `claude` from your
  normal terminal.
- Node.js 20+ and Python 3.11+ with `venv` are installed.
- You are in the folder where you want this research project to live.
- This guide uses `--local`, so GPD is installed only for the current folder.

## 1) Confirm `claude` works

From your normal terminal, run:

```bash
claude --version
```

If it prints a version number, Claude Code is installed and available on your `PATH`.

If it does not, use Anthropic's getting-started guide linked below, then come back here.

## 2) Install, start, and use GPD

<!-- gpd-public-surface:runtime-quickstart-claude-code:start -->
From your normal terminal:

```bash
npx -y get-physics-done --claude --local
claude
```

Inside Claude Code:

```text
/gpd:help
/gpd:start
/gpd:tour
/gpd:new-project --minimal
/gpd:map-research
/gpd:resume-work
```

Suggested order for beginners: `/gpd:help`, `/gpd:start`, `/gpd:tour`, then either `/gpd:new-project --minimal`, `/gpd:map-research`, or `/gpd:resume-work`.

Return to work from your normal terminal with `gpd resume` or `gpd resume --recent`, then reopen `claude` in the right folder and run `/gpd:resume-work`.

After your first successful start or later, use `/gpd:settings` to review autonomy, workflow defaults, model-cost posture, runtime permission sync, and preset/tier overrides. The safest starting point is `review` plus runtime defaults. Favor scientific rigor and explicit uncertainty over agreement-seeking, and keep missing evidence or artifacts explicit instead of inventing them.
<!-- gpd-public-surface:runtime-quickstart-claude-code:end -->

Claude Code requires a Pro, Max, Teams, Enterprise, or Console account. The free Claude.ai plan does not include Claude Code access.

## Readiness before unattended runs

After `/gpd:settings` changes autonomy, or before an overnight run, check the
active runtime from your normal terminal:

```bash
gpd validate unattended-readiness --runtime claude-code --autonomy supervised
```

Use the autonomy mode you selected if it is not `supervised`. If the verdict is
`not-ready`, apply the runtime permission update and check again:

```bash
gpd permissions sync --runtime claude-code --autonomy supervised
gpd validate unattended-readiness --runtime claude-code --autonomy supervised
```

If the verdict is `relaunch-required`, exit Claude Code and relaunch `claude`
from this project folder before treating unattended use as ready.

## What success looks like

- `claude --version` prints a version.
- `npx -y get-physics-done --claude --local` finishes without errors.
- Inside Claude Code, `/gpd:help` shows the GPD commands.
- `/gpd:start` routes a beginner to the right entry point.
- `/gpd:tour` explains the main commands without changing anything.
- `/gpd:new-project --minimal`, `/gpd:map-research`, or `/gpd:resume-work` starts the right GPD flow for new work, existing research, or an existing GPD project.

## Quick troubleshooting

- `claude: command not found` means Claude Code is not installed or not on your `PATH`. Install Claude Code first, then try `claude --version` again.
- If Claude Code opens but says your account does not have access, make sure you are using a Pro, Max, Teams, Enterprise, or Console account.
- If Claude Code opens but asks you to sign in, finish the sign-in flow, then rerun `claude`.
- If `/gpd:help` is not recognized, rerun `npx -y get-physics-done --claude --local` from your normal terminal, then reopen Claude Code.

## Official docs

- Anthropic: [Claude Code getting started](https://code.claude.com/docs/en/getting-started)
- Anthropic: [Claude Code settings](https://code.claude.com/docs/en/settings)
