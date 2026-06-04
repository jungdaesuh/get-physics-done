# Verification Status Authority

Vocabulary boundary: `gpd-verifier` owns scientific verdicts; `verify-phase`/`verify-work` gate artifacts and route without recomputing, softening, or upgrading them. Headings are presentation only.

Target status:
- `VERIFIED`: all supporting artifacts exist, are substantive, and pass decisive checks with computation evidence; required anchors and decisive comparisons are acceptable.
- `PARTIAL`: evidence exists, but a decisive check, comparison, reference action, proof-redteam closure, or suggested contract check remains open.
- `FAILED`: required artifact/evidence is missing, incomplete, incorrect, forbidden, or failed.
- `UNCERTAIN`: expert or human judgment is required.

Top-level verification status:
- `passed`: every decisive target is `VERIFIED`, required references are completed, every `must_surface` reference has all `required_actions` recorded in `completed_actions`, decisive comparison verdicts are acceptable, forbidden proxies are rejected, proof-bearing work has passed proof-redteam artifacts, no unresolved decisive `suggested_contract_checks` remain, and no blockers remain.
- `gaps_found`: any decisive target is `FAILED` or `PARTIAL` because required evidence, computation, comparison, reference action, proof-redteam closure, forbidden-proxy rejection, or suggested decisive check is missing or failed.
- `expert_needed`: automated/computational checks pass, but domain-expert judgment remains.
- `human_needed`: automated/computational checks pass, but non-expert human input or a user decision remains.

Runtime return status is separate: `completed` means the verifier process wrote a schema-valid report; `checkpoint` stops for fresh continuation; `blocked` means required artifacts/prerequisites could not be produced or validated; `failed` means process failure. Do not use top-level `failed` for a scientific or evidence gap.

Accept `completed` only after the artifact gate passes: report exists, report path is in `gpd_return.files_written`, validation passes, and required proof-redteam artifacts report `status: passed`. Fail closed on missing/invalid frontmatter, missing `files_written`, stale reports, omitted comparison verdicts, open proof-redteam audits, unresolved suggested decisive checks, or missing required reference actions.
