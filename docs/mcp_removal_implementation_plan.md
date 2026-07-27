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
- Only 2 of 95 prompt files referenced MCP tools: `src/gpd/commands/verify-work.md` (the `mcp__gpd_verification__*` entries in its `allowed-tools:` frontmatter list) and `src/gpd/agents/gpd-verifier.md` (its frontmatter `tools:` line) — all 3 tools from `gpd-verification`.
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
   - [x] Move error-catalog parsing from `errors_mcp.py` into `src/gpd/core/error_catalog.py`; server imports from core until deleted (no duplication window).
   - [x] Move protocol parsing/routing from `protocols_server.py` into `src/gpd/core/protocol_catalog.py`; same import discipline.
   - [x] Extend the existing `gpd verify` sub-app with contract subcommands wrapping `gpd.core.contract_validation` / `gpd.core.protocol_bundles` / `gpd.core.verification_checks`:
     - [x] `gpd --raw verify contract-check --payload <file|-> [--project-dir DIR]` (JSON in, stable-envelope JSON out; `--schema` prints the contract-check payload model's pydantic JSON schema so agents can self-correct invalid payloads). Exits 1 on `status: fail` so CI callers can gate on `$?`.
     - [x] No-orphan guarantee for all new subcommands: fail fast instead of blocking — when `--payload -` is used with a TTY stdin (no piped input), exit immediately with a usage error rather than waiting on stdin. Lock waits are already bounded (`file_lock` 5 s acquisition timeout, `src/gpd/core/utils.py:461`) and OS advisory locks auto-release on process death, so no CLI invocation can linger or leave stale locks; nothing in these commands may spawn background processes or daemons.
     - [x] `gpd --raw verify suggest-checks --contract <file|-> --project-dir DIR [--active-checks <id>,... ]`. `--project-dir` is not optional in practice: without it the anchor grounding is skipped and `contract_warnings` comes back empty.
     - [x] `gpd --raw verify bundle-checklist <bundle-id> [<bundle-id> ...]`. Exits 1 when any requested bundle id is unknown.
     - [x] `gpd --raw verify checklist <domain>` and `gpd --raw verify coverage --error-classes <id>,... --active-checks <id>,...` (replace `get_checklist`/`get_verification_coverage`).
   - [x] Add `gpd --raw refs errors [--domain <d> | --id <n> [--detection|--traceability]]` and `gpd --raw refs protocols [--domain <d> | --name <n> | --route <query> | --checkpoints <n>]` over the new core modules — one command each with mutually exclusive selector flags, not `list`/`get` subcommands (no existing CLI surface; `gpd query` is project-artifact search, unrelated). Unknown domains/ids emit the stable error envelope on stdout and exit 1.
   - [x] Close the two conventions gaps on the existing `gpd convention` sub-app: `gpd convention validate-assert <file> [--lock <file|-> | --project-dir DIR]` (wraps `check_assertions`/`parse_assert_conventions`) and `gpd convention subfield-defaults <domain>`. `validate-assert` fails closed when no lock is resolvable, so assertions cannot pass vacuously outside a GPD project. Mutations already go through `save_state_json_locked` (used by both `cli.py` and the server).
   - [x] **Audit performed** — `gpd pattern` parity against the patterns server (`gpd/cli.py` `pattern list|search` vs `patterns_server.lookup_pattern`/`list_domains`). **Two gaps found**, both still open:
     - [ ] `lookup_pattern(domain, category, keywords)` post-filters free-text search results by `domain` and `category`; `gpd pattern search <query>` takes no filter flags, so a keyword search cannot be narrowed. (`gpd pattern list` is a *superset* of the server's no-keyword path — it adds `--severity`, which `lookup_pattern` lacks — so the list side has no gap.)
     - [ ] `list_domains()` returns the valid `domains`/`categories`/`severities` vocabularies (`VALID_DOMAINS`/`VALID_CATEGORIES`/`VALID_SEVERITIES`); no `gpd pattern` command exposes them. Agents composing `gpd pattern add` have no CLI way to discover the accepted enum values.
     - Envelope note: the server flattens both paths into `{count, patterns, query, library_exists}`, while the CLI emits the raw `PatternListResult`/`PatternSearchResult` models (`matches` rather than `patterns`, no `query` on the list path). Closing the two gaps above should also reconcile the key names.
   - [x] Decision recorded: `dimensional_check`, `limiting_case_check`, `symmetry_check` are **dropped without CLI replacement** — they are regex/guidance-text generators whose own docstrings defer real math to SymPy; no prompt references them.
   - [x] No CLI work for `gpd-state` (surface exists) or `gpd-skills` (the runtime's own skill system is the surface; no replacement).
   - [x] Output envelopes reuse the `stable_mcp_response`/`stable_mcp_error` shape, now in the transport-neutral `gpd.core.envelopes`, so downstream parsing is identical across MCP (until deleted) and CLI.

3. **Phase 2 — Prompt/skill migration**
   - [x] `src/gpd/commands/verify-work.md`: replace the 3 `mcp__gpd_verification__*` entries in the `allowed-tools:` frontmatter list and their call sites with `gpd --raw verify ...` shell invocations.
   - [x] `src/gpd/agents/gpd-verifier.md`: drop the 3 `mcp__gpd_verification__*` names from `tools:`; keep `shell`; update body instructions to the CLI forms.
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

## Deferred with rationale

Consciously left undone in Phases 1–2; each is tracked, none blocks Phase 3 planning.

- **Frontmatter-regex hoist to `gpd.core.frontmatter`.** Four near-identical unclosed-frontmatter / leading-blank-line regex variants now live in `gpd.core.error_catalog`, `gpd.core.protocol_catalog`, `gpd.mcp.servers/__init__.py` (`parse_frontmatter_with_error`), and `gpd.core.frontmatter` itself. They differ in failure mode (raise vs. return an error string vs. silently return `({}, text)`), so folding them into one helper is a behavior-reconciliation task, not a move. Tracked as a follow-up; doing it inside this diff would have mixed a semantic change into a transport migration.
- **`filename="<mcp_input>"` literal retained** in `gpd.core.convention_checks.assert_convention_validate_payload`. Verified it never reaches the emitted envelope — the payload builder drops `AssertionCheckResult.file` and `AssertionMismatch.file` — so it is the one shared builder's internal label for both the `assert_convention_validate` MCP tool and `gpd convention validate-assert`. Renaming it changes nothing observable and would only churn the transport-parity seam; it retires with the MCP vocabulary in Phase 3.
- **Core docstrings that reference `gpd.mcp.*` paths** (e.g. `contract_checks` pointing at `gpd.mcp.servers.verification_server` for published input schemas) are accurate today — those schemas really do live there — and become stale only when Phase 3 deletes the module. Updated for transport-neutral *wording* (no more "MCP error envelope"), left pointing at the real code.

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
