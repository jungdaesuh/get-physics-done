# Runtime Delegation Note

Use `@{GPD_INSTALL_DIR}/references/orchestration/agent-delegation.md` as the authoritative delegation contract.

For any runtime handoff, preserve these canonical rules:

- Spawn a fresh subagent for the task below.
- This is a one-shot handoff: `status: checkpoint` stops for the user. Do not make the child wait in place.
- Fresh-continuation ownership stays with the main orchestrator after a child checkpoint.
- Empty-model omission: If `model` resolves to `null` or an empty string, omit it so the runtime uses its default model.
- Child artifact gate: apply `references/orchestration/child-artifact-gate.md`; the local callsite names expected artifacts, validators, applicator, and failure route.
- Return gate: A missing or invalid `gpd_return` is incomplete; retry or use explicit main-context fallback according to the local failure route.
- Recovery limit: Recover literal child-authored file contents only; must not synthesize, patch, or paste a child `gpd_return`.
- Evidence limit: Files, commits, and preexisting artifacts are recovery evidence only until the local gate passes.
- Always pass `readonly=false` for file-producing agents.

If native subagent spawning is unavailable, execute sequentially in the main context with the same gates.
