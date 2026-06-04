# Planner Autonomy Policy

Autonomy controls decision authority and checkpoint density. It never relaxes
the approved contract, required anchors, forbidden proxies, proof obligations,
or acceptance tests.

## Mode Effects

### Supervised mode (`autonomy: "supervised"`)

- Insert `checkpoint:human-verify` after every task that produces a material
  physics result.
- Insert `checkpoint:decision` before every approximation, convention, method,
  or scope choice that changes downstream meaning.
- Every inserted `checkpoint:human-verify` uses the `[Y/n/e]` resume-signal
  idiom (Enter = Y); see
  `{GPD_INSTALL_DIR}/references/orchestration/checkpoint-ux-convention.md`.
- Plans must stay exactly inside CONTEXT.md locked decisions and the approved
  contract. Human checkpoints decide how to satisfy those requirements, not
  whether they apply.
- Set plans interactive when they carry physics decision points.

### Balanced mode (`autonomy: "balanced"`)

- Insert checkpoints at phase boundaries and key physics decisions.
- Keep routine standard work non-interactive.
- Use standard conventions and approximations when the record makes them clear.
- If validity is borderline, add a validity-check task or checkpoint depending
  on downstream risk.
- Adjust implementation choices only inside the approved contract.

### YOLO mode (`autonomy: "yolo"`)

- Auto-continue on clean passes, but preserve first-result gates, required
  anchors, pre-fanout checkpoints, and hard stops.
- Hard stops include failed sanity gates, unresolved convention conflicts,
  circuit-breaker behavior, context RED, or an approximation switch that would
  change interpretation.
- You may refine decomposition and add internal validation, but do not widen or
  rewrite the approved contract, anchors, forbidden proxies, or locked user
  decisions without a checkpoint or roadmap revision.

## Planning Decision Matrix

| Decision | Supervised | Balanced | YOLO |
| --- | --- | --- | --- |
| Convention selection | Checkpoint | Auto if standard; checkpoint if non-standard or conflicting | Auto if consistent with lock |
| Approximation choice | Checkpoint with options | Auto if standard; add validity task or checkpoint if borderline | Auto only inside approved framing |
| Scope adjustment | Never | Limited inside approved contract; checkpoint structural changes | Only inside approved contract and milestone objectives |
| Method selection | Checkpoint with options | Auto if `RESEARCH.md` or literature is clear; otherwise checkpoint | Auto |
| Limiting case selection | Checkpoint | Auto for standard and obviously missing safeguards | Auto minimal set |
| Gap closure approach | Checkpoint per gap | Auto targeted fixes; checkpoint diagnostic/structural changes | Auto targeted fixes; checkpoint structural changes |
| Phase revision | Always checkpoint | Checkpoint structural, auto targeted | Auto targeted, checkpoint structural |

## Interaction With Research Mode

| Autonomy | Explore | Balanced research | Exploit |
| --- | --- | --- | --- |
| Supervised | User approves each tangent decision before it becomes a branch or side investigation | Standard plus checkpoints | Focused and verified at each step |
| Balanced | Broad search, but tangent choices are surfaced explicitly | Default research flow | Efficient execution with key checkpoints |
| YOLO | Broad search inside approved scope; tangent choices still stay explicit | Fast auto research loop | Fast convergent execution |
