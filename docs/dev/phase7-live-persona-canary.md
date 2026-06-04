# Phase 7 Live Persona Canary

Manual live is opt-in. It is never started by pull request, push, release, or publish jobs. The operator approves budget, provider account, tracked row set, and local workspace before any provider CLI launch.

Row ids are stable identity. Use the canonical row ids from the tracked class-only manifest; runtime, provider account, date, workspace, and attempt values are metadata only and must not create alternate row ids.

Raw artifacts stay ignored/operator-local under repo-local `tmp/`: prompts, stdout/stderr, transcripts, argv/env, auth/account data, home paths, provider replies, command files, and raw diffs. Keep runner workspaces, runtime homes, prompts, transcripts, stdout/stderr, argv/env, and sidecars inside ignored `tmp/` paths, with row attempts under `tmp/phase7-live-persona-YYYYMMDD/raw/<row_id>/<runtime_class>/<attempt_id>/`.

Public output is a sanitized class-only summary: row-set ids, canonical row ids, runtime/persona/workflow/result/write/next-step classes, aggregate counts, redaction status, and finding classes. It must not include raw text, local paths, hashes, account identifiers, command lines, tokens, provider replies, transcript excerpts, or ignored raw artifact paths.

Release and publish jobs must not launch provider CLIs. They may consume an already-produced sanitized summary by report id. Nightly is deferred; any later nightly canary must use a dedicated workflow with `workflow_dispatch` and optionally `schedule`, protected credentials, strict budgets, and sanitized summary artifacts only.

## Phase 6 Shadow-Live Scope

Phase 6 shadow-live rows reuse this policy. They may observe a manually approved provider run, but repo code stays provider-free: no pull request, push, release, publish, or test job launches a provider CLI, and this runbook defines no live provider runner. Public review material is class tokens and counts only; raw material stays inside ignored repo-local `tmp/`.

## Manual Sequence

1. Select a tracked row set from `tests/fixtures/phase7_live_persona_matrix.json`; for the Phase 6 first manual canary use `phase6_first_manual_canary`. Preserve the manifest ordering, and run any `phase6_tri_runtime_readonly` rows before bounded write rows when that row set is included.
2. Create `tmp/phase7-live-persona-YYYYMMDD/` and keep all raw material under `raw/<row_id>/<runtime_class>/<attempt_id>/` inside it.
3. Confirm clean/frozen checkout, row-owned homes, class-only budget/auth sidecars, and that every attempt maps back to its tracked canonical row id.
4. Run rows manually; stop on mutation, budget exhaustion, auth uncertainty, or redaction failure.
5. Produce only the sanitized summary; keep raw artifacts local unless requested for private debugging.

## Public Summary Shape

The public summary uses `phase7.live-persona-canary-summary.v1` with class-only fields such as `execution_mode_class=manual_opt_in`, `trigger_class=operator_local_manual`, `raw_artifact_retention_class=operator_local_ignored_tmp`, `public_artifact_class=sanitized_class_only_summary`, `provider_launch_source_class=manual_operator`, `ci_provider_launch_allowed=false`, `release_publish_provider_launch_allowed=false`, `nightly_status_class=deferred`, and `nightly_allowed_triggers` containing `workflow_dispatch` and `schedule`.

Rows may include row-set ids, canonical row ids, and runtime/persona/workflow/write/result/next-step, shadow-live, capture-policy, redaction, finding, and event-count classes. Runtime, provider, date, workspace, and attempt classes are metadata only, not row identity. Do not include prompt/final-answer/provider text, stdout/stderr, transcripts, argv/env values, secrets, auth paths, account data, absolute paths, ignored raw artifact paths, hashes, or provider session identifiers.

Policy tests validate this shape through `tests.helpers.persona_summary`, shared
with Phase 4 live-smoke class-only negative cases. The helper is test-only;
scripts and product code must not import it.
