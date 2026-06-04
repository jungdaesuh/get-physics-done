<purpose>
Present the candidate persona patch for review and route durable mutation only
through the local research-persona CLI.
</purpose>

<process>
1. Show a concise summary of facts, axes, list updates, privacy labels, and
   inferred or low-confidence entries.
2. Show the approval commands:

```text
gpd research-persona validate GPD/persona/candidate-patch.json
gpd research-persona diff GPD/persona/candidate-patch.json
gpd research-persona apply-patch GPD/persona/candidate-patch.json
```

3. Explicit user approval is required before mutation. Do not apply-patch until
   approval is given after the candidate patch and diff are reviewed.
4. If the user declines, stop without mutation and keep the candidate patch as
   a review artifact only.
5. If the user approves and asks you to apply it, run only the CLI
   `apply-patch` command and then validate the stored persona through the CLI.
</process>

<forget_route>
For later removal, direct the user to:

```text
gpd research-persona forget <fact-id>
```
</forget_route>
