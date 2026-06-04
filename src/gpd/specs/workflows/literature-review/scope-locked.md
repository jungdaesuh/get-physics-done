<purpose>
Load scoped reference artifacts and assemble the reviewer handoff after the review scope is fixed.
</purpose>

<process>

<step name="load_scoped_reference_artifacts">
Once the scope is fixed, surface only the reference artifacts that remain relevant to the agreed topic.

```bash
SCOPE_LOCKED_INIT=$(load_literature_review_stage scope_locked "${topic:-$ARGUMENTS}")
if [ $? -ne 0 ]; then
  echo "ERROR: gpd initialization failed: $SCOPE_LOCKED_INIT"
  exit 1
fi
```

- Apply `SCOPE_LOCKED_INIT.staged_loading.field_access_instruction` before reading `SCOPE_LOCKED_INIT`.
- If `reference_artifact_files` is populated, read those files now and keep only the entries that support the confirmed scope.
- Carry forward the scoped file handles; do not rely on embedded artifact bodies in this handle-first stage.
- Only read or propagate the deferred reference-artifact context after the scope has been fixed.
- Do not use deferred reference artifacts to reopen the scope question.
</step>

<step name="identify_foundations">
**Phase 1: Foundational Works**

Every subfield has seminal papers that defined the field. Identify them:

1. Search for review articles first (they cite the seminal works):

   ```
   web_search: "[topic] review" site:arxiv.org
   web_search: "[topic]" site:journals.aps.org/rmp
   ```

2. From review articles, extract:

   - The 5-10 most-cited papers
   - The textbook treatments
   - The original derivation of key results

3. For each foundational work, record:

   - Full citation (authors, title, journal, year)
   - Stable `anchor_id` and concrete `locator` if the work is contract-critical or likely to be reused downstream
   - Key contribution (what they showed/computed/proved)
   - Method used
   - Conventions (units, metric signature, normalization)
   - Where the result is used downstream
   - Whether it should be treated as a contract-critical anchor for later planning or verification

4. Build a citation timeline showing how the field developed.
   </step>

<step name="map_methods">
**Phase 2: Methodological Landscape**

Catalog all methods that have been applied to this problem:

For each method:

| Field              | Detail                                                              |
| ------------------ | ------------------------------------------------------------------- |
| Method name        | Formal name and common abbreviations                                |
| Type               | Analytical / Numerical / Mixed                                      |
| Key idea           | One-sentence description of the approach                            |
| Regime of validity | Where it works (weak coupling, high T, large N, etc.)               |
| Limitations        | Where it fails (strong coupling, low dimension, sign problem, etc.) |
| Accuracy           | Typical precision achievable                                        |
| Computational cost | Scaling with system size, time, memory                              |
| Key references     | Original paper + best application to this system                    |
| Available codes    | Open-source implementations, if any                                 |

Organize methods by approach type:

- **Exact methods**: Bethe ansatz, integrability, conformal bootstrap, etc.
- **Perturbative**: Weak coupling, 1/N, epsilon expansion, etc.
- **Variational**: Trial wavefunctions, DMRG, tensor networks, etc.
- **Monte Carlo**: DQMC, PIMC, VMC, AFQMC, etc.
- **Mean-field and beyond**: Hartree-Fock, RPA, GW, DMFT, etc.
- **Effective theories**: EFT, renormalization group, etc.

Note which methods agree and where they disagree -- this reveals the interesting physics.
</step>

<step name="catalog_results">
**Phase 3: Key Results Catalog**

For each significant result in the literature:

| Field       | Detail                                                                 |
| ----------- | ---------------------------------------------------------------------- |
| Quantity    | What was computed (energy, correlation function, phase boundary, etc.) |
| Value       | Numerical result or analytical expression                              |
| Method      | How it was obtained                                                    |
| Uncertainty | Error bars, systematic uncertainties, convergence status               |
| Conventions | Units, normalization, sign conventions used                            |
| Regime      | Parameter values, approximations in effect                             |
| Reference   | Full citation                                                          |
| Agreement   | How it compares with other determinations                              |

Tabulate results for the SAME quantity across different papers/methods to expose:

- Agreement (convergence of independent methods)
- Disagreement (controversial values)
- Trends (how results evolved as methods improved)
- Which values are decisive benchmarks versus optional background comparisons
  </step>

<step name="trace_citations">
**Phase 4: Citation Network Analysis**

Map intellectual lineages:

1. **Method lineages**: paper_A -> paper_B -> paper_C (each improving on the previous)
2. **Competing approaches**: lineage_X vs lineage_Y (different methods for same problem)
3. **Reconciliation**: papers that compared or unified different approaches
4. **Branching points**: where the field split into sub-problems

This reveals:

- Which methods are still actively developed (recent citations)
- Which are considered superseded (cited only for historical context)
- Which groups are leading each approach
- Where cross-pollination between approaches has been fruitful
  </step>

<step name="find_controversies">
**Phase 5: Controversies and Disagreements**

Actively search for disagreements in the literature:

1. **Numerical discrepancies**: Different groups get different values for the same quantity

   - How significant is the disagreement? (In sigma)
   - Is the discrepancy resolution-dependent? (Finite-size, continuum limit)
   - Has anyone explained the discrepancy?

