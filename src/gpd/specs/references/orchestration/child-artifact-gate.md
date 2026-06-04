# Child Artifact Gate

Canonical child-return acceptance gate. Stage prompts should say to run/apply the local `child_gate` tuple, keep the tuple fields visible, and avoid restating this protocol.

- Tuple fields: `id`, `role`, `return_profile`, `required_status`, `expected_artifacts`, `allowed_roots`, `freshness`, `validators`, `applicator`, `failure_route`, `status_route`, `write_allowlist`.
- Aggregate gates are separate reconciliation tuples, not child-return gates: `id`, `required_child_gates`, `expected_artifacts`, `validators`, `failure_route`.
- Route on a valid fenced `gpd_return.status` (`completed`, `checkpoint`, `blocked`, `failed`), not headings, prose, runtime status, files, commits, or preexisting artifacts.
- `completed` passes only when every required expected artifact is named in `gpd_return.files_written`, exists, is readable, satisfies allowed root/freshness rules, passes validators, and any required applicator reports `passed: true`.
- Use `gpd validate child-handoff --gate ... --return-file ...` for a read-only tuple result. Use `gpd validate handoff-artifacts ... --require-status completed` as the filesystem/return gate when expected artifacts are project-local paths/globs.
- Durable state, contract, continuation, or lineage effects require the callsite applicator, normally `gpd apply-return-updates`.
- Gate result concepts: `passed`, `mutated`, `primary_failure_class`, `failure_classes`, `selected_route`, `next_action_class`, `checked_files`, `errors`, `warnings`, `applicator_command`, `applicator_ran`.
- Failure classes: `return_missing`, `return_malformed_repairable`, `return_malformed_blocking`, `return_status_route`, `artifact_missing`, `artifact_stale`, `artifact_path_repairable`, `artifact_root_blocked`, `validator_failed`, `applicator_failed`. Read-only gates report `mutated: false`; applicator failures must report whether rollback preserved mutation boundaries.
- Recovery evidence limit: files, commits, runtime success text, and preexisting artifacts never prove success without the typed return, artifact checks, validators, and required applicator result.
- Missing/invalid returns, failed artifact checks, failed validators, or failed applicators leave the handoff incomplete. Do not synthesize, patch, or paste a child `gpd_return`; retry or run explicit main-context fallback with its own return.
- For `checkpoint`, follow the callsite `status_route` and `references/orchestration/continuation-boundary.md`; the child stops.

Callsite shape: child role; expected artifacts; allowed root/suffix/freshness; validators; applicator; status/failure routes.
