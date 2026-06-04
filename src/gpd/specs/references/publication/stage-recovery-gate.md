# Publication Stage Recovery Gate

Shared recovery gate for spawned publication children and staged handoffs. Callsites still own expected artifacts, validators, write allowlists, retry prompts, and stop/reroute rules.

- Treat every spawned publication child as one-shot. Any `status: completed`, `checkpoint`, `blocked`, or `failed` return is terminal for that child run.
- A `completed` return is provisional until the orchestrator captures the typed return, checks callsite-owned artifacts on disk, and confirms fresh `gpd_return.files_written` names the artifacts written in this run.
- Do not use prose success text, live child memory, pending tool state, unstaged scratch notes, or stale preexisting files as proof of current-run completion.
- Do not accept stale preexisting files as proof of current-run completion. Existing files count only for explicit read-only/current inspection owned by the callsite.
- For `checkpoint`, stop that child and resume only by spawning a fresh continuation from persisted artifacts plus declared carry-forward inputs.
- For `blocked` or `failed`, classify the callsite artifact boundary before any fresh retry. If a retry is allowed, it is a fresh child run from persisted inputs, not a resumed live child.
- For parallel waves, wait for every outcome, validate or classify every promised artifact, retire children, then continue only from persisted artifacts and declared carry-forward inputs.
- Any `gpd_return.files_written` path outside the callsite write allowlist is a failed handoff, not authorization to repair upstream artifacts.
