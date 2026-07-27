# Remove GPD Built-in MCP Servers — Replace with `gpd` CLI + Skills

**Status:** Draft
**Last updated:** 2026-07-27

## Purpose

Eliminate the resident-process cost of GPD's built-in MCP servers (7 always-on + optional `gpd-arxiv`) by replacing them with zero-idle-cost equivalents: `gpd` CLI subcommands invoked from the already-installed skill/command prompts. Measured on a live machine: 54 sessions × 7 servers = 378 processes, ~5 GB RSS, with only 3 of ~41 MCP tools referenced by any workflow prompt.

## Goals

- Zero resident GPD processes per runtime session (no `mcpServers` entries installed).
- The 3 actually-used MCP tools (`run_contract_check`, `suggest_contract_checks`, `get_bundle_checklist`) reachable via `gpd` CLI with `--raw` JSON output.
- Reference content (error catalog, protocols) accessible to agents via CLI, since `specs/references/` lives inside the installed wheel and prompts cannot hardcode its path.
- Upgrade path that actively removes stale `gpd-*` entries from users' runtime configs.

## Non-Goals

- Removing the `gpd-wolfram` managed integration (opt-in, off by default, genuinely network/session-shaped; `src/gpd/mcp/managed_integrations.py`). Decide separately.
- Replacing arXiv search with a new GPD feature. `gpd-arxiv` is optional, unreferenced by all 95 prompts, and its dependency (`arxiv_mcp_server`) is not installed by default; lit-review agents already use `web_search`/`web_fetch`. It is simply deleted.
- Changing what the workflow prompts *do* — only how they reach the underlying code.

## Current Context (confirmed facts)

- Server registry: `src/gpd/mcp/builtin_servers.py` (`_BUILTIN_SERVERS`, `GPD_MCP_SERVER_KEYS`, `build_mcp_servers_dict`, `build_public_descriptors`).
- Consumers of the registry:
  - Install flow: `src/gpd/adapters/install_utils.py:284,308`; adapters `claude_code.py:325`, `codex.py:1106,2217`, `gemini.py:1228`, `copilot_cli.py:137,392,779`.
  - CLI: `gpd mcp-server <name>` (runs a server in-process) and `gpd list-servers` (`src/gpd/cli.py` ~11480–11520).
  - Public descriptors: `infra/gpd-*.json` (8 files), kept in sync by `tests/test_release_consistency.py`, `tests/test_metadata_consistency.py`, and scoped by `scripts/repo_graph_contract.py:98`.
  - Console entry points: `gpd-mcp-{conventions,verification,protocols,errors,patterns,arxiv,state,skills}` in `pyproject.toml [project.scripts]`.
- Only 2 of 95 prompt files reference MCP tools: `src/gpd/commands/verify-work.md:40-42` and `src/gpd/agents/gpd-verifier.md` (frontmatter `tools:` line) — all 3 tools from `gpd-verification`.
- All servers are stateless per-request wrappers; the real logic already lives in `gpd.core.*` / `gpd.contracts` (shared with the CLI, including `save_state_json_locked` file locking). The exceptions are parsing/routing code that lives **inside** server modules and must move to core:
  - Error-catalog markdown-table parsing: `src/gpd/mcp/servers/errors_mcp.py`.
  - Protocol section/step/checkpoint parsing + keyword routing: `src/gpd/mcp/servers/protocols_server.py`.
- `gpd` CLI already covers far more than the state surface:
  - State: `gpd state get/patch/advance/validate`, `gpd health`, `gpd suggest`, `gpd progress` (`--raw` JSON).
  - Conventions: `gpd convention set/list/diff/check/vocabulary` (`src/gpd/cli.py:2527-2658`). Missing vs. server: `assert_convention_validate`, `subfield_defaults` (`vocabulary` dumps label vocabulary, not per-domain defaults).
  - Patterns: `gpd pattern init/add/list/search/promote/seed` (`src/gpd/cli.py:3705-3800`) — near-full parity with the server (`search`≈`lookup_pattern`).
  - A `gpd verify` sub-app already exists (`src/gpd/cli.py:3228`) with `summary/plan/phase/references/commits/artifacts` — the contract tools are new subcommands on it, not a new sub-app. Note `gpd validate verification-contract` (`src/gpd/cli.py:9645`) is a different thing (VERIFICATION.md frontmatter/oracle validation), not `run_contract_check`.
  - No CLI surface exists for the error catalog or protocol content.
