# Contract Authority Gate

Use when a workflow sees `project_contract`, `project_contract_gate`, `project_contract_load_info`, or `project_contract_validation`.

- `project_contract` is approved scope only when `project_contract_gate.authoritative` is true.
- A visible blocked contract is diagnostic context, not planning, execution, verification, fingerprint/alignment, or delegation authority.
- Before those authoritative uses, obey the lifecycle preflight and stop fail-closed if the gate is not authoritative.
- When blocked, surface the gate/load/validation payloads, route to contract repair, and do not infer approved scope from roadmap, state, manuscript, reference context, or user prose.
- Read-only review, mapping, publication, and resume flows may carry the blocked contract as context, but not as approval to close milestone, publishability, or scientific status.
- The local workflow still owns its subject, artifacts, validators, and failure route.

## Blocked Lifecycle Stop Phrase

Stop on blocked load/validation or false gate. Do not plan, execute, verify, fingerprint, align, or pass `project_contract` to subagents. Surface gate/load errors. Use `references/orchestration/stage-stop-envelope.md`: blocked/contract_gate, one repair Primary, and the owning workflow rerun command after repair.
