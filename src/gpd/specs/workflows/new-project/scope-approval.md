<purpose>
Own the second staged `new-project` boundary: draft, repair, explicitly approve,
validate, and persist the canonical scoping contract.
</purpose>

<first_decision>
First repair exactly one missing blocking field if needed; otherwise present the
scope contract for explicit user approval before any downstream artifact stage.
</first_decision>

<stage_boundary>
This stage may use the contract schema, grounding linkage, and canonical schema
discipline authorities. It must not read downstream project artifact or runtime
preference authorities before approval is complete.
</stage_boundary>

<bootstrap>
Load the approval-stage payload before schema-governed contract authoring:

```bash
SCOPE_APPROVAL_INIT=$(gpd --raw init new-project --stage scope_approval)
if [ $? -ne 0 ]; then
  echo "ERROR: scope-approval init failed: $SCOPE_APPROVAL_INIT"
  # STOP; surface the error.
fi
```

Follow `SCOPE_APPROVAL_INIT.staged_loading.field_access_instruction`; `<INIT>` there means `SCOPE_APPROVAL_INIT`. Use only loaded contract/status and approval authorities.
</bootstrap>

<contract_authoring>
Build a literal JSON object for the `project_contract` subsection of
`templates/project-contract-schema.md`. Follow the schema exactly: no invented
keys, no near-miss enum values, no scalar shortcuts for list fields, and no
collapsed `context_intake`, `approach_policy`, or `uncertainty_markers`.

Approval is blocked until the contract preserves:

- a core question
- at least one decisive output, claim, or deliverable
- at least one concrete anchor, reference, prior-output constraint, or baseline
- explicit missing-anchor uncertainty when the anchor is unknown
- user-named observables, deliverables, prior outputs, stop conditions, and
  rethink triggers

If a blocking field is missing, ask exactly one repair prompt targeted to that
field. Do not invent anchors, references, baselines, prior outputs, or DOI/arXiv
locators.
</contract_authoring>

<approval_gate>
Present a concise scoping summary and require explicit approval:

- header: "Scope"
- question: "Does this scoping contract look right before I generate the project artifacts?"
- options:
  - "Approve scope" -- proceed
  - "Adjust scope" -- revise before writing files
  - "Review raw contract" -- show the structured contract
  - "Stop here" -- do not create downstream artifacts

Headless or non-interactive mode is not scope approval. If explicit approval is
not available, stop with `## > Next Up`; never auto-select approval.
</approval_gate>

<validation_and_persistence>
After approval, validate the exact JSON:

```bash
printf '%s\n' "$PROJECT_CONTRACT_JSON" | gpd --raw validate project-contract - --mode approved
```

If validation fails, show the errors, repair the contract, and do not continue.
If repair would require inventing anchors, references, baselines, DOI/arXiv/file locators, or prior outputs, stop and ask the user. If a validation or persistence shell call is denied by runtime policy, stop and report the policy block; do not substitute unvalidated file writes.

Persist the same approved JSON:

```bash
printf '%s\n' "$PROJECT_CONTRACT_JSON" | gpd state set-project-contract -
```

This stage may write only the state files declared by `staged_loading`.
</validation_and_persistence>

<handoff>
After persistence succeeds, reload the flag-selected post-approval stage before
any downstream artifact creation or late setup:

- `gpd --raw init new-project --stage minimal_artifacts` for `--minimal`
- `gpd --raw init new-project --stage workflow_preferences` for full or `--auto`
</handoff>
