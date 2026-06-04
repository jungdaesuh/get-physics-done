---
load_when:
  - "plan checker profile"
  - "autonomy-aware plan review"
  - "review depth calibration"
tier: 2
context_cost: medium
---

# Plan Checker Depth Profiles

Use this reference after reading `gpd-plan-checker.md` when profile, autonomy, or review-depth settings affect how much detail to apply. These settings change breadth and depth only; they never waive the D0 contract gate or the proof/numerical/publication floors.

## Profile-Aware Checking Rigor

The active model profile (from `GPD/config.json`) controls not just which model tier is used, but how many dimensions are checked and at what depth.

**Invariant across all profiles:** Profile changes depth and breadth, never minimum contract completeness. Every profile must still run the contract gate, require decisive outputs, require anchor coverage, require acceptance tests, reject forbidden proxies as sole success conditions, and require a disconfirming path for risky work.

**deep-theory:** D0-D16 checked at maximum rigor. Require explicit justification for every approximation. Flag any task without validation step.

**numerical:** Emphasize D5 (computational feasibility), D6 (validation strategy), D9 (dependency correctness), D11 (contract/artifact derivation), and D16 (environment validation). Require convergence, benchmark or limiting-case anchors, uncertainty treatment, reproducibility, and stop/rethink conditions for every numerical task.

**exploratory:** Reduce optional depth, not contract rigor. Always run Dimension 0 plus the core dimensions: Dim 1 (Research Question Coverage), Dim 2 (Task Completeness), Dim 4 (Approximation Validity), Dim 5 (Computational Feasibility), Dim 8 (Result Wiring and Coherence), Dim 9 (Dependency Correctness), Dim 10 (Scope Sanity), Dim 11 (Contract Completeness And Artifact Derivation), Dim 16 (Computational Environment Validation). Optional dimensions may be abbreviated, but decisive outputs, anchors, acceptance tests, forbidden proxies, and disconfirming paths remain mandatory.

**review:** D0-D16. Additionally check: does the plan reference specific literature results for comparison? Are all claims testable?

**paper-writing:** D0-D16 with emphasis on Dim 12 (Literature Awareness), Dim 13 (Path to Publication), Dim 8 (Result Wiring), and Dim 11 (Contract Completeness And Artifact Derivation). Verify plans map to paper sections, figures, and tables. Check notation consistency tasks exist. Require cross-reference verification.

## Autonomy-Aware Plan Checking

Read autonomy mode from config. Higher autonomy = plan checker is more critical (no human reviewing plans before execution).

| Autonomy | Plan Checker Behavior |
|---|---|
| **supervised** | **Lighter breadth, same minimum gate.** Focus on blockers first, but ALWAYS run the contract gate, anchor coverage, acceptance-test coverage, and disconfirming-path checks. Human review does not replace those requirements. |
| **balanced** (default) | **Standard+ check.** Run the full dimension check per profile. Flag any plan with `interactive: false` that lacks explicit verification criteria, and verify that every approximation has a validity check somewhere in the phase. Warn if any task exceeds a 60-minute estimate without an intermediate checkpoint. |
| **yolo** | **Maximum scrutiny.** Everything in balanced mode PLUS: verify all contract-critical outputs are independently testable (not circular), check that scope extensions stay inside the approved contract, require at least one limiting-case check per plan, and flag plans that combine derivation + numerical validation when that would erase independent failure detection. |

**Key interaction:** In `balanced + exploratory`, the profile can reduce optional detail, but autonomy still requires explicit validation on non-interactive plans and does NOT relax contract completeness. In `yolo`, autonomy increases scrutiny because there is less human intervention; it does not grant permission to ignore approved anchors, decisive outputs, forbidden proxies, or disconfirming paths.
