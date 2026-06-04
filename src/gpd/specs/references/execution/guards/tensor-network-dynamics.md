# Tensor Network Dynamics Execution Guard

Use for selected `tensor-network-dynamics` bundles.

- State ansatz, boundary conditions, conserved quantum numbers, truncation
  scheme, bond dimension, timestep or optimization tolerance, and target
  observable before running.
- Track discarded weight, entanglement growth, norm/energy drift, and symmetry
  sector preservation at each decisive step.
- Demonstrate convergence with bond dimension and timestep or sweep count; do
  not report a single-bond-dimension result as decisive.
- Check short-time expansion, exact diagonalization on a small system, or a
  known integrable/free limit when available.
- For dynamics, separate physical relaxation from truncation-induced damping and
  report the time window where errors remain controlled.
