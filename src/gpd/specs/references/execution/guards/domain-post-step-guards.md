# Domain Post-Step Guards

Load this when the selected bundle does not already provide domain-specific
execution checks. Apply matching rows after major intermediate results.

| Domain | Guard |
|---|---|
| QFT / gauge theory | Check Ward or Slavnov-Taylor identity, gauge-parameter cancellation for observables, unitarity/optical-theorem consistency, and renormalization convention. |
| Condensed matter | Check Kramers-Kronig consistency, spectral positivity, sum rules, extensive scaling, and symmetry breaking assumptions. |
| Statistical mechanics | Check detailed balance or ensemble validity, partition-function positivity, thermodynamic stability, finite-size effects, and high/low-temperature limits. |
| Numerical / simulation | Check conditioning, cancellation risk, conserved quantities, resolution dependence, and reproducibility metadata. |
| General relativity / cosmology | Check Bianchi or constraint identities, metric signature and gauge convention, conservation laws, Newtonian or perturbative limits, and coordinate artifacts. |
| Nuclear / particle | Check cross-section positivity, partial-wave unitarity, CPT/isospin/flavor selection rules, and benchmark normalization. |
| Quantum information | Check trace preservation, complete positivity, entropy/fidelity bounds, and no-cloning or no-signaling constraints where relevant. |
| Astrophysics | Check Eddington, virial, Jeans, compactness, or balance-law constraints that match the system. |
| Soft matter / biophysics | Check fluctuation-dissipation, positivity/stability, scaling laws, and small-deformation or dilute-limit assumptions. |
| Mathematical physics | Check integer-valued invariants, anomaly matching, modular/index relations, and hypotheses needed for the theorem used. |

Do not apply an unrelated row just because it shares vocabulary with the
project. If no row fits, continue with the generic method guards and contract
anchors.
