# Planner Protocol Bundle Planning

Selected protocol bundle guidance is additive and subordinate to the approved
contract. It helps order tasks, choose benchmark gates, and surface pitfalls;
it never changes `project_contract`, PLAN `contract`, required anchors,
forbidden proxies, locked user decisions, or proof obligations.

## Selection Order

1. If init JSON or child context exposes selected bundle `planning_guides`,
   load only those guide assets and use them as the dependency skeleton.
2. If selected bundle context has no planner-specific guides, use estimator
   policies, decisive artifact guidance, verifier extensions, and asset notes
   to identify benchmark-before-production, convergence, proof, convention, or
   artifact tasks.
3. If no bundle guidance is selected or it is insufficient, load
   `{GPD_INSTALL_DIR}/references/planning/domain-strategy-index.md` and then
   only the one or two matching guide files from that index.
4. For cross-domain work, decide which domain supplies the physics and which
   supplies the method. Load
   `{GPD_INSTALL_DIR}/references/planning/cross-domain-convention-bridge.md`
   when results cross convention boundaries.

## Fallback Skeleton

```text
contract gate -> convention lock -> approximation/regime declaration
-> method/blueprint decision -> benchmark or proof setup
-> derivation/implementation -> validation against dimensions, limits,
   symmetries, conservation laws, convergence, anchors, and disconfirming cases
-> decisive artifact and return contract
```

## Preservation Rules

- Preserve user decision fidelity: locked decisions are requirements; deferred
  ideas remain out of scope.
- Preserve tangent control: multiple viable main lines require a checkpoint or
  explicit tangent route, not branch-like plans.
- Preserve proof-bearing safety: non-`other` proof claims need auditable
  hypotheses, parameters, conclusions, proof deliverables, and proof-redteam
  paths.
- Preserve tool safety: specialized runtime assumptions go in
  `tool_requirements`, not only task prose.
- Preserve return-only ownership: roadmap updates and shared-state changes are
  returned through `gpd_return`, not silently written unless explicitly
  delegated.
