<purpose>
Confirm the research persona-building scope and consent boundary before any
interview or local evidence scan.
</purpose>

<hard_boundaries>
- No silent memory: do not silently create, infer, or update persona memory.
- Do not read raw private persona profile content into prompts or child handoffs.
- Do not inspect project files, papers, collaborators, references, or tool
  metadata until the user explicitly approves the source category.
- Do not mutate persona storage in this stage.
</hard_boundaries>

<process>
1. State that this workflow produces a candidate `ResearchPersonaPatch` only.
2. Ask whether the user wants interview-only intake, current-project evidence,
   named paper/reference evidence, or to stop.
3. If local evidence is requested, list the exact path categories before
   reading them and wait for approval.
4. Select a candidate patch destination such as
   `GPD/persona/candidate-patch.json` or a `/tmp` path.
5. Carry forward only scope, consent, and evidence handles to synthesis.
</process>

<approval_boundary>
Explicit user approval is required before mutation. Do not apply-patch in this
stage; the approval stage owns the review route through:

```text
gpd research-persona validate
gpd research-persona diff
gpd research-persona apply-patch
```
</approval_boundary>
