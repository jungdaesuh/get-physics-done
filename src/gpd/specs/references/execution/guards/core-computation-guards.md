# Core Computation Guards

Load this only when no selected bundle execution guide covers the active method.
Run the rows that match the current step; multiple rows may apply.

| Method family | Guard |
|---|---|
| Angular momentum / CG coefficients | Check triangle inequalities, m-value sums, phase convention, and one coefficient against a table or independent algebra. |
| Grassmann / fermionic algebra | Count anticommutation signs, closed fermion loops, exchange parity, and Pauli exclusions explicitly. |
| Diagrammatic calculations | Count vertices, propagators, external legs, symmetry factors, and momentum conservation at every vertex. |
| Variational / extremization | Check boundary terms, stationarity, known variational bounds, and Hellmann-Feynman consistency when forces appear. |
| Operator algebra / commutators | Verify Hermiticity, Jacobi identity, ordering convention, and representation-domain assumptions. |
| Perturbative or asymptotic expansions | State the expansion parameter and order, enumerate terms/topologies, test one known limit, and estimate truncation error. |
| Path or functional integrals | Check measure/Jacobian, saddle equations, zero modes, determinant signs, and regulator dependence. |
| Fourier or spectral decompositions | Check the project Fourier convention, Parseval/normalization, reality conditions, and aliasing or basis truncation. |
| Numerical computation | Run at multiple resolutions/tolerances, compare with a known limit or benchmark, check condition number/stability, and record units. |
| Numerical ODE/PDE/FEM/spectral | Verify boundary-condition count, conservation laws, convergence order, mesh/basis quality, and a known solution or manufactured test. |
| Monte Carlo / sampling | Check burn-in, autocorrelation/effective sample size, detailed balance or proposal diagnostics, and independent seed agreement. |
| Exact diagonalization / Krylov | Check Hermiticity, Hilbert-space dimension, residual norms, degeneracy structure, and loss of orthogonality. |
| Tensor network / DMRG | Track discarded weight, bond-dimension convergence, symmetry-sector consistency, and monotonic energy behavior when applicable. |
| DFT / electronic structure | Check SCF convergence, k-point/basis convergence, functional/pseudopotential identity, variational behavior, and a known material benchmark. |
| Molecular or symplectic dynamics | Check force consistency, timestep convergence, conservation drift, reversibility or symplecticity, and thermostat interpretation. |
| Scattering / cross-section | Check positivity, optical theorem or unitarity, crossing/channel conventions, flux normalization, and threshold limits. |
| Quantum circuits / channels | Check gate unitarity or channel complete positivity, trace preservation, measurement normalization, and symmetry constraints. |
| Inverse problems / parameter estimation | Check identifiability, conditioning, prior propriety, posterior/likelihood normalization, and uncertainty calibration. |
| Lattice Boltzmann method | Check relaxation parameter, Mach-number regime, mass/momentum conservation, Chapman-Enskog limit, and boundary treatment. |

On failure, stop the step, rerun the executor self-critique checkpoint, and
apply the deviation protocol if the failure survives one bounded correction.
