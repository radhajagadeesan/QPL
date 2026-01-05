============================================================
 Pauli Conjugation Identity: INFRASTRUCTURE TEST
 exp_i(π/4, X) ; Z ; exp_i(-π/4, X) = Y
============================================================

Qubit as I + I (one-hot encoding):
  - Physical: 2 tag wires [t₀, t₁]
  - Logical |0⟩ = |10⟩, Logical |1⟩ = |01⟩

Type: I + I (width = 2)

============================================================
 1. Build X = twist+[I,I]
============================================================
Term: TwistPlus(I, I)
Gates: 1
Permutation: [0, 1]

X (logical 2x2):
  [+0.0000+0.0000i, +1.0000+0.0000i]
  [+1.0000+0.0000i, +0.0000+0.0000i]

✓ VERIFY: X = Pauli-X? True

============================================================
 2. Build Z = Z gate on wire 1
============================================================
Term: Z(1, I+I)
Gates: 1

Z (logical 2x2):
  [+1.0000+0.0000i, +0.0000+0.0000i]
  [+0.0000+0.0000i, -1.0000+0.0000i]

✓ VERIFY: Z = Pauli-Z? True

============================================================
 3. Build Y = twist ; S[1] ; Sdg[0]
============================================================
Term: Seq(TwistPlus(I,I), S(1), Sdg(0))
Gates: 3
Commands:
  S q[0];
  Sdg q[1];
  SWAP q[0], q[1];

Y (logical 2x2):
  [+0.0000+0.0000i, +0.0000-1.0000i]
  [+0.0000+1.0000i, +0.0000+0.0000i]

✓ VERIFY: Y = Pauli-Y? True (phase=1.0000+0.0000j)

============================================================
 4. Build exp_i(π/4, X)
============================================================
Term: ExpInvolution(π/4, TwistPlus(I,I))
Gates: 3
Commands:
  XXPhase(3.75) q[0], q[1];
  YYPhase(3.75) q[0], q[1];
  ZZPhase(3.75) q[0], q[1];

exp_i(π/4, X) (logical 2x2):
  [+0.6533-0.2706i, +0.2706+0.6533i]
  [+0.2706+0.6533i, +0.6533-0.2706i]

✓ VERIFY: matches exp(iπ/4·X)? True

============================================================
 5. Build exp_i(-π/4, X)
============================================================
Term: ExpInvolution(-π/4, TwistPlus(I,I))
Gates: 3

exp_i(-π/4, X) (logical 2x2):
  [+0.6533+0.2706i, +0.2706-0.6533i]
  [+0.2706-0.6533i, +0.6533+0.2706i]

============================================================
 6. Build conjugation: exp_i(π/4,X) ; Z ; exp_i(-π/4,X)
============================================================
Term: Seq(exp_i(π/4,X), Z, exp_i(-π/4,X))
Gates: 7
Commands:
  XXPhase(3.75) q[0], q[1];
  YYPhase(3.75) q[0], q[1];
  ZZPhase(3.75) q[0], q[1];
  Z q[1];
  XXPhase(0.25) q[0], q[1];
  YYPhase(0.25) q[0], q[1];
  ZZPhase(0.25) q[0], q[1];

Conjugation (logical 2x2):
  [-0.0000-0.0000i, -0.0000+1.0000i]
  [+0.0000-1.0000i, +0.0000+0.0000i]

============================================================
 7. VERIFY: Conjugation = Y
============================================================

Conjugation result:
  [-0.0000-0.0000i, -0.0000+1.0000i]
  [+0.0000-1.0000i, +0.0000+0.0000i]

Expected Y:
  [+0.0000+0.0000i, -0.0000-1.0000i]
  [+0.0000+1.0000i, +0.0000+0.0000i]

Conjugation = Y (up to phase)? True
Phase factor: -1.0000-0.0000j

Conjugation = Y_explicit? True (phase=-1.0000-0.0000j)

============================================================
 8. Summary
============================================================

┌────────────────────────────────────────────────────────────┐
│  Qubit as I + I (one-hot encoding)                         │
├────────────────────────────────────────────────────────────┤
│  X = twist+[I,I]                  → Pauli-X ✓              │
│  Z = Z[1]                         → Pauli-Z ✓              │
│  Y = twist ; S[1] ; Sdg[0]        → Pauli-Y ✓              │
├────────────────────────────────────────────────────────────┤
│  exp_i(π/4, X) ; Z ; exp_i(-π/4, X) = Y ✓                  │
└────────────────────────────────────────────────────────────┘

Verified by:
  1. Compiling each term to pytket circuit
  2. Extracting unitary via circuit.get_unitary()
  3. Extracting logical 2x2 submatrix from physical 4x4
  4. Comparing matrices up to global phase

✓ ALL INFRASTRUCTURE TESTS PASSED!
