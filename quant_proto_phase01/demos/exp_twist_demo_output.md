============================================================
 Exponential of Involution Demo
 exp_i(π/4, Twist) ; exp_i(π/4, Twist) = i·Twist
============================================================

============================================================
 1. The Involution: Twist (TwistTen)
============================================================

Term: TwistTen(Q, Q)
Type: Q ⊗ Q → Q ⊗ Q

Compiled circuit:
  Gates: 0
  Permutation: [1, 0]

SWAP (Twist) matrix:
  [+1.0000+0.0000i, +0.0000+0.0000i, +0.0000+0.0000i, +0.0000+0.0000i]
  [+0.0000+0.0000i, +0.0000+0.0000i, +1.0000+0.0000i, +0.0000+0.0000i]
  [+0.0000+0.0000i, +1.0000+0.0000i, +0.0000+0.0000i, +0.0000+0.0000i]
  [+0.0000+0.0000i, +0.0000+0.0000i, +0.0000+0.0000i, +1.0000+0.0000i]

============================================================
 2. Single exp_i(π/4, Twist)
============================================================

Term: ExpInvolution(π/4, TwistTen(Q,Q))
Type: Q ⊗ Q → Q ⊗ Q

Compiled circuit:
  Gates: 3
  Commands:
    XXPhase(3.75) q[0], q[1];
    YYPhase(3.75) q[0], q[1];
    ZZPhase(3.75) q[0], q[1];

Expected exp(iπ/4 · SWAP):
  [+0.7071+0.7071i, +0.0000+0.0000i, +0.0000+0.0000i, +0.0000+0.0000i]
  [+0.0000+0.0000i, +0.7071+0.0000i, +0.0000+0.7071i, +0.0000+0.0000i]
  [+0.0000+0.0000i, +0.0000+0.7071i, +0.7071+0.0000i, +0.0000+0.0000i]
  [+0.0000+0.0000i, +0.0000+0.0000i, +0.0000+0.0000i, +0.7071+0.7071i]

(qiskit not available for unitary extraction)

============================================================
 3. Composition: exp_i(π/4, Twist) ; exp_i(π/4, Twist)
============================================================

Term: Seq(ExpInvolution(π/4, twist), ExpInvolution(π/4, twist))
Type: Q ⊗ Q → Q ⊗ Q

Compiled circuit:
  Gates: 6
  Commands:
    XXPhase(3.75) q[0], q[1];
    YYPhase(3.75) q[0], q[1];
    ZZPhase(3.75) q[0], q[1];
    XXPhase(3.75) q[0], q[1];
    YYPhase(3.75) q[0], q[1];
    ZZPhase(3.75) q[0], q[1];

Expected exp(iπ/2 · SWAP) = i·SWAP:
  [+0.0000+1.0000i, +0.0000+0.0000i, +0.0000+0.0000i, +0.0000+0.0000i]
  [+0.0000+0.0000i, +0.0000+0.0000i, +0.0000+1.0000i, +0.0000+0.0000i]
  [+0.0000+0.0000i, +0.0000+1.0000i, +0.0000+0.0000i, +0.0000+0.0000i]
  [+0.0000+0.0000i, +0.0000+0.0000i, +0.0000+0.0000i, +0.0000+1.0000i]

============================================================
 4. Mathematical Verification
============================================================

The identity follows from:

    exp(iθP) = cos(θ)·I + i·sin(θ)·P    (for involution P² = I)

Therefore:
    exp(iθP) · exp(iθP) = [cos(θ)·I + i·sin(θ)·P]²
                        = cos²(θ)·I + 2i·cos(θ)·sin(θ)·P + i²·sin²(θ)·P²
                        = cos²(θ)·I + i·sin(2θ)·P - sin²(θ)·I   (using P² = I)
                        = [cos²(θ) - sin²(θ)]·I + i·sin(2θ)·P
                        = cos(2θ)·I + i·sin(2θ)·P
                        = exp(2iθP)

For θ = π/4:
    exp(iπ/4·P) · exp(iπ/4·P) = exp(iπ/2·P)
                               = cos(π/2)·I + i·sin(π/2)·P
                               = 0·I + i·1·P
                               = i·P

So: exp_i(π/4, Twist) ; exp_i(π/4, Twist) = i·Twist

Up to global phase (which is unobservable), this equals Twist!


============================================================
 5. Verification: (exp;exp) vs Twist
============================================================
Eigenvalue analysis:

SWAP eigenvalues:
  -1.0000+0.0000i
  +1.0000+0.0000i
  +1.0000+0.0000i
  +1.0000+0.0000i

i·SWAP eigenvalues:
  +0.0000+1.0000i
  +0.0000+1.0000i
  +0.0000+1.0000i
  +0.0000-1.0000i

The eigenvalues of i·SWAP are just i times those of SWAP.
This confirms that i·SWAP = i · SWAP (global phase times SWAP).

In quantum mechanics, global phase is unobservable,
so exp_i(π/4, Twist) ; exp_i(π/4, Twist) ≡ Twist

============================================================
 6. Circuit Summary
============================================================

┌─────────────────────────────────────────────────────────────┐
│  Term                              │ Gates │ Result         │
├─────────────────────────────────────────────────────────────┤
│  TwistTen(Q,Q)                     │   0   │ Permutation    │
│  exp_i(π/4, Twist)                 │   3   │ ExpSwap gate   │
│  exp_i(π/4, Twist) ; exp_i(π/4, Twist) │   6   │ Two ExpSwaps   │
└─────────────────────────────────────────────────────────────┘

Key result:
  Two ExpSwap(π/4) gates compose to give exp(iπ/2·SWAP) = i·SWAP
  This equals SWAP up to global phase, confirming the involution identity.


✓ Demo complete!
