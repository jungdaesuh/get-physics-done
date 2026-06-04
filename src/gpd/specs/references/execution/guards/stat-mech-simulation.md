# Statistical Mechanics Simulation Execution Guard

Use for selected `stat-mech-simulation` bundles.

- Before production, record the ensemble, update rule, observable definitions,
  normalization conventions, random seeds, and exact or literature benchmark.
- Run ordered and disordered starts when thermalization could bias the claim.
- Estimate autocorrelation time or effective sample size for each decisive
  observable; do not treat raw sample count as independent evidence.
- Check detailed balance, partition-function positivity where applicable, and a
  known high-temperature, low-temperature, or small-system limit.
- For critical claims, produce finite-size scaling or collapse artifacts with
  uncertainty bars and normalization notes.
- Preserve raw measurements and metadata needed to reproduce burn-in,
  autocorrelation, and benchmark comparisons.
