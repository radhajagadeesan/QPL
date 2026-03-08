============================================================
  LIVE EXECUTION: ExpInvolution Conjugation Demo
  All compilations are real - no fabricated output
============================================================

Type: Q ⊗ Q (width = 2 qubits)

SWAP = TwistTen(Q, Q) — wire permutation [1, 0]
exp_i(θ, SWAP) = exp(iθ · SWAP) — uses ExpSwap decomposition


============================================================
Demo 1: Build SWAP = TwistTen(Q, Q)
============================================================
  [COMPILING TwistTen(Q, Q)...] OK - 1 gates on 2 qubits

Compiled Circuit
================
Circuit: 1 gates on 2 qubits
Permutation: [0, 1]
Gates:
  SWAP on [0, 1]

SWAP (compiled):
  |00⟩ [+1.0000+0.0000i, +0.0000+0.0000i, +0.0000+0.0000i, +0.0000+0.0000i]
  |01⟩ [+0.0000+0.0000i, +0.0000+0.0000i, +1.0000+0.0000i, +0.0000+0.0000i]
  |10⟩ [+0.0000+0.0000i, +1.0000+0.0000i, +0.0000+0.0000i, +0.0000+0.0000i]
  |11⟩ [+0.0000+0.0000i, +0.0000+0.0000i, +0.0000+0.0000i, +1.0000+0.0000i]

✓ VERIFY: SWAP² = I? True

============================================================
Demo 2: Build exp_i(π/4, SWAP)
============================================================
  [COMPILING ExpInvolution(π/4, SWAP)...] OK - 1 gates on 2 qubits

Compiled Circuit
================
Circuit: 1 gates on 2 qubits
Permutation: [0, 1]
Gates:
  Unitary2qBox on [0, 1]

exp_i(π/4, SWAP) (compiled):
  |00⟩ [+0.7071+0.7071i, +0.0000+0.0000i, +0.0000+0.0000i, +0.0000+0.0000i]
  |01⟩ [+0.0000+0.0000i, +0.7071+0.0000i, +0.0000+0.7071i, +0.0000+0.0000i]
  |10⟩ [+0.0000+0.0000i, +0.0000+0.7071i, +0.7071+0.0000i, +0.0000+0.0000i]
  |11⟩ [+0.0000+0.0000i, +0.0000+0.0000i, +0.0000+0.0000i, +0.7071+0.7071i]

✓ VERIFY: matches cos(θ)I + i·sin(θ)·SWAP? True (phase=1.0000+0.0000j)

============================================================
Demo 3: Build exp_i(-π/4, SWAP)
============================================================
  [COMPILING ExpInvolution(-π/4, SWAP)...] OK - 1 gates on 2 qubits

Compiled Circuit
================
Circuit: 1 gates on 2 qubits
Permutation: [0, 1]
Gates:
  Unitary2qBox on [0, 1]

exp_i(-π/4, SWAP) (compiled):
  |00⟩ [+0.7071-0.7071i, +0.0000+0.0000i, +0.0000+0.0000i, +0.0000+0.0000i]
  |01⟩ [+0.0000+0.0000i, +0.7071+0.0000i, +0.0000-0.7071i, +0.0000+0.0000i]
  |10⟩ [+0.0000+0.0000i, +0.0000-0.7071i, +0.7071+0.0000i, +0.0000+0.0000i]
  |11⟩ [+0.0000+0.0000i, +0.0000+0.0000i, +0.0000+0.0000i, +0.7071-0.7071i]

✓ VERIFY: exp(iθ·SWAP) · exp(-iθ·SWAP) = I (up to phase)? True

============================================================
Demo 4: Build Z gate
============================================================
  [COMPILING Z(0, Q⊗Q)...] OK - 1 gates on 2 qubits

Compiled Circuit
================
Circuit: 1 gates on 2 qubits
Permutation: [0, 1]
Gates:
  Z on [0]

Z (compiled):
  |00⟩ [+1.0000+0.0000i, +0.0000+0.0000i, +0.0000+0.0000i, +0.0000+0.0000i]
  |01⟩ [+0.0000+0.0000i, +1.0000+0.0000i, +0.0000+0.0000i, +0.0000+0.0000i]
  |10⟩ [+0.0000+0.0000i, +0.0000+0.0000i, -1.0000+0.0000i, +0.0000+0.0000i]
  |11⟩ [+0.0000+0.0000i, +0.0000+0.0000i, +0.0000+0.0000i, -1.0000+0.0000i]

============================================================
Demo 5: Conjugation exp_i(π/4,SWAP) ; Z ; exp_i(-π/4,SWAP)
============================================================
  [COMPILING conjugation...] OK - 3 gates on 2 qubits

Compiled Circuit
================
Circuit: 3 gates on 2 qubits
Permutation: [0, 1]
Gates:
  Unitary2qBox on [0, 1]
  Z on [0]
  Unitary2qBox on [0, 1]

Conjugation result:
  |00⟩ [+1.0000+0.0000i, +0.0000+0.0000i, +0.0000+0.0000i, +0.0000+0.0000i]
  |01⟩ [+0.0000+0.0000i, +0.0000+0.0000i, +0.0000+1.0000i, +0.0000+0.0000i]
  |10⟩ [+0.0000+0.0000i, +0.0000-1.0000i, -0.0000+0.0000i, +0.0000+0.0000i]
  |11⟩ [+0.0000+0.0000i, +0.0000+0.0000i, +0.0000+0.0000i, -1.0000+0.0000i]

✓ VERIFY: Conjugation is unitary? True

============================================================
Demo 6: Composition law exp(θ);exp(θ) = exp(2θ)
============================================================
  [COMPILING exp_i(π/2, SWAP)...] OK - 1 gates on 2 qubits
  [COMPILING exp(π/4);exp(π/4)...] OK - 2 gates on 2 qubits

Double composition
==================
Circuit: 2 gates on 2 qubits
Permutation: [0, 1]
Gates:
  Unitary2qBox on [0, 1]
  Unitary2qBox on [0, 1]

✓ VERIFY: exp(π/4);exp(π/4) = exp(π/2)? True
  Phase factor: 1.0000-0.0000j

============================================================
Summary
============================================================

ExpInvolution Infrastructure Test
─────────────────────────────────
Type: Q ⊗ Q (2 qubits)
SWAP = TwistTen(Q,Q) — wire permutation

SWAP² = I (involutive)                          ✓
exp_i(θ, SWAP) = cos(θ)I + i·sin(θ)·SWAP       ✓
exp(iθ) · exp(-iθ) = I                          ✓
Conjugation is unitary                          ✓
Composition law: exp(θ);exp(θ) = exp(2θ)        ✓

The ExpInvolution infrastructure correctly implements exp(iθ·P)
for wire-permutation involutions P.

✓ ALL TESTS PASSED!

Tip: Run with --circuits to see ASCII circuit diagrams
