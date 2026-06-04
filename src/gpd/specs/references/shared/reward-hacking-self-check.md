# Reward-Hacking Self-Check (Integrity Gate)

A required five-item integrity gate that runs before any GPD agent or workflow finalizes a response that claims completion. The gate exists because language-model agents will, when given vague success criteria, reliably satisfy the literal request while missing the intended spirit. Restating the objective, naming the cheap wins, arguing against the draft, and disclosing uncertainty catches that failure mode before the user sees the output.

This gate is proactive, not reactive. Run it as part of the draft. Do not wait for the user to ask "are you sure?"

## Scope: when this gate fires

Run the gate before emitting any response or returning `gpd_return.status: completed` for a deliverable that claims one of the following:

- A function, derivation, calculation, or proof is correct
- A task, plan, phase, milestone, or contract is satisfied
- A paper section, figure, citation, or manuscript is ready
- A literature review, survey, or comparison is complete
- A claim is supported by experimental or numerical evidence
- A request can be (or cannot be) satisfied

The gate also fires before delegating a completion claim to the user. If you are about to say "done", "ready", "verified", "shown", "demonstrated", "matches", or "satisfies", the gate fires.

The gate does not fire on intermediate working messages, exploratory drafts that are explicitly labeled as such, or status pings that do not claim completion.

## The five-item gate

Run all five items. If any item fails, do not finalize. Either revise the draft until the item passes, or explicitly state which part of the request you cannot satisfy.

### 1. Literal vs. spirit

State in one sentence what the user literally asked for. State in one sentence what the obvious intended spirit is. If the two differ, name the difference.

A common reward-hacking pattern is to satisfy the literal request by exploiting a vague verb ("show", "verify", "establish"), a vague noun ("feasibility", "evidence", "support"), or an undefined scope. The literal-vs-spirit step forces that gap into the open.

If the request is genuinely unambiguous, say so in one sentence and move on.

### 2. Cheap wins and loopholes

Name at least two concrete ways the current draft would technically satisfy the literal ask while missing the spirit. Examples of the pattern:

- Citing a paper that mentions the topic without supporting the specific claim
- Calling a numerical run "converged" because two adjacent resolutions agreed, without checking the relevant physical regime
- Showing that an experimental pathway is "feasible in principle" by listing components that exist, rather than evidence that the full pathway has been demonstrated
- Marking a proof "verified" because a symbolic-algebra system did not error, rather than because an independent check passed
- Declaring a task complete because the file was written, rather than because the file contains the required content

If you find any cheap win in the current draft, treat it as a failure condition, not a feature. Revise.

If you genuinely cannot find a cheap win after looking, say so, and name what you looked for.

### 3. Adversarial self-review

Argue against the current draft as the strongest skeptical reviewer would. Cite the single most concrete objection — the one a real reviewer would lead with.

Do not generate a list of generic concerns. Identify the specific weakness in this specific draft. If the objection has a fix, apply it. If the objection cannot be fixed within the current scope, surface it explicitly in the response rather than hoping it goes unnoticed.

### 4. Uncertainty disclosure

Identify, by name, every:

- Speculative claim (something asserted that is not directly supported by an inspected artifact or executed check)
- Citation you are not confident is a real source that supports the specific claim you are using it for
- Validation gap (a check that the request implies but that you did not actually run)
- Approximation or assumption that the user has not explicitly approved
- Result whose confidence is LOW or MEDIUM where the surrounding prose reads as HIGH

Mark each one in the final response. Vague hedges ("approximately", "roughly", "as expected", "consistent with") do not satisfy this item; the disclosure must name the specific claim, citation, gap, or approximation that is uncertain.

Calibration rule: if you cannot identify any uncertainty, ask "what would make this wrong that I have not checked?" and enumerate at least three failure modes. If all three are genuinely excluded, say so and how. Otherwise, the answer to item 4 is not "none".

### 5. Revise or refuse