- `gpd doctor` does not probe MCP servers (the `health_check` blocks live only in the `infra/` descriptors and their consistency tests; `gpd.core.health` has no server probes) — no doctor changes needed.
- The `arxiv` optional extra exists in `pyproject.toml [project.optional-dependencies]` (`arxiv-mcp-server[pdf]>=0.4.11`) solely for the bridge.
- Test surface to migrate/remove: `tests/mcp/` (30 files, ~1.2 MB).

## Rationale

MCP earns its cost through persistent state, streaming, or held connections. Every GPD server re-reads disk per request and holds nothing between calls — the exact profile of a CLI invocation, which costs 0 MB idle. Design-it-twice alternative considered: **consolidate 7 servers into one FastMCP process** (~85% memory reduction, tiny diff, no prompt changes). Rejected as the end state because the requirement is *zero* resident cost and one process per session × N sessions still accumulates; it remains the fallback if upstream declines full removal. The skills layer needs no invention: GPD's commands/agents are already installed as prompts with shell access; they just need CLI invocations instead of MCP tool names.

Risk tier: **Tier 3** (public surface: console scripts, infra descriptors, MCP tool names). API evolution gate items are embedded in Phase 4 and Validation.

## Assumptions

- All supported runtimes (Claude Code, Codex, Gemini CLI, Copilot CLI, OpenCode) can execute shell commands from agent prompts. (Holds today; verify OpenCode/Copilot sandbox defaults during Phase 2.)
- No known external consumers of the `gpd-mcp-*` console scripts or `infra/gpd-*.json` beyond GPD's own install flow. **Assumption — confirm via GitHub code search before Phase 4.**
- Maintainers (psi-oss) accept removal. If not, fall back to single-process consolidation (see Rationale).

## Implementation Plan

1. **Phase 0 — Immediate local relief (no repo change, this machine)**
   - [ ] Close stale runtime sessions (54 live sessions each holding 7 servers).
   - [ ] Remove `gpd-conventions|errors|patterns|protocols|skills|state` entries from runtime `mcpServers` config; keep `gpd-verification` until Phase 3 ships if `/gpd:verify-work` is in active use. Note: `gpd install` re-adds them until Phase 3.

