# Continuation Boundary

Canonical one-shot and fresh-continuation contract. Stage prompts should name local checkpoint triggers/payloads, then reference this boundary instead of repeating the protocol.

- A spawned `task()` run is one-shot. If it cannot finish without user input, human verification, or a decision, it returns a typed `gpd_return.status: checkpoint` envelope and stops.
- The child must not wait for the user, keep the run alive, or expect resume-in-place.
- The orchestrator owns the pause: present the checkpoint, collect the response, record durable continuation state when needed, and start a fresh continuation handoff with explicit state plus the user response.
- Checkpoint returns keep domain content in the body or extended fields. Name files in `files_written` only after they exist; use `files_written: []` when the checkpoint intentionally defers writes.
- `checkpoint_intent` is child-owned reason, waiting condition, cursor, and gate hints. It is not durable authority until the parent/applicator supplies parent-owned resume context, result/session identifiers, timestamps, and resolved bounded-segment state.
- If expected artifacts are named, verify them through `references/orchestration/child-artifact-gate.md` before accepting success or continuing.
- Fresh continuation rules: verify resume preconditions, check named artifacts, perform only approved follow-up work, and return a fresh typed `gpd_return` envelope.

Agent prompts should not duplicate these generic lifecycle rules.
