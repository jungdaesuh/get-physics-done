# GitHub Copilot CLI Quickstart for GPD

This guide uses the simplest path to get started. GitHub Copilot CLI's official
docs may list additional install, auth, or platform-specific options.

Back to the onboarding hub: [GPD Onboarding Hub](./README.md).

## Choose this runtime if

Use GitHub Copilot CLI if you want GPD inside GitHub Copilot CLI and prefer the
`/gpd-...` command style with GitHub's AI assistant.

## What must already be true

- You already have the GitHub CLI (`gh`) installed with the Copilot extension
  and can launch `gh copilot` from your normal terminal.
- Node.js 20+ and Python 3.11+ with `venv` are installed.
- You are in the folder where you want this research project to live.
- This guide uses `--local`, so GPD is installed only for the current folder.

## 1) Confirm GitHub Copilot CLI works

Run this in your normal terminal:

```bash
gh copilot --help
```

If you see Copilot help instead of `command not found`, the CLI is available.
If `gh copilot` is missing, install the GitHub CLI first with:

```bash
gh extension install github/gh-copilot
```

## 2) Install, start, and use GPD

<!-- gpd-public-surface:runtime-quickstart-copilot-cli:start -->
From your normal terminal:

```bash
npx -y get-physics-done --copilot --local
gh copilot
```

Inside GitHub Copilot CLI:

```text
/gpd-help
/gpd-start
/gpd-tour
/gpd-new-project --minimal
/gpd-map-research
/gpd-resume-work
```

Suggested order for beginners: `/gpd-help`, `/gpd-start`, `/gpd-tour`, then either `/gpd-new-project --minimal`, `/gpd-map-research`, or `/gpd-resume-work`.

Return to work from your normal terminal with `gpd resume` or `gpd resume --recent`, then reopen `gh copilot` in the right folder and run `/gpd-resume-work`.

After your first successful start or later, use `/gpd-settings` to review autonomy, workflow defaults, model-cost posture, runtime permission sync, and preset/tier overrides. The safest starting point is `review` plus runtime defaults. Favor scientific rigor and explicit uncertainty over agreement-seeking, and keep missing evidence or artifacts explicit instead of inventing them.
<!-- gpd-public-surface:runtime-quickstart-copilot-cli:end -->

If you are not signed in yet, follow the GitHub authentication prompts.

## What success looks like

- `gh copilot --help` works.
- GPD installation finishes without errors.
- Inside GitHub Copilot CLI, `/gpd-help` returns a GPD help screen.
- `/gpd-start` routes a beginner to the right entry point.
- `/gpd-tour` gives a read-only walkthrough of the main commands.
- `/gpd-new-project --minimal`, `/gpd-map-research`, or `/gpd-resume-work` starts the right GPD flow for new work, an existing research folder, or an existing project.

## Quick troubleshooting

- Missing `gh copilot`: install the GitHub CLI and the Copilot extension first, then reopen your terminal.
- Missing `/gpd-...` commands: rerun the install command above, then restart GitHub Copilot CLI.
- Not signed in: run `gh auth login` to authenticate with GitHub, then try again.

## Official docs

- GitHub CLI: [Install](https://cli.github.com/)
- GitHub Copilot CLI: [Getting started](https://docs.github.com/en/copilot/github-copilot-in-the-cli)