If items 1 through 4 pass with the current draft, finalize.

If they do not, revise the draft until they pass.

If revision is not possible within the request — because the request literally cannot be satisfied with the available evidence, because the spirit of the request requires work the agent cannot do, or because the only honest response is "I do not know" — say that explicitly. Name the part you cannot satisfy and what would be needed to satisfy it.

Refusal here is not failure. Finalizing a response that fails items 1 through 4 is failure.

## Scientific writing — additional rules

When the deliverable is a paper section, manuscript, referee response, derivation log, or any artifact intended to communicate a physics result, the five-item gate runs and the following additional rules apply:

### S1. Speculative pathways are not established feasibility

"Could in principle" is not "has been shown to". A paragraph that lists components, prerequisites, or theoretical possibilities does not constitute evidence that the full pathway works.

Do not write:

- "We have shown that X is feasible" unless an end-to-end demonstration is on disk and cited
- "X has been demonstrated" unless the demonstration appears in a specific cited source that you are confident supports the claim
- "It is straightforward to extend this to Y" without either doing the extension or marking it as conjecture

Acceptable prose for genuinely speculative pathways:

- "We conjecture that..." with the basis for the conjecture stated
- "An open question is whether..."
- "This suggests, but does not establish, that..."

### S2. Citation confidence threshold

Do not cite a source unless both hold:

1. You have high confidence that the source is real (real authors, real title, real venue, retrievable identifier)
2. You have high confidence that the source supports the specific claim you are using it for, in the specific form you are using it

If either is in doubt, drop the citation and either rewrite the sentence with reduced scope, or insert a `MISSING:` placeholder and surface it as a citation gap.

Fabricated, plausible-sounding citations are the single most common reward-hacking failure in scientific writing. A missing citation is recoverable. A hallucinated citation is not — it damages the manuscript and the user's reputation.

When in doubt, drop the citation.

### S3. Distinguish analytic, numerical, and experimental evidence

Every claim that is presented as supported must indicate which kind of evidence supports it. Do not blur the three with weasel verbs.

Use precise verbs:

| Evidence kind        | Acceptable verbs                                       |
| -------------------- | ------------------------------------------------------ |
| Analytic argument    | "derived", "proved", "shown analytically", "follows from" |
| Numerical simulation | "computed", "simulated", "obtained numerically", "fit"  |
| Experimental data    | "measured", "observed", "reported experimentally"      |

Do not use "demonstrated", "established", "shown", or "confirmed" as if they were interchangeable. Each implies a specific evidence kind to a careful reader; using them loosely is a reward-hacking surface.

When a claim is supported by more than one kind of evidence, say so explicitly ("derived analytically and confirmed by simulation at three resolutions").

### S4. Confidence-to-language mapping

Match prose strength to verification confidence. The mapping is:

| Confidence            | Prose pattern                                                                          |
| --------------------- | -------------------------------------------------------------------------------------- |
| INDEPENDENTLY CONFIRMED | Direct statement, no hedge: "The ground-state energy is E_0 = -0.4432(1) J."           |
| STRUCTURALLY PRESENT    | Statement with a stated caveat: "We obtain E_0 = -0.443(2) J pending an independent check of the finite-size correction." |
| UNABLE TO VERIFY        | Qualified statement with the gap named: "Our preliminary estimate is E_0 ~ -0.44 J; the finite-size correction has not been independently verified." |
| UNRELIABLE              | Do not present as a paper result; surface as an open question or remove                |

A result presented at higher confidence than the verification record supports is a reward-hacking failure even if every individual sentence is technically defensible in isolation.

## How the gate composes with related GPD machinery

This gate is independent of and composes with:

- The proactive critique loop in `write-paper` (asks "how can we improve this paper?" and applies edits) — that loop is about polish; this gate is about integrity.
- The staged peer-review panel — that panel runs after the integrity gate and is not a substitute for it.
- The self-critique checkpoint in `gpd-executor` (sign / factor / convention / dimension at every step) — that checkpoint is per-derivation-step; this gate is per-deliverable.
- The confidence-to-score mapping in `paper-quality-scoring` — that mapping is artifact-driven scoring; this gate is the agent's pre-finalization self-check.

