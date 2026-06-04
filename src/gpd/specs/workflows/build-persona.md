<purpose>
Build a robust private research persona candidate without silently changing
machine-local persona storage.

The workflow interviews the user only after explicit consent, scans local
project evidence only after explicit path-scoped consent, and emits a candidate
`ResearchPersonaPatch` JSON object for user approval. The approval and storage
mutation path is the Phase 2 local CLI: `gpd research-persona diff` followed by
`gpd research-persona apply-patch`.

No silent memory: do not silently create, infer, or update persona memory from
ordinary chat context, project scans, or prior behavior. Explicit user approval
is required before mutation; do not apply-patch until approval is given after
the candidate patch and diff are reviewed.
</purpose>

<hard_boundaries>
- Never write `${GPD_DATA_DIR:-~/.gpd}/research-persona/profile.json` directly.
- Never run `gpd research-persona apply-patch` on the user's behalf unless the
  user explicitly asks after reviewing the candidate patch.
- Never infer permission to interview, inspect papers, inspect collaborators,
  inspect git history, or scan files from command invocation alone.
- Never include `never_prompt` facts in prompt-visible summaries.
- Treat collaborator names, unpublished project details, personal workflow
  habits, and sensitive preferences as private unless the user explicitly marks
  them `safe_to_share`.
- Prefer `private_local` for new facts unless the user chooses a narrower or
  broader privacy label.
</hard_boundaries>

<required_reading>
Read all files referenced by the invoking prompt's execution_context before
starting. Use the local research-persona CLI controls as the storage authority:

- `gpd research-persona show --projection local|project-private|prompt|public`
- `gpd research-persona validate <profile.json|- >`
- `gpd research-persona diff <patch.json|- >`
- `gpd research-persona apply-patch <patch.json|- >`
- `gpd research-persona forget <fact-id>`
- `gpd research-persona export-capsule --role planner|executor|verifier|paper_writer|literature|recovery|explainer|doppelganger|taste`
</required_reading>

<process>

<step name="load_existing_snapshot">
Inspect only the local persona shape and counts first. This read is allowed
because the user explicitly invoked persona building, but keep it local and do
not inject raw private content into later prompts.

```bash
PERSONA_STATUS=$(gpd --raw research-persona show --projection local)
if [ $? -ne 0 ]; then
  echo "$PERSONA_STATUS"
  # Continue with an empty-draft mindset only if the error says the profile is missing.
fi
```

Use this payload to avoid duplicate fact IDs and to know whether the user is
building from scratch or updating an existing profile. Do not copy raw profile
contents into delegated prompts or final prose.
</step>

<step name="consent_gate">
Before asking any interview questions or scanning any local files, ask for
explicit scope consent.

If `ask_user` is available, present exactly these mutually exclusive choices:

- `Interview only` -- ask focused questions; do not inspect local files.
- `Interview plus current project` -- ask questions and read only explicitly
  relevant files in the current workspace after listing the categories.
- `Stop` -- do not collect persona facts.

If `ask_user` is not available, present the same options in plain text and wait
for a freeform response.

If the user chooses `Stop`, end without emitting a patch.
If the user chooses project scanning, ask one follow-up listing the path
categories to allow, such as `GPD/STATE.md`, `GPD/ROADMAP.md`,
`GPD/knowledge/*.md`, `GPD/literature/*.md`, manuscript files, source package
metadata, or selected paper/reference files. Only read categories the user
approved.
</step>

<step name="interview">
Ask a compact interview tailored to the requested scope. Do not ask all
questions if the user's answers already resolve the scope.

Cover these dimensions when relevant:

1. Research areas, subfields, and current problems.
2. Expertise level by axis: mathematical, computational, experimental,
   theoretical, applied, literature/navigation, and writing/publication.
3. Preferred explanation style: abstraction level, derivation density, code
   detail, examples, notation strictness, and citation depth.
4. Scientific taste: what the user sees as elegant, suspicious, promising,
   boring, overfit, under-justified, or worth pursuing.
5. Workstyle: cadence, checkpoint preference, tolerance for autonomous action,
   preferred tools, languages, notebooks, symbolic/numeric packages, and
   testing expectations.
6. Papers, collaborators, references, datasets, software, or groups the user
   wants remembered.
7. Privacy defaults: which items are `private_local`, `project_private`,
   `safe_to_share`, `session_only`, or `never_prompt`.

Keep questions grouped. When an answer contains sensitive personal details, ask
whether to store that item at all and which privacy label to use.
</step>

