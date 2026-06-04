# Convention Coordinator Playbook

Load this only when the notation coordinator needs detailed convention
selection examples, cross-convention tables, conversion rules, or rollback
procedure details. The agent prompt keeps ownership and source-of-truth rules
inline; this file carries worked material.

## Mid-Execution Convention Requests

When an executor discovers a missing convention, require a concise request:

```markdown
### CONVENTION NEEDED

**Task:** [current task]
**Category:** [metric, Fourier, spinor, gauge, discretization, ...]
**Context:** [calculation step requiring the choice]
**Constraints:** [locked conventions that constrain the choice]
**Candidates:**
- Option A: [convention] -- used by [reference], advantage: [why]
- Option B: [convention] -- used by [reference], advantage: [why]
**Recommendation:** [choice and compatibility rationale]
```

Resolve non-interactive requests by choosing the compatible subfield/default
choice, then lock it with `gpd convention set` and refresh `CONVENTIONS.md`.
For interactive plans, return a `checkpoint` and wait for the fresh
continuation before any lock or file write.

Example: a finite-temperature condensed-matter calculation may need a Green's
function time-ordering convention. With `k_B = 1` and lattice Fourier
normalization already locked, Matsubara `G(k,tau)` is usually compatible with a
finite-temperature primary reference; retarded `G^R(k,omega)` is better for
transport or spectral functions. The request should state which calculation
needs the convention and what prior lock constrains it.

## Auto-Suggestion Examples

For project bootstrap, load `subfield-convention-defaults.md`, identify the
primary subfield, then flag cross-subfield conflicts before returning a
supervised checkpoint or applying an approved auto mode.

Example: QFT in curved spacetime for Hawking radiation.

| Category | Suggested choice | Reason |
| --- | --- | --- |
| Units | Natural, with `hbar = c = G = 1` if GR dominates | Merges QFT and GR scales |
| Metric signature | `(-,+,+,+)` | GR convention in Wald/MTW-style calculations |
| Fourier convention | Physics `exp(-i omega t)` | Standard QFT transform convention |
| Riemann sign | MTW/Wald-compatible | Needed before importing curvature formulas |
| Field normalization | Canonical commutator | QFT mode expansion anchor |

If the primary flat-space QFT reference uses `(+,-,-,-)`, state the conflict
explicitly and document how propagators and mass-shell conditions convert.

## Cross-Convention Interaction Tables

Classic high-risk pairs:

| Convention A | Convention B | Required relation |
| --- | --- | --- |
| Metric `(+,-,-,-)` | Propagator | `i/(k^2 - m^2 + i epsilon)` with `k^2 = k0^2 - |k|^2` |
| Metric `(-,+,+,+)` | Propagator | `-i/(k^2 + m^2 - i epsilon)` with `k^2 = -k0^2 + |k|^2` |
| Fourier `exp(-ikx)` | Mode expansion | annihilation part carries `exp(+ikx)` under the paired inverse |
| `D = d + i g A` | Field strength | commutator sign must match the chosen derivative |
| Natural units | Action | action dimensionless; Lagrangian density has mass dimension `d` |
| Relativistic states | Completeness | include `d^3k/(2pi)^3 1/(2E_k)` |

Extended interactions to check when the corresponding locks exist:

| Convention A | Convention B | Required relation |
| --- | --- | --- |
| Levi-Civita sign | Gamma-5 | sign in `gamma5 = +/- i gamma0 gamma1 gamma2 gamma3` |
| Generator normalization | Coupling definition | fixes factors in structure constants and Casimirs |
| Gamma basis | Spinor normalization | `ubar u = 2m` versus normalized Weyl conventions |
| Creation order | Normal ordering | number-operator convention determines Wick reordering |
| Metric signature | Levi-Civita tensor | lowering all indices changes sign by convention |
| State normalization | Creation operators | `sqrt(n+1)` factors depend on normalized states |

## Numerical Factor Registry

Record factors whose values depend on conventions:

| Factor source | Typical error | Determining convention pair |
| --- | --- | --- |
| `2 pi` | missing or duplicated Fourier measure | Fourier convention plus integral normalization |
| `4 pi` | `alpha` versus `g^2` confusion | coupling definition plus action normalization |
| `sqrt(2)` | field amplitude mismatch | field and creation-operator normalization |
| `i` sign | propagator numerator sign | metric plus Fourier convention |
| factor `2` | spin-sum mismatch | spinor normalization |
| sign powers | Riemann or dual tensor sign | Riemann, metric, and Levi-Civita conventions |

## Convention Changes And Rollback

Valid changes include numerical-unit needs, a critical source/tool convention,
or repair of an internally inconsistent lock. Invalid changes include cosmetic
preference, unrelated textbook drift, or implicit unreviewed usage.

Every change must document:

- decision record in `GPD/DECISIONS.md`;
- old value, new value, effective phase, and test values;
- conversion table for affected quantities;
- update to `state.json.convention_lock` through `gpd convention set`;
- refreshed `GPD/CONVENTIONS.md`;
- downstream phases that must convert imported results.

Rollback protocol:

1. Identify scope by searching for the old convention assertion or formula
   pattern.
2. Prepare a revert plan listing files and dependency order.
3. Apply the rollback atomically as one scoped change set.
4. Mark the reverted convention append-only in `CONVENTIONS.md`; do not delete
   history.
5. Re-run the consistency checker.
6. Return fresh rollback files to the orchestrator for commit.

If rollback fails partway, use the previous orchestrator commit as the recovery
target and complete remaining file updates manually.

## Conversion Table Templates

Metric signature conversion:

| Quantity | `(+,-,-,-)` | `(-,+,+,+)` | Rule |
| --- | --- | --- | --- |
| metric | `diag(+1,-1,-1,-1)` | `diag(-1,+1,+1,+1)` | `eta -> -eta` |
| `p^2` | `E^2 - |p|^2` | `-E^2 + |p|^2` | flip sign |
| on-shell | `p^2 = m^2` | `p^2 = -m^2` | flip mass-shell sign |
| propagator | `i/(p^2-m^2+i eps)` | `-i/(p^2+m^2-i eps)` | numerator and pole signs |

Fourier conversion:

| Convention | Forward | Inverse | Measure |
| --- | --- | --- | --- |
| Physicist | `integral dx f(x) exp(-ikx)` | `integral dk/(2pi) f(k) exp(+ikx)` | `dk/(2pi)` |
| Symmetric | `integral dx/sqrt(2pi) ...` | `integral dk/sqrt(2pi) ...` | split factors |
| Opposite sign | `integral dt f(t) exp(+i omega t)` | paired inverse with `exp(-i omega t)` | sign flip |

Unit conversion:

| Quantity | Natural units | SI conversion cue |
| --- | --- | --- |
| Length | inverse energy | restore `hbar c` |
| Time | inverse energy | restore `hbar` |
| Mass | energy | convert through `E = m c^2` |
| Cross section | inverse energy squared | restore `(hbar c)^2` |
| Temperature | energy | restore `k_B` relation |
