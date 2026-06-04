# AMO / Quantum Optics Planning Guide

Use for atom-light systems, quantum optics, cold atoms, trapped ions, spectra,
master equations, and decoherence.

Dependency skeleton:

```
System Hamiltonian -> frame transformation -> approximation bounds
-> dynamics equation -> observables -> decoherence or noise model
-> experimental or known-limit comparison
```

Decision points:

- Rotating frame and drive convention.
- RWA, dipole, Lamb-Dicke, or Markov approximation validity.
- Master equation, Schrodinger evolution, Heisenberg-Langevin, or trajectory
  method.

Planning requirements:

- Quantify RWA and dipole bounds rather than saying "check validity".
- Lock Rabi-frequency, detuning, Clebsch-Gordan, and field-normalization
  conventions before spectra or transition rates.
- Add positivity, detailed-balance, selection-rule, or sum-rule checks where
  the claim depends on open-system dynamics or transitions.

Common pitfalls:

- Applying RWA far from resonance or near ultrastrong coupling.
- Neglecting recoil for cold atoms.
- Wrong Clebsch-Gordan phase convention.
- Confusing peak, rms, angular-frequency, and cycle-frequency definitions.

Decisive artifacts:

- Hamiltonian in the chosen frame with approximation inequalities.
- Observable prediction with convention notes.
- Experimental, exact, or sum-rule comparison.
