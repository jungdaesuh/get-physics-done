# Runtime Command Snippets

Stable runtime-local command rules live here so generated command prompts can
carry compact pointers instead of repeating the same prose in every command.

## Runtime Shell Bridge

- Keep user-facing command names canonical in prose: `gpd ...` for a normal terminal and the runtime-native command prefix shown in command-local notes.
- When shell steps call the GPD CLI, put the command-local bridge directly in
  command position.
- The bridge is a command with arguments, not one executable path. Do not store
  it in a scalar variable and then expand that variable as the command.
- If you need reuse inside one shell block, define a shell function around the exact bridge and pass arguments through with `"$@"`.
- In zsh examples, use `cmd_status=$?`; `status` is a reserved read-only parameter.

## Runtime Questioning

- Ask each user-facing question exactly once.
- Present options once.
- Do not restate the prompt or add meta narration.

## Runtime Shell Policy

- Some runtimes enforce a syntactic allowlist before shell commands execute.
- Prefer direct commands and reason over stdout instead of wrapping approved
  commands in shell variables, command substitutions, heredocs, or extra
  chained blocks.
- Treat shell-looking variable assignments, loops, placeholders, and terminal
  examples as non-runnable guidance unless the rendered prompt keeps them in a
  shell fence with an allowed first command.
- If a runtime shell tool is denied by policy, stop and report the policy
  block. Do not replace validation or persistence commands with unvalidated
  file writes.
- Keep approved contract JSON in memory or under `GPD/`; do not write approved
  contracts to operating-system temp directories.
