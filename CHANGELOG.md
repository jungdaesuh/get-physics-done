# Changelog

All notable changes to Get Physics Done are documented here.

## vNEXT

- **Breaking: GPD's built-in MCP servers are removed.** `gpd install` no longer writes any `mcpServers` entries, the `src/gpd/mcp/servers/` package and the eight `infra/gpd-*.json` public descriptors are deleted, and the `gpd-mcp-{conventions,verification,protocols,errors,patterns,arxiv,state,skills}` console scripts are gone. Every capability they exposed is reachable from the `gpd` CLI (`--raw` for stable JSON envelopes — the same schema-versioned shape the MCP tools returned) or by reading installed files directly. Measured motivation: 54 live sessions x 7 always-on servers = 378 resident processes and ~5 GB RSS, for 3 tools any workflow prompt actually referenced.

  **Automatic migration.** Install, upgrade, *and* uninstall now actively delete the legacy `gpd-conventions`, `gpd-errors`, `gpd-patterns`, `gpd-protocols`, `gpd-skills`, `gpd-state`, `gpd-verification`, and `gpd-arxiv` entries from Claude Code (`.mcp.json` / `.claude.json`), Codex (`config.toml`), Gemini (`settings.json`), Copilot CLI (`copilot.json`), and OpenCode (`opencode.json`). Every non-GPD entry is preserved byte-for-byte. Just upgrade and relaunch your runtime; no manual config editing is required.

  **Not affected.** The opt-in `gpd-wolfram` managed integration is unchanged: it still installs, still ships the `gpd-mcp-wolfram` console script, and `gpd mcp-serve wolfram` / `gpd list-servers` still work (both now cover managed integrations only). The paper compiler under `gpd.mcp.paper` is unchanged.

  **Migration table.**

  | Removed MCP tool | Replacement |
  | --- | --- |
  | `mcp__gpd_verification__run_contract_check` | `gpd --raw verify contract-check --payload <file\|-> [--project-dir DIR]` (`--schema` prints the payload JSON schema; exits 1 on `status: fail`) |
  | `mcp__gpd_verification__suggest_contract_checks` | `gpd --raw verify suggest-checks --contract <file\|-> --project-dir DIR [--active-checks <id>,...]` |
  | `mcp__gpd_verification__get_bundle_checklist` | `gpd --raw verify bundle-checklist <bundle-id> [<bundle-id> ...]` |
  | `mcp__gpd_verification__get_checklist` | `gpd --raw verify checklist <domain>` |
  | `mcp__gpd_verification__get_verification_coverage` | `gpd --raw verify coverage --error-classes <id>,... --active-checks <id>,...` |
  | `mcp__gpd_verification__run_check` | `gpd --raw verify contract-check` (contract-aware execution is the single supported path) |
  | `mcp__gpd_verification__{dimensional,limiting_case,symmetry}_check` | **Dropped, no replacement.** These were regex/guidance-text generators whose own docstrings deferred the real work to SymPy; no prompt referenced them. Use SymPy or `/gpd:dimensional-analysis` / `/gpd:limiting-cases`. |
  | `mcp__gpd_errors__{get_error_class,get_detection_strategy,get_traceability,list_error_classes}` | `gpd --raw refs errors [--domain <d> \| --id <n> [--detection\|--traceability]]` |
  | `mcp__gpd_errors__check_error_classes` | `gpd --raw refs errors --domain <d>` plus the phase contract; free-text triage is no longer a tool call |
  | `mcp__gpd_protocols__{get_protocol,list_protocols,route_protocol,get_protocol_checkpoints}` | `gpd --raw refs protocols [--domain <d> \| --name <n> \| --route <query> \| --checkpoints <n>]` |
  | `mcp__gpd_conventions__{convention_lock_status,convention_set,convention_check,convention_diff}` | `gpd convention list/set/check/diff` |
  | `mcp__gpd_conventions__assert_convention_validate` | `gpd --raw convention validate-assert <file> [--lock <file\|-> \| --project-dir DIR]` |
  | `mcp__gpd_conventions__subfield_defaults` | `gpd --raw convention subfield-defaults <domain>` |
  | `mcp__gpd_patterns__{lookup_pattern,add_pattern,promote_pattern,seed_patterns,list_domains}` | `gpd pattern search/add/promote/seed/list` |
  | `mcp__gpd_state__{get_state,get_phase_info,get_progress,validate_state,advance_plan,get_config}` | `gpd state get/patch/advance/validate`, `gpd progress`, `gpd config` |
  | `mcp__gpd_state__{suggest_next,run_health_check}` | `gpd suggest`, `gpd health` |
  | `mcp__gpd_skills__{list_skills,get_skill,route_skill,get_skill_index}` | Your runtime's own skill/command system — GPD's commands and agents are already installed as prompts. |
  | `mcp__gpd_arxiv__*` (`search_papers`, `download_paper`, `list_papers`, `read_paper`, `get_abstract`, `download_source`) | The arXiv HTTP API (`https://export.arxiv.org/api/query`) via your runtime's `web_search` / `web_fetch` tools, which lit-review agents already used. `gpd-arxiv` was optional, off by default, and referenced by zero prompts. |

  The `arxiv` optional extra is also removed; it existed only for the deleted bridge. The `arxiv` Python package now lives in the `paper` extra, where the bibliography enrichment that actually imports it belongs.