<step name="consented_scan">
If the user approved local scanning, perform a narrow read-only survey of only
approved paths. Use this scan to propose candidate facts; never treat it as
confirmed ground truth unless the user confirms it.

Useful read-only checks include:

```bash
find GPD -maxdepth 3 -type f 2>/dev/null | sort | head -80
rg -n --glob '*.md' --glob '*.tex' --glob 'pyproject.toml' --glob 'package.json' --glob 'Cargo.toml' "arXiv|doi|collaborat|author|method|theorem|simulation|experiment|notebook|pytest|ruff|numpy|jax|mathematica|wolfram|latex" . 2>/dev/null | head -120
```

Do not inspect private credential files, environment files, browser caches,
home-directory documents, email, chat exports, or git remotes unless the user
explicitly names those exact sources for this persona-building run.
</step>

<step name="draft_patch">
Convert confirmed interview answers and user-approved scan inferences into a
single candidate `ResearchPersonaPatch` JSON object.

Patch requirements:

- Top-level `schema_version` is `1`.
- Use `source_kind: "interview"` for directly stated answers.
- Use `source_kind: "project_scan"` for consented local evidence, with
  `confidence: "inferred"` unless the user confirmed the fact.
- Prefer stable fact IDs such as `interest.quantum-field-theory`,
  `expertise.math.derivations`, `workstyle.tests.pytest`, or
  `taste.prefers-mechanistic-explanations`.
- Use `add_fact`, `replace_fact`, `add_axis`, `replace_axis`, `add_list_item`,
  `remove_list_item`, or pointer operations supported by the research-persona
  patch schema.
- Include `sources`, `privacy`, `confidence`, and `updated_at` on every fact.
- Use `safe_to_share` only when the user explicitly chooses it.
- Use `never_prompt` for facts that may be retained locally for audit or
  duplicate suppression but must never enter prompt capsules.
- Keep collaborator and unpublished-project facts `private_local` or
  `project_private` unless the user explicitly chooses otherwise.

For scientific-taste facts, capture preferences as reviewable hypotheses, not
identity claims. Example categories include:

- `taste.values_elegant_minimal_models`
- `taste.suspicious_of_unchecked_numerics`
- `taste.prefers_first_principles_derivations`
- `taste.likes_cross_regime_consistency_checks`

For Researcher Doppelganger support, include only user-approved style and taste
facts that help a future role critique plans in the user's voice. Do not invent
personal opinions.

For Expertise-Aware Explanations support, include explanation-depth facts and
axes that help future explainers choose prerequisite level, math density, code
examples, and citation depth.
</step>

<step name="validate_candidate">
Write the candidate patch to the response as a fenced JSON block or, if a local
temporary file is needed for validation, use `/tmp` and keep it outside persona
storage. Then validate with the local CLI before presenting it as ready:

```bash
gpd --raw research-persona diff /tmp/research-persona-candidate-patch.json
```

If diff fails, fix the patch and re-run until the CLI accepts it, or report the
schema error and stop without suggesting application.
</step>

<step name="present_for_approval">
Present:

1. A short summary of what the patch would add, replace, or remove.
2. The complete candidate `ResearchPersonaPatch` JSON.
3. The approval commands:

```bash
gpd research-persona diff /tmp/research-persona-candidate-patch.json
gpd research-persona apply-patch /tmp/research-persona-candidate-patch.json
```

If no temporary file was written, tell the user they can pass the JSON through
stdin:

```bash
gpd research-persona diff -
gpd research-persona apply-patch -
```

Make clear that `apply-patch` is the mutation step and must be user-approved.
Offer `gpd research-persona forget <fact-id>` for later deletion.
</step>

<step name="capsule_check_optional">
If the user asks how the patch would affect future behavior, explain that
projected capsules are role-specific and privacy-filtered. The relevant local
checks are:

```bash
gpd research-persona export-capsule --role planner
gpd research-persona export-capsule --role explainer
gpd research-persona export-capsule --role doppelganger
gpd research-persona export-capsule --role taste
```

Do not run these against newly proposed facts until the user applies the patch.
</step>

</process>

<success_criteria>
- [ ] Existing persona inspected only through local CLI projection
- [ ] Explicit consent collected before interview or scans
- [ ] Scans restricted to user-approved local path categories
- [ ] Candidate facts have source kind, confidence, privacy, and stable IDs
- [ ] Candidate patch validates through `gpd research-persona diff`
- [ ] Final answer includes the full candidate patch and separate approval route
- [ ] No direct write to research-persona storage occurred
</success_criteria>
