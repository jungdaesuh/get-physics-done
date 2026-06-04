<purpose>
Create a candidate `ResearchPersonaPatch` from consented interview answers and
approved evidence handles.
</purpose>

<process>
1. Delegate candidate synthesis to `gpd-persona-builder` with a scoped write
   path for the patch artifact.
2. Require every proposed fact to include `source_kind`, `sources`,
   `evidence_refs`, `confidence`, and a privacy label.
3. Use conservative privacy defaults: `private_local` unless the user chooses
   `project_private`, `session_only`, `safe_to_share`, or `never_prompt`.
4. Keep `never_prompt` material out of prompt-facing summaries and capsules.
5. Validate the candidate by running a read-only diff:

```text
gpd research-persona diff GPD/persona/candidate-patch.json
```

6. If validation fails, revise the candidate patch or stop with the schema
   error. Do not apply the patch.
</process>

<downstream_hooks>
The patch may include approved facts for future `doppelganger`, `explainer`,
and `taste` capsules, but this stage does not run those behaviors.
</downstream_hooks>
