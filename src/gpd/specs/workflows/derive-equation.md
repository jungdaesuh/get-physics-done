<purpose>
Perform a rigorous physics derivation with explicit assumptions, locked
conventions, checkable algebra, decisive physics checks, and honest persistence.
</purpose>

<core_principle>
A derivation is a proof chain from stated assumptions to a stated result. Every
major step must expose the operation, conventions, approximation domain, and at
least one decisive check. Intuition may motivate the route; it does not certify
the result.
</core_principle>

<references>
Use `{GPD_INSTALL_DIR}/references/analysis/physics-validation-recipes.md` when
executing detailed dimensional, limiting-case, symmetry, numerical spot-check,
and common-pitfall recipes. Do not eager-load that reference before the target
and proof-bearing status are known.
</references>

<derivation_standards>
- State assumptions, definitions, conventions, and starting point before
  algebra.
- Include `ASSERT_CONVENTION` in the document header and in convention-sensitive
  derivation steps.
- Name each major operation and show enough intermediate algebra to verify it.
- Justify approximations with the neglected term, validity parameter, and error
  scale.
- Keep dimensions, known limits, symmetries, and complex/algebraic spot-checks
  visible as decisive checks.
- Box the final expression and state validity domain, interpretation, and links
  to known or prior results.
</derivation_standards>

<process>

<step name="load_context">
Load current-workspace state and conventions. This workflow may run as a
standalone/current-workspace analysis, so bootstrap must not auto-reenter an
ancestor or recent project.

```bash
INIT=$(gpd --raw init progress --include state,config --no-project-reentry)
if [ $? -ne 0 ]; then
  echo "ERROR: gpd initialization failed: $INIT"
  # STOP; surface the error.
fi
```

Parse `workspace_root`, `project_root`, `state_exists`, `current_phase`,
`convention_lock`, `derived_convention_lock`, and continuation/runtime fields.
Treat phase context as authoritative only when the bootstrap surfaces a concrete phase number and phase directory. Do not synthesize a phase-local output path from an ancestor project root or an unverified phase guess.

If project state exists, inspect conventions, active approximations, validity
ranges, prior notation, and `intermediate_results`; inspect `intermediate_results` before re-deriving. Check existing canonical equation/result entries related to the target. Use `gpd result search` to locate the canonical result first; once a canonical `result_id` is known, use `gpd result show "{result_id}"` for the direct stored-result view before deciding whether a fresh derivation is needed. If state exists but phase context is not authoritative, keep background visible but write under `GPD/analysis/` and skip registry persistence.

Run convention verification before deriving when a project exists:

```bash
CONV_CHECK=$(gpd --raw convention check 2>/dev/null)
if [ $? -ne 0 ]; then
  echo "WARNING: Convention verification failed — review before deriving"
  echo "$CONV_CHECK"
fi
```
</step>

<step name="state_problem">
Write the derivation objective before calculating:

```markdown
## Derivation Objective

**Goal:** Derive [expression/relation/equation] for [system/quantity].
**Starting point:** [Given Lagrangian/Hamiltonian/action/equation]
**Expected result:** [Known expression or symmetry/dimensional form]
**Method:** [Variational/perturbative/exact/saddle-point/RG/etc.]
```
</step>

<step name="proof_obligation_screen">
Proof-bearing derivations fail closed. If the objective is theorem-style or
contract-backed `proof_obligation` work, proof review is mandatory before the
result can be treated as established.

@{GPD_INSTALL_DIR}/references/verification/core/proof-redteam-workflow-gate.md

For proof-bearing derivations, carry this theorem inventory through the
document:

```markdown
## Proof Inventory

- **Claim / theorem target:** [exact statement being proved]
- **Named parameters:** [symbol -> role / domain]
- **Hypotheses:** [H1, H2, ...]
- **Quantifier / domain obligations:** [for all x in ..., exists y such that ...]
- **Conclusion clauses:** [what the proof must establish]
```

Reserve the sibling proof-redteam artifact:

- **Phase-scoped:** `${phase_dir}/DERIVATION-{slug}-PROOF-REDTEAM.md`
- **Standalone:** `GPD/analysis/derivation-{slug}-proof-redteam.md`

`gpd-check-proof` is the canonical owner of that audit whenever runtime
delegation is available. If delegation is unavailable, stop at a checkpoint
rather than self-certifying theorem-proof alignment in the writer context.
</step>

<step name="establish_framework">
Write numbered assumptions, definitions, conventions, and the starting point.
If a project convention lock exists, every declared convention must match it; a
drift is a hard stop until corrected through `gpd convention set` or by using
the locked convention.

```markdown
## Assumptions

A1. [Physical assumption]: [justification and validity regime]
A2. [Mathematical assumption]: [failure mode]

## Definitions

| Symbol | Meaning | Dimensions | Defined by |
| --- | --- | --- | --- |
| {symbol} | {name} | {[dimensions]} | {equation or convention} |

## Conventions

<!-- ASSERT_CONVENTION: natural_units={from lock}, metric_signature={from lock}, fourier_convention={from lock} -->

## Starting Point

[Expression with indices, factors, source, and dimensional check.]
```
</step>

<step name="derive_step_by_step">
For each major operation:

1. Name the operation: variation, integration by parts, expansion, saddle
   approximation, series sum, analytic continuation, basis projection, etc.
2. Show the key algebra with enough context that a physicist can verify it.
3. Record the convention assertion for the step.
4. Check dimensions, at least one simple limit, and relevant symmetry.
5. For approximations, state the neglected terms, the controlling parameter,
   and the leading error scale.

If any convention assertion differs from Step 1 or from the project lock, stop
immediately and resolve the drift before combining results.
</step>