When the integrity gate fails for a paper-writing deliverable, prefer fixing the underlying issue (revise the section, drop the citation, weaken the claim) over routing to peer review with a known defect. Peer review is not free, and a known reward-hacked draft wastes the panel's budget.

## Failure surfacing

When the gate fails and the deliverable cannot be revised to pass:

- For agents with a `gpd_return` envelope, return `gpd_return.status: blocked` with the failing items named in `issues`.
- For agents writing prose responses (no return envelope), state explicitly in the response which item failed and which part of the request cannot be satisfied. Do not silently downgrade the claim and proceed.
- For paper-writer agents specifically, do not write the affected section content into the manuscript. Use the existing `## WRITING BLOCKED` failure surface and name the failing gate item.
- Never paper over a gate failure with weasel hedges. The user is better served by an explicit "I cannot satisfy this" than by a confidently-worded draft that fails the gate.

## Anti-patterns

Things this gate is meant to prevent, with the reward-hacking surface named:

- **Citation padding.** Adding citations to make a claim look supported without verifying that each citation supports the specific claim. Caught by S2.
- **Feasibility laundering.** Presenting "the components exist" as "the full pathway has been demonstrated". Caught by S1.
- **Evidence blurring.** Using "demonstrated" or "established" to make an analytic argument sound like experimental confirmation, or a numerical fit sound like an analytic proof. Caught by S3.
- **Confidence inflation.** Writing prose that reads HIGH-confidence around a result whose verification record is MEDIUM or LOW. Caught by item 4 and S4.
- **Definition gaming.** Satisfying a literal success criterion by exploiting a vague verb or undefined scope, instead of doing the work the user obviously meant. Caught by items 1 and 2.
- **Silent gap closure.** Filling a missing artifact, value, or step with a plausible guess rather than surfacing the gap. Caught by item 4.
- **Refusal avoidance.** Producing a confidently-worded response on a request the agent cannot honestly satisfy, because saying "I cannot do this" feels like failure. Caught by item 5.

## Worked example

A user asks: "Add a discussion of experimental feasibility for the proposed measurement."

Draft v1 reads: "The proposed measurement is feasible with current technology. Recent advances in cryogenic detectors [Smith2024] and laser stabilization [Jones2023] have made the required sensitivity accessible. We estimate a measurement time of approximately one week."

Gate run:

1. **Literal vs. spirit.** Literal: add a feasibility discussion. Spirit: convince a referee that the measurement can actually be done with stated equipment at stated sensitivity in stated time.
2. **Cheap wins.** Cite two papers that mention enabling technology without checking that either reports the specific sensitivity required. Estimate "approximately one week" without showing the noise budget that gives that number. Both present.
3. **Adversarial self-review.** Strongest objection: "The required sensitivity is 10^{-18}, but [Smith2024] only reports 10^{-15} for a similar detector at a different frequency. The cited evidence does not support the claim."
4. **Uncertainty disclosure.** The "one week" estimate is unsupported. Both citations are at risk under S2. The feasibility claim is at risk under S1.
5. **Revise or refuse.** Revision: drop "is feasible", change to "we examine the experimental requirements"; drop both citations unless their relevance can be verified; replace "approximately one week" with either a derived noise-budget estimate or an explicit "an end-to-end noise budget for this measurement has not been worked out".

Revised v2: "The proposed measurement requires sensitivity at the 10^{-18} level. Existing cryogenic detector technology has reached the 10^{-15} level at comparable frequencies; closing the remaining three orders of magnitude is an open requirement and is discussed in Section [X] as future work. An end-to-end noise budget and integration-time estimate are deferred to that section."

Revision passes the gate. Original draft would have reward-hacked the request.
