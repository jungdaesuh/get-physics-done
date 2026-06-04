# Phase 4 Persona Live Smoke

This runbook defines the optional manual live-smoke policy for Phase 4 persona
checks. It is not a CI runner.

## Policy

- Manual live is opt-in. Pull request, push, release, and publish jobs must not
  launch provider CLIs or receive provider secret environment names.
- CI coverage for Phase 4 persona behavior is provider-free replay and
  sanitized-summary validation only. CI may validate class-only evidence, but it
  must not create live provider artifacts or start a provider runtime.
- The operator chooses the row set, budget, provider account, runtime homes, and
  isolated workspace before any provider process is started.
- Use stable row ids for the selected rows. A row id names the behavior under
  observation; runtime, provider account, date, workspace, and attempt values are
  metadata only and must not create alternate row identities.
- Raw live artifacts stay ignored and operator-local under a repo-local root like
  `tmp/phase4-persona-live-YYYYMMDD/`. Store row attempts under
  `tmp/phase4-persona-live-YYYYMMDD/raw/<row_id>/<runtime_class>/<attempt_id>/`.
  Keep prompts, replies, stdout/stderr, transcripts, argv/env captures,
  auth/account material, command files, hashes, token material, absolute local
  paths, generated attempt ids, and provider output out of tracked files.
- Public review may include only a sanitized class-only summary. The summary may
  contain row ids, class fields, behavior classes, aggregate or behavior counts,
  redaction status, and finding classes. It must not contain raw prompts,
  provider replies, stdout/stderr, transcripts, argv/env values, auth/account
  data, absolute paths, hashes, provider secret env names, command lines, or
  token-like values. Use command/action classes and behavior metric counts
  instead of copied prompt prose or live transcript excerpts.
- CI may validate an already-produced sanitized summary with
  `scripts/validate_phase4_persona_summary.py`. CI must not create live provider
  artifacts or execute a provider launcher.

## Manual Sequence

1. Create a fresh ignored local root, for example
   `tmp/phase4-persona-live-YYYYMMDD/`, with raw row attempts under
   `raw/<row_id>/<runtime_class>/<attempt_id>/`.
2. Freeze the checkout state and record only class-level operator notes for
   public reporting.
3. Run the selected stable row ids manually from the operator machine. Stop on
   unexpected mutation, budget exhaustion, provider auth uncertainty, redaction
   failure, or any need to mint a runtime/provider/date-specific row id.
4. Produce a sanitized summary and validate it locally:

   ```bash
   uv run python scripts/validate_phase4_persona_summary.py tmp/phase4-persona-live-YYYYMMDD/summary.json
   ```

5. Share only the validated class-only summary unless a maintainer explicitly
   requests private debugging material.

## Public Summary Shape

Use schema `phase4.persona-live-smoke-summary.v1`.

Required top-level policy fields:

- `execution_mode_class`: `manual_opt_in`
- `trigger_class`: `operator_local_manual`
- `raw_artifact_retention_class`: `operator_local_ignored_tmp`
- `public_artifact_class`: `sanitized_class_only_summary`
- `provider_launch_source_class`: `manual_operator`
- `ci_provider_launch_allowed`: `false`

Rows may include canonical `row_id`, runtime/persona/workflow/gate/result/
next-action classes, write class, behavior classes, behavior metric counts,
redaction status class, finding classes, and event class counts. Runtime,
provider, date, workspace, and attempt fields are metadata classes only, not row
identity. Count maps should use class tokens as keys and integers as values.
Scalar count fields should be non-negative integers.
