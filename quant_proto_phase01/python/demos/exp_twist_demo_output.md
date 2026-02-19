============================================================
  LIVE EXECUTION: Exponential of Involution Test
  All compilations are real - no fabricated output
============================================================

Verifies exp_i(π/4, Twist) ; exp_i(π/4, Twist) = i·Twist
by extracting unitaries from compiled circuits.

============================================================
Demo 1: TwistTen Compilation
============================================================
  [COMPILING TwistTen(Q, Q)...] OK - 1 gates on 2 qubits

Compiled Circuit
================
Circuit: 1 gates on 2 qubits
Permutation: [0, 1]
Gates:
  SWAP on [0, 1]

U_twist (from compiled circuit):
  [+1.0000+0.0000i, +0.0000+0.0000i, +0.0000+0.0000i, +0.0000+0.0000i]
  [+0.0000+0.0000i, +0.0000+0.0000i, +1.0000+0.0000i, +0.0000+0.0000i]
  [+0.0000+0.0000i, +1.0000+0.0000i, +0.0000+0.0000i, +0.0000+0.0000i]
  [+0.0000+0.0000i, +0.0000+0.0000i, +0.0000+0.0000i, +1.0000+0.0000i]

✓ VERIFY: U_twist = SWAP? True (phase=1.0000+0.0000j)

============================================================
Demo 2: exp_i(π/4, Twist) Compilation
============================================================
  [COMPILING ExpInvolution(π/4, TwistTen)...] OK - 1 gates on 2 qubits

Compiled Circuit
================
Circuit: 1 gates on 2 qubits
Permutation: [0, 1]
Gates:
  Unitary2qBox on [0, 1]

U_exp_single (from compiled circuit):
  [+0.7071+0.7071i, +0.0000+0.0000i, +0.0000+0.0000i, +0.0000+0.0000i]
  [+0.0000+0.0000i, +0.7071+0.0000i, +0.0000+0.7071i, +0.0000+0.0000i]
  [+0.0000+0.0000i, +0.0000+0.7071i, +0.7071+0.0000i, +0.0000+0.0000i]
  [+0.0000+0.0000i, +0.0000+0.0000i, +0.0000+0.0000i, +0.7071+0.7071i]

Expected exp(iπ/4 · SWAP):
  [+0.7071+0.7071i, +0.0000+0.0000i, +0.0000+0.0000i, +0.0000+0.0000i]
  [+0.0000+0.0000i, +0.7071+0.0000i, +0.0000+0.7071i, +0.0000+0.0000i]
  [+0.0000+0.0000i, +0.0000+0.7071i, +0.7071+0.0000i, +0.0000+0.0000i]
  [+0.0000+0.0000i, +0.0000+0.0000i, +0.0000+0.0000i, +0.7071+0.7071i]

✓ VERIFY: U_exp_single = exp(iπ/4·SWAP)? True (phase=1.0000+0.0000j)

============================================================
Demo 3: exp_i(π/4, twist) ; exp_i(π/4, twist) Composition
============================================================
  [COMPILING exp;exp composition...] OK - 2 gates on 2 qubits

Compiled Circuit
================
Circuit: 2 gates on 2 qubits
Permutation: [0, 1]
Gates:
  Unitary2qBox on [0, 1]
  Unitary2qBox on [0, 1]

U_composed (from compiled circuit):
  [+0.0000+1.0000i, +0.0000+0.0000i, +0.0000+0.0000i, +0.0000+0.0000i]
  [+0.0000+0.0000i, +0.0000+0.0000i, +0.0000+1.0000i, +0.0000+0.0000i]
  [+0.0000+0.0000i, +0.0000+1.0000i, +0.0000+0.0000i, +0.0000+0.0000i]
  [+0.0000+0.0000i, +0.0000+0.0000i, +0.0000+0.0000i, +0.0000+1.0000i]

Expected i·SWAP:
  [+0.0000+1.0000i, +0.0000+0.0000i, +0.0000+0.0000i, +0.0000+0.0000i]
  [+0.0000+0.0000i, +0.0000+0.0000i, +0.0000+1.0000i, +0.0000+0.0000i]
  [+0.0000+0.0000i, +0.0000+1.0000i, +0.0000+0.0000i, +0.0000+0.0000i]
  [+0.0000+0.0000i, +0.0000+0.0000i, +0.0000+0.0000i, +0.0000+1.0000i]

✓ VERIFY: U_composed = i·SWAP? True (phase=1.0000-0.0000j)

============================================================
Demo 4: Composition Law exp_i(θ);exp_i(θ) = exp_i(2θ)
============================================================
  [COMPILING exp(π/4);exp(π/4)...] OK - 2 gates on 2 qubits
  [COMPILING exp(π/2) direct...] OK - 1 gates on 2 qubits

exp_i(π/2, twist) Circuit
=========================
Circuit: 1 gates on 2 qubits
Permutation: [0, 1]
Gates:
  Unitary2qBox on [0, 1]

U_exp_half_pi (from compiled circuit):
  [+0.0000+1.0000i, +0.0000+0.0000i, +0.0000+0.0000i, +0.0000+0.0000i]
  [+0.0000+0.0000i, +0.0000+0.0000i, +0.0000+1.0000i, +0.0000+0.0000i]
  [+0.0000+0.0000i, +0.0000+1.0000i, +0.0000+0.0000i, +0.0000+0.0000i]
  [+0.0000+0.0000i, +0.0000+0.0000i, +0.0000+0.0000i, +0.0000+1.0000i]

✓ VERIFY: (exp_i(π/4);exp_i(π/4)) = exp_i(π/2)? True (phase=1.0000-0.0000j)

============================================================
✓ ALL INFRASTRUCTURE TESTS PASSED
============================================================

Verified by extracting unitaries from compiled circuits:

  1. TwistTen(Q,Q) compiles to SWAP
  2. exp_i(π/4, twist) compiles to exp(iπ/4·SWAP) (up to phase)
  3. exp_i(π/4, twist) ; exp_i(π/4, twist) = SWAP (up to phase)
  4. exp_i(π/4, twist) ; exp_i(π/4, twist) = exp_i(π/2, twist)

The composition law exp_i(θ,P) ; exp_i(θ,P) = exp_i(2θ,P) is verified!