- Add pandoc-driven markdown→LaTeX pipeline for the paper writer. Sections can opt in via `Section.content_format="markdown"`; raw-LaTeX payloads still pass through unchanged. Pandoc is probed once per `render_paper` call and shared across sections. When pandoc is missing the markdown path raises `PandocNotAvailable` with a recovery hint; legacy `maybe_convert_to_latex` callers degrade to pass-through. `--natbib` is the default so `@key` / `[@k1; @k2]` emit `\citet`/`\citep` for the template's `\bibliography{…}` to resolve; `pandoc-crossref` is auto-enabled when installed and `pandoc-citeproc` is intentionally excluded from auto-detection.
- Fix Nature template citation rendering: switch from `naturemag.bst` to `unsrtnat` with `\usepackage[numbers,super,sort&compress]{natbib}`. `naturemag.bst` predates natbib and has no author-name macro, so pandoc's `\citet` rendered as "(author?)" in the final PDF while passing every string-level `.tex` assertion.
- Fix PRL template cite-command resolution under revtex4-2: pass `natbib` as a class option (`\documentclass[…,natbib]{revtex4-2}`) instead of `\usepackage{natbib}`, which would otherwise option-clash with revtex's internal natbib load.
- Define `\providecommand{\tightlist}{…}` across every journal template (apj, jfm, jhep, mnras, nature, prl) so pandoc-emitted bullet lists compile.
- Fix `state patch` silent failures: failed fields now include `failure_reasons` with specific messages (invalid status, invalid transition, field not found). Dot-notation prefixes (e.g., `position.status` -> `Status`) are stripped only when the original name is not found. Session Continuity mirror fields (e.g., `resume_file`) are rejected with an explicit error directing users to the continuation API. CLI pretty-prints each failure reason as a separate row.
- Recognize bare arXiv IDs (`1304.4926`, `hep-th/0603001`) and bare DOIs (`10.1103/PhysRevD.100.026003`) as concrete reference locators for `must_surface` anchor validation. Fix casefold mismatch in `_is_project_artifact_path` that misclassified mixed-case archive names (e.g., `math.DG/0211159`) as project artifact paths.
- Fix `gpd suggest` ignoring actual project state: use `_project_scoped_cwd()` so root-level PROJECT.md is auto-migrated before `suggest_next()` runs, matching the pattern used by `progress`, `state`, and `status` commands.
- Fix `phase_add` and `phase_insert` heading consistency: detect heading level, number padding, and separator style (colon vs em-dash) from existing ROADMAP phases instead of hardcoding `### Phase {N}:`. Defaults to `### Phase N: ` (unpadded, colon) for empty ROADMAPs, matching the `new-project` template.
- Fix LaTeX special character escaping in user-provided metadata fields: `~`, `#`, `%`, and `&` in title, abstract, author fields, and acknowledgments are now escaped before rendering, preventing compilation errors and silent data loss. Agent-generated LaTeX content (section bodies, figure captions, appendix content) is deliberately unaffected.
- **Breaking (raw output only):** `gpd question resolve` and `gpd calculation complete` now return structured results (resolved/completed text, search text, remaining count) instead of a bare `1`. Raw JSON output changes from `{"result": "1"}` to a model with `resolved`/`completed`, `search_text`, and `remaining` fields. The prior `{"result": "1"}` output was a bug (unhelpful) and is not considered a stable contract.
- Broaden citation regexes to detect natbib (`\citep`, `\citet`, `\citealt`, `\citealp`, `\citeauthor`, `\citeyear`, `\citetext`), capitalized (`\Cite*`), starred (`\cite*`), and biblatex (`\parencite`, `\textcite`, `\autocite`) variants across the paper-quality scorer and artifact builder. Add `check_citation_bib_coherence()` to `build_paper()` to warn when `.tex` citations and `.bib` entries are inconsistent, with `\nocite{*}` support.
- Add `check_result_consistency` health check: cross-validates `state.json` intermediate results against SUMMARY `provides` frontmatter with guards against empty-string false matches, short-string over-matching, and malformed state records.
- Fix Windows test compatibility: cross-platform absolute paths in MCP tests, `shlex.quote`-aware assertions, `encoding="utf-8"` on `read_text()`, POSIX display paths in CLI/git_ops, permission/LaTeX/tilde/bash test portability, and schema pattern alignment.
- Split releases into a manual release-PR preparation workflow and a separate publish workflow for PyPI, npm, tags, and GitHub Releases.
- fix: use `Path.replace()` instead of `Path.rename()` for atomic settings overwrite on Windows.
- Fix silent data loss in state normalization: malformed list entries (e.g., approximations with missing `name` field) now remove only the invalid entry instead of stripping the entire section.
- Fix agent docs: `approximation add` and `uncertainty add` use positional arguments, not `--name`/`--quantity` flags (agent-infrastructure.md, sensitivity-analysis.md, error-propagation.md).
- Fix catastrophic state reset: `_normalize_state_schema({})` now emits the integrity sentinel that triggers backup recovery, preventing silent data loss when `state.json` contains an empty object.
- Auto-migrate `ROADMAP.md` and `PROJECT.md` from workspace root into `GPD/` on first command, so files placed at the root are found by all GPD operations.
- Accept integer and float values in `depends_on` and `files_modified` frontmatter lists by coercing them to strings during validation.
- Add `--answer` flag to `gpd question resolve` so resolved questions and their answers are preserved in `state.json` and `STATE.md` instead of being silently discarded.

## v1.1.0

- Public open-source release.
- Multi-runtime support for Claude Code, Gemini CLI, Codex, and OpenCode.
- Structured physics research workflows for planning, execution, verification, and publication support.