<step name="verify_intermediate">
At natural sub-calculation boundaries, run decisive checks:

- dimensional consistency;
- known or simple limiting cases;
- symmetry preservation or covariance;
- numerical spot-checks for algebraically complex equations;
- cross-phase consistency when combining prior results.

For detailed check recipes and pitfall prompts, load
`{GPD_INSTALL_DIR}/references/analysis/physics-validation-recipes.md`. When
combining prior results, re-read the prior `ASSERT_CONVENTION` lines and run
`gpd --raw convention check 2>/dev/null` if the project has a convention lock.
</step>

<step name="state_result">
State the final result with:

```markdown
## Result

Under assumptions A1-A{N}, the [quantity] is

$$
\boxed{[final expression]}
$$

**Dimensions:** [verified]
**Regime of validity:** [where this holds]
**Interpretation:** [physical meaning]
**Limiting cases verified:** [table or bullets]
**Connection to known results:** [known reductions or extensions]
```
</step>

<step name="document_derivation">
Write a self-contained derivation artifact with frontmatter, objective,
assumptions, definitions, conventions, starting point, derivation, result,
verification, error analysis, and references.

Save to:

- **Phase-scoped (authoritative phase context only):** `${phase_dir}/DERIVATION-{slug}.md`
- **Current-workspace fallback (standalone or no authoritative phase context):** `GPD/analysis/derivation-{slug}.md`

Create `GPD/analysis/` only for the fallback branch:

```bash
mkdir -p GPD/analysis
```

For proof-bearing work, reserve the sibling audit path listed in
`proof_obligation_screen`. Do not have the derivation writer self-author that
audit. If any named parameter, hypothesis, quantifier, or conclusion clause is
uncovered, `gpd-check-proof` must set `status: gaps_found` and the derivation
must not describe the theorem as established.

Resolve the proof-critic model and spawn the independent critic:

```bash
CHECK_PROOF_MODEL=$(gpd resolve-model gpd-check-proof)
```

@{GPD_INSTALL_DIR}/references/orchestration/runtime-delegation-note.md

```
task(
  subagent_type="gpd-check-proof",
  model="{check_proof_model}",
  readonly=false,
  prompt="First, read {GPD_AGENTS_DIR}/gpd-check-proof.md for your role and instructions.
Then read {GPD_INSTALL_DIR}/templates/proof-redteam-schema.md and {GPD_INSTALL_DIR}/references/verification/core/proof-redteam-protocol.md.
Operate in proof-redteam mode with a fresh context.
Follow the proof-redteam protocol's one-shot return semantics.

Write to:
- `${phase_dir}/DERIVATION-{slug}-PROOF-REDTEAM.md` when authoritative phase context is phase-scoped
- `GPD/analysis/derivation-{slug}-proof-redteam.md` when using the current-workspace fallback

<spawn_contract>
write_scope:
  mode: scoped_write
  allowed_paths:
    - ${phase_dir}/DERIVATION-{slug}-PROOF-REDTEAM.md
    - GPD/analysis/derivation-{slug}-proof-redteam.md
expected_artifacts:
  - one proof-redteam artifact at the selected path above
shared_state_policy: return_only
</spawn_contract>

Read the derivation artifact, theorem inventory, relevant PLAN/contract context, and supporting verification artifacts. Audit the exact theorem text, not a paraphrase. Fail closed on missing parameter coverage, hidden assumptions, or narrower special-case proofs sold as general claims.",
  description="Proof redteam for derivation {slug}"
)
```
</step>

<step name="persist_result">
Persist only project-backed, authoritative phase results through the executable
bridge:

```bash
gpd result persist-derived --id "{result_id}" --derivation-slug "{derivation_slug}" --equation "{final_equation}" --description "{short description}" --phase "{phase}" --validity "{validity}" [--depends-on "{comma-separated ids}"]
```

If no stable `result_id` is available yet, omit `--id` and let the bridge derive
one from slug plus phase. Re-check `intermediate_results` and exact equation or
description matches before creating a duplicate. If the bridge reports multiple
matches, stop and disambiguate.

Read bridge output carefully: `requested_result_id` is the requested stable ID,
`result_id` is the actual canonical entry, and
`requested_result_redirected=true` means the canonical anchor differs from the
requested derivation-oriented ID. Carry the actual `result_id` forward for
continuation and later reruns. If the bridge reports multiple matches, stop and
disambiguate.

If `state_exists` is true but authoritative phase context is missing, skip
registry write-back and keep the artifact under `GPD/analysis/`. If
`state_exists` is false, skip registry write-back and do not invent project
state. If the bridge returns `status=skipped` with
`reason=no_recoverable_project_state`, treat it as the standalone branch.
</step>

</process>

<success_criteria>
- [ ] Convention lock loaded and verified when present.
- [ ] `ASSERT_CONVENTION` appears in the derivation header and per
  convention-sensitive step.
- [ ] Existing canonical results inspected before re-deriving.
- [ ] Assumptions, definitions, starting point, derivation operations,
  approximations, and final validity domain are explicit.
- [ ] Dimensional, limiting-case, symmetry, numerical spot-check, and
  cross-phase consistency checks are recorded where applicable.
- [ ] Proof-bearing derivations include theorem inventory, reserve the sibling
  `DERIVATION-{slug}-PROOF-REDTEAM.md` artifact, and hand it to
  `gpd-check-proof`.
- [ ] The theorem is not treated as established unless `gpd-check-proof` writes
  a passing sibling artifact.
- [ ] Project-backed results persist through `gpd result persist-derived` with
  the actual canonical `result_id` retained.
- [ ] Runs without authoritative phase context skipped registry write-back and
  stayed self-contained under `GPD/analysis/`.
</success_criteria>