2. **Methodological disagreements**: Different methods give inconsistent results

   - Which method is more reliable in this regime?
   - Are the approximations comparable?
   - Could both be right in different limits?

3. **Conceptual disagreements**: Different physical interpretations of the same result

   - Is this a genuine physics disagreement or a convention difference?
   - What experiment or calculation could distinguish between interpretations?

4. **Convention conflicts**: Different papers use different conventions
   - Catalog convention choices across the major references
   - Note where convention mismatches could cause apparent disagreements
     </step>

<step name="identify_gaps">
**Phase 6: Open Questions**

Systematically identify what has NOT been done:

1. **Uncomputed quantities**: Observables mentioned in the literature but never calculated
2. **Unexplored regimes**: Parameter ranges where no reliable method works
3. **Unresolved puzzles**: Anomalous results with no accepted explanation
4. **Missing connections**: Two related results that nobody has connected
5. **Unverified predictions**: Theoretical predictions awaiting experimental confirmation
6. **Long-standing conjectures**: Claims without proof, supported only by numerical evidence

For each gap:

- Why hasn't it been addressed? (Too hard? Not important enough? Technical obstacle?)
- What would it take to address it? (Better methods? More computing power? New data?)
- What would we learn? (Is it worth the effort?)
- Whether a missing anchor or missing benchmark is currently blocking downstream planning
  </step>

<step name="assess_frontier">
**Phase 7: Current Frontier**

Map the state-of-the-art:

1. **Most recent results** (last 1-2 years)

   - What has been computed or measured recently?
   - How does it change the picture from the review articles?

2. **Active groups**

   - Which groups are producing results in this area?
   - What methods are they using?
   - What are their current projects? (Check recent arXiv submissions)

3. **Emerging methods**

   - New theoretical or computational approaches being applied
   - Machine learning / AI applications to this problem
   - New experimental techniques

4. **Community direction**
   - What was discussed at recent conferences?
   - Where is the field heading?
     </step>

<step name="create_review_document">
The reviewer now owns the synthesis pass in fresh context. Use the stage-local scope, anchors, and reference context to write the review and sidecar, rather than synthesizing it inline in the orchestrator.

```bash
REVIEWER_MODEL=$(gpd resolve-model gpd-literature-reviewer)
```

Build the reviewer prompt from the scoped evidence:

```markdown
<objective>
Write a systematic literature review for {topic} and produce the matching review document and citation-sidecar outputs.
</objective>

<scope_summary>
Topic: {topic}
Slug: {slug}
Depth: {depth}
Seed anchors: {seed_anchors}
Confirmed boundaries: {scope_boundaries}
Contract-critical anchors: {contract_critical_anchors}
</scope_summary>

<context>
Project contract: {project_contract}
Contract intake: {contract_intake}
Effective reference intake: {effective_reference_intake}
Active references: {active_reference_context}
Scoped reference artifact file handles: {reference_artifact_files}
</context>

<output>
Write `GPD/literature/{slug}-REVIEW.md` and `GPD/literature/{slug}-CITATION-SOURCES.json`.
</output>

<citation_sidecar_contract>
`GPD/literature/{slug}-CITATION-SOURCES.json` is a JSON array of strict `CitationSource` objects with stable `reference_id`; `year` is a string; Extra keys are rejected by the downstream parser; audit-only fields such as `verification_status`, `canonical_identifiers`, and `verification_sources` stay in `GPD/literature/{slug}-CITATION-AUDIT.md`. Compact shape: `[{"source_type":"paper","reference_id":"ref-main","bibtex_key":"Ref2026","title":"Fixture Reference","authors":["Ada Example"],"year": "2026","journal":"Journal of Fixture Physics"}]`.
</citation_sidecar_contract>

<spawn_contract>
write_scope:
  mode: scoped_write
  allowed_paths:
    - GPD/literature/{slug}-REVIEW.md
    - GPD/literature/{slug}-CITATION-SOURCES.json
expected_artifacts:
  - GPD/literature/{slug}-REVIEW.md
  - GPD/literature/{slug}-CITATION-SOURCES.json
shared_state_policy: return_only
</spawn_contract>
```

```
REVIEW_RETURN=$(
task(
  subagent_type="gpd-literature-reviewer",
  model="{reviewer_model}",
  readonly=false,
  prompt="First, read {GPD_AGENTS_DIR}/gpd-literature-reviewer.md for your role and instructions.\\n\\n" + review_prompt
)
)
```

**If the reviewer agent fails to spawn or returns an error:** Report the failure and stop. Offer: 1) Retry with the same scope, 2) Execute the review in the main context, 3) Abort.

**If the reviewer reports completed:** apply the review artifact gate for
`GPD/literature/{slug}-REVIEW.md` and
`GPD/literature/{slug}-CITATION-SOURCES.json`; if either artifact fails, keep
the handoff incomplete.

**If the reviewer checkpoints:** collect the response, use
`references/orchestration/continuation-boundary.md`, and rerun the review gate
before advancing.

**If the reviewer blocks or fails:** surface the blocker and offer: 1) Add
context, 2) Narrow scope, 3) Abort.

</step>

</process>