2. **Phase 1 — CLI parity (additive, independently shippable PR)**
   - [ ] Move error-catalog parsing from `errors_mcp.py` into `src/gpd/core/error_catalog.py`; server imports from core until deleted (no duplication window).
   - [ ] Move protocol parsing/routing from `protocols_server.py` into `src/gpd/core/protocol_catalog.py`; same import discipline.
   - [ ] Extend the existing `gpd verify` sub-app (`src/gpd/cli.py:3228`) with contract subcommands wrapping `gpd.core.contract_validation` / `gpd.core.protocol_bundles` / `gpd.core.verification_checks`:
     - [ ] `gpd verify contract-check --payload <file|->` (JSON in, stable-envelope JSON out; `--schema` flag prints the pydantic JSON schema so agents can self-correct invalid payloads).
     - [ ] No-orphan guarantee for all new subcommands: fail fast instead of blocking — when `--payload -` is used with a TTY stdin (no piped input), exit immediately with a usage error rather than waiting on stdin. Lock waits are already bounded (`file_lock` 5 s acquisition timeout, `src/gpd/core/utils.py:461`) and OS advisory locks auto-release on process death, so no CLI invocation can linger or leave stale locks; nothing in these commands may spawn background processes or daemons.
     - [ ] `gpd verify suggest-checks --contract <file|->`.
     - [ ] `gpd verify bundle-checklist <bundle-id>...`.
     - [ ] `gpd verify checklist <domain>` and `gpd verify coverage` (replace `get_checklist`/`get_verification_coverage`).
   - [ ] Add `gpd refs errors [list|get <id>|--domain <d>]` and `gpd refs protocols [list|get <name>|route <query>|checkpoints <name>]` over the new core modules (no existing CLI surface; `gpd query` is project-artifact search, unrelated).
   - [ ] Close the two conventions gaps on the existing `gpd convention` sub-app: `gpd convention validate-assert <file>` (wraps `check_assertions`/`parse_assert_conventions`) and `gpd convention subfield-defaults <domain>`. Mutations already go through `save_state_json_locked` (used by both `cli.py` and the server).
   - [ ] Audit `gpd pattern` parity against the patterns server (`search` vs `lookup_pattern` filters, `list` vs `list_domains`); close any gaps found — expected near-zero work.
   - [ ] Decision recorded: `dimensional_check`, `limiting_case_check`, `symmetry_check` are **dropped without CLI replacement** — they are regex/guidance-text generators whose own docstrings defer real math to SymPy; no prompt references them.
   - [ ] No CLI work for `gpd-state` (surface exists) or `gpd-skills` (the runtime's own skill system is the surface; no replacement).
   - [ ] Output envelopes reuse the `stable_mcp_response`/`stable_mcp_error` shape (rename to a transport-neutral module, e.g. `gpd.core.envelopes`) so downstream parsing is identical across MCP (until deleted) and CLI.

3. **Phase 2 — Prompt/skill migration**
   - [ ] `src/gpd/commands/verify-work.md:40-42`: replace the 3 `mcp__gpd_verification__*` allowlist entries and call sites with `gpd verify ...` Bash invocations.
   - [ ] `src/gpd/agents/gpd-verifier.md`: drop the 3 `mcp__gpd_verification__*` names from `tools:`; keep `shell`; update body instructions to the CLI forms.
   - [ ] Sweep `src/gpd/specs/references/` for prose directing agents at MCP tools — confirmed matches in ≥9 files, including `tooling/tool-integration.md`, `tooling/runtime-config-guide.md`, `verification/core/verification-quick-reference.md`, `orchestration/checkpoints.md`, `orchestration/state-portability.md` — and update to CLI/file-read guidance.
   - [ ] Verify each runtime adapter's permission/allowlist handling covers the new `gpd verify|refs|conventions|patterns` invocations (adapters already manage permissions for `gpd` commands; extend patterns if allowlists are verb-scoped).

4. **Phase 3 — Remove the MCP layer (breaking release)**
   - [ ] Adapters/install: stop writing `mcpServers`; on install/upgrade, actively delete entries named in a retained tombstone constant — the current `GPD_MCP_SERVER_KEYS`, which already includes all 8 servers (`gpd-arxiv` included; it is `frozenset(_BUILTIN_SERVERS.keys())`, `builtin_servers.py:266`) — from Claude Code, Codex, Gemini, Copilot, OpenCode configs. Adapters already union `managed_optional_mcp_server_keys()` (wolfram) for removal handling (`copilot_cli.py:139`, `install_utils.py:308-310`); preserve that. Uninstall keeps using the same tombstone.
   - [ ] Delete `src/gpd/mcp/servers/` (all 7 servers + arxiv bridge + `_arxiv_*` helpers + `arxiv_translators.py`), `verification_contract_policy.py`'s server-description surface (keep contract policy logic used by CLI), and shrink `builtin_servers.py` to the tombstone-keys module (or fold into `install_utils`).
   - [ ] Remove `gpd mcp-server` and `gpd list-servers` CLI commands (or keep `list-servers` for one release returning `{}` plus a deprecation note — decide with maintainers).
   - [ ] Remove the built-in `gpd-mcp-*` entry points from `pyproject.toml` — all except `gpd-mcp-wolfram`, which belongs to the out-of-scope managed integration; remove `infra/gpd-*.json`; update `scripts/repo_graph_contract.py:98`.
   - [ ] Remove the `arxiv` optional extra from `pyproject.toml [project.optional-dependencies]` (exists solely for the bridge).
   - [ ] Tests: delete/port `tests/mcp/` (30 files) — parity assertions move to CLI tests in Phase 1; update `test_release_consistency.py`, `test_metadata_consistency.py`.
   - [ ] API evolution gate artifacts: CHANGELOG breaking-change entry with migration table (old MCP tool → new CLI command); caller inventory (runtime configs, entry points, infra descriptors — plus GitHub code search for external `gpd-mcp-` usage); version bump per repo's semver policy.

## Validation Plan

- [ ] `uv run pytest` green after each phase.
- [ ] Parity tests (Phase 1): for each ported tool, CLI output equals the MCP server output on the same fixtures (run before servers are deleted; these become the regression suite).
- [ ] Upgrade migration test (Phase 3): given a runtime config containing all 8 legacy `gpd-*` entries plus one user-defined non-GPD server, `gpd install` removes exactly the GPD entries and preserves the user's.
- [ ] E2E: in a sample GPD project, run `/gpd:verify-work` end-to-end on Claude Code and one non-Claude runtime (Codex or Gemini) — contract check, bundle checklist, and suggest-checks all round-trip through the CLI.
- [ ] Resource check: after install on a clean runtime, `ps aux | grep gpd.mcp` shows zero processes during an active session.
- [ ] No-orphan check: after exercising each new CLI subcommand (including a `--payload -` invocation with no piped stdin, which must exit non-zero immediately), `pgrep -f "gpd (verify|refs|convention|pattern)"` returns nothing.
- [ ] Descriptor-consistency tests (`tests/test_release_consistency.py`, `tests/test_metadata_consistency.py`) updated and green after `infra/` removal. `gpd doctor` needs no changes (verified: `gpd.core.health` contains no MCP server probes).

## Risks and Mitigations

- Risk: Upstream (psi-oss) rejects full removal — MCP is advertised in README/positioning.
  Mitigation: Ship Phase 1+2 as a standalone PR (pure additive + prompt cleanup, valuable regardless). Propose Phase 3 in an issue first; fallback is single-process consolidation (one FastMCP mount, ~85% reduction) which Phases 1–2 make trivial.
- Risk: Losing MCP's schema-enforced inputs makes agents produce malformed contract payloads.
  Mitigation: `gpd verify contract-check --schema` + structured pydantic validation errors on stdout give agents a self-correction loop; prompt text in `verify-work.md` points to it.
- Risk: A runtime's permission model blocks the new CLI calls where MCP tools were pre-authorized.
  Mitigation: Phase 2 task extends each adapter's managed allowlist; E2E validation on two runtimes.
- Risk: Unknown external consumers of `gpd-mcp-*` entry points or `infra/*.json`.
  Mitigation: GitHub code search before Phase 3; breaking-change CHANGELOG + optional one-release deprecation stub for `list-servers`.
- Risk: Parsing logic drift while both server and CLI exist (Phase 1→3 window).
  Mitigation: single source in `gpd.core.*`; servers import from core; parity tests pin both surfaces.

## Completion Criteria

- [ ] No `mcpServers` entries written by `gpd install` on any runtime; upgrade removes legacy entries.
- [ ] Zero `gpd.mcp.servers` processes during active sessions.
- [ ] `/gpd:verify-work` passes E2E via CLI on ≥2 runtimes.
- [ ] `src/gpd/mcp/servers/`, `infra/gpd-*.json`, and `gpd-mcp-*` entry points deleted; tests and consistency checks green.
- [ ] CHANGELOG migration table published.

## Open Questions

- Scope of `gpd-wolfram` managed integration — leave (opt-in) or fold into this removal? Owner: maintainers.
- Single release removal vs. staged (release N: stop installing + deprecate; N+1: delete code)? Depends on external-consumer search results.
- Keep `gpd list-servers` as a one-release deprecation stub or remove outright?
- The `gpd convention` and `gpd pattern` CLI surfaces already exist, so the only real question is the two gap subcommands (`validate-assert`, `subfield-defaults`): add them (workflows depend on the ASSERT_CONVENTION discipline even though no prompt names the MCP tool), or drop the capability with the server? Default in this plan: add both — cheap, logic already in `gpd.core.conventions`. Decide in PR review.
