# Executor Protocol Bundle Execution

Load this reference when `<selected_protocol_bundle_ids>` is non-empty, `protocol_bundle_context` names selected execution assets, selected bundles provide verifier extensions or estimator policies, or no selected bundle covers a needed method and the executor must fall back to a generic guard.

The executor consumes selected bundle context; it does not select bundles. Selection belongs to init/context surfaces and `protocol_bundles.py`.

## Core Rules

- Selected bundle guidance is additive specialized guidance only.
- Load only selected asset paths named by `<protocol_bundle_context>` or `<protocol_bundle_load_manifest>`.
- Keep unselected bundle catalogs absent.
- Selected assets cannot relax approved contract anchors, forbidden proxies, first-result gates, acceptance tests, decisive evidence obligations, or shared-state return boundaries.
- If selected context is absent or incomplete, use `{GPD_INSTALL_DIR}/references/execution/executor-index.md` and `{GPD_INSTALL_DIR}/references/execution/guards/README.md` only as a minimal fallback.

## Loading Order

1. Read `<selected_protocol_bundle_ids>`, `<protocol_bundle_load_manifest>`, `<protocol_bundle_context>`, and `<protocol_bundle_verifier_extensions>` from the spawn prompt or init JSON.
2. Prefer selected bundle `execution_guides` for the active method/domain.
3. Load selected core protocols before work enters that method family.
4. Load selected optional protocols only when the task actually enters that method family.
5. Load selected verification-domain docs and verifier extensions before final verification or SUMMARY claims.
6. If selected assets miss a required method check, load the guard README and one matching guard file. Do not load the full catalog.
7. If no selected or fallback domain fits, stay with generic execution flow plus contract-backed anchors and checks instead of forcing the work into a topic bucket.

## Asset Roles

- `project_templates`: clarify decisive artifacts and phase structure.
- `subfield_guides`: clarify standard methods, pitfalls, and benchmark language.
- `protocols`: control method-specific execution discipline.
- `verification_domains`: define final checks before a result is believable.
- `execution_guides`: provide selected method/domain guardrails during implementation.
- `estimator_policies`: specify acceptable error, uncertainty, or comparison policy.
- `decisive_artifacts`: identify outputs that must appear for contract-backed success.

## Carry-Forward

Carry selected estimator policies, decisive artifact requirements, and final verification notes into the work log and SUMMARY. When a contract item conflicts with bundle guidance, the contract wins.

Before declaring success:

- confirm every selected verifier extension relevant to the produced result was applied or explicitly marked not applicable;
- confirm contract-backed anchors and forbidden-proxy decisions are reflected in `contract_results`;
- confirm decisive comparisons are reflected in `comparison_verdicts` when required or attempted;
- record any selected-bundle gap as an issue or next action rather than silently broadening the bundle.

If the work changes formulation mid-plan, load additional selected or fallback protocols on demand and record the shift. Do not stay trapped in the original bundle or fallback subfield when the actual computation demands a different method family.
