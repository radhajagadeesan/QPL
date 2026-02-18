# QSwitch Term Demo Output

Run with: `PYTHONPATH=src python demos/qswitch_term_demo.py`

---

```

======================================================================
  QSWITCH AS A TERM USING CASE
======================================================================


TYPE DEFINITIONS:

    Bool  = I + I           width = 1
    I ⊗ Q                   width = 1
    Bool ⊗ Q = (I+I) ⊗ Q    width = 2


======================================================================
  1. The Distribution Step
======================================================================


To use Case on Bool ⊗ Q, we first distribute:

    (I + I) ⊗ Q  ──DistR──→  (I ⊗ Q) + (I ⊗ Q)

This transforms the tensor-of-sum into a sum-of-tensors,
allowing Case to branch on the tag while keeping the Q payload.

DistR(I, I, Q) : (I ⊗ (I ⊕ Q)) → ((I ⊗ I) ⊕ (I ⊗ Q))

======================================================================
  2. The Case Branches
======================================================================


Each branch operates on I ⊗ Q (which has width 1, just the Q).
Since I has width 0, the payload is effectively just Q.

    Left branch:  I ⊗ Q → I ⊗ Q   applies H ; S
    Right branch: I ⊗ Q → I ⊗ Q   applies S ; H

Left branch (H;S):  (Ten(left=Unit(), right=Q()), Ten(left=Unit(), right=Q()))
Right branch (S;H): (Ten(left=Unit(), right=Q()), Ten(left=Unit(), right=Q()))

======================================================================
  3. The Case Term
======================================================================


Case combines the branches into a copairing:

    Case(I⊗Q, I⊗Q, left, right) : (I⊗Q) + (I⊗Q) → (I⊗Q) + (I⊗Q)

When compiled, this becomes controlled gates:
    - Left branch: anti-controlled (fires when tag=0)
    - Right branch: controlled (fires when tag=1)

Case term type: (Plus(left=Ten(left=Unit(), right=Q()), right=Ten(left=Unit(), right=Q())), Plus(left=Ten(left=Unit(), right=Q()), right=Ten(left=Unit(), right=Q())))

======================================================================
  4. Full QSwitch = DistR ; Case
======================================================================


QSwitch[H,S] = DistR ; Case[H;S, S;H]

Type: (I ⊗ (I ⊕ Q)) → ((I ⊗ Q) ⊕ (I ⊗ Q))
    ≅ Bool ⊗ Q → Bool ⊗ Q


======================================================================
  5. Compilation
======================================================================

Qubits: 2
Gates:  6

Commands:
  X q[0];
  CH q[0], q[1];
  CS q[0], q[1];
  X q[0];
  CS q[0], q[1];
  CH q[0], q[1];

Compilation log:
  DistR perm=[0, 1] (tag moves to front)
  Case: 2 left gates (anti-ctrl), 2 right gates (ctrl) at offset 0

======================================================================
  6. Circuit Diagram
======================================================================


  ctrl ──X───●───●───X───●───●──
             │   │       │   │
  tgt  ─────CH──CS──────CS──CH──

Gate sequence:
  X q[0]        ← flip ctrl for anti-control
  CH q[0],q[1]  ← controlled H (left branch, part 1)
  CS q[0],q[1]  ← controlled S (left branch, part 2)
  X q[0]        ← restore ctrl
  CS q[0],q[1]  ← controlled S (right branch, part 1)
  CH q[0],q[1]  ← controlled H (right branch, part 2)


======================================================================
  7. Execution Semantics
======================================================================


When ctrl = |0⟩:
  - X flips to |1⟩ → CH;CS fire → X flips back to |0⟩
  - Target receives: H ; S ✓
  - Right branch gates skip (ctrl is |0⟩)

When ctrl = |1⟩:
  - X flips to |0⟩ → CH;CS skip → X flips back to |1⟩
  - CS;CH fire
  - Target receives: S ; H ✓

When ctrl = |+⟩ = (|0⟩ + |1⟩)/√2:
  - BOTH branches execute coherently!
  - |0⟩|ψ⟩ → |0⟩(HS)|ψ⟩
  - |1⟩|ψ⟩ → |1⟩(SH)|ψ⟩
  - Result: (|0⟩(HS)|ψ⟩ + |1⟩(SH)|ψ⟩)/√2


======================================================================
  8. Wrapping in Lambda
======================================================================


λx:(Bool⊗Q). DistR ; Case[H;S, S;H]

Type: (I ⊗ (I ⊕ Q)) → ((I ⊗ Q) ⊕ (I ⊗ Q))

This is a proper closed term representing QSwitch[H,S].

Compiled λ-term: 6 gates

======================================================================
  Summary
======================================================================


┌──────────────────────────────────────────────────────────────────────┐
│  QSWITCH AS A TERM                                                   │
├──────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  TERM:                                                               │
│    QSwitch[H,S] = DistR(I,I,Q) ; Case(I⊗Q, I⊗Q, H;S, S;H)           │
│                                                                      │
│  TYPE:                                                               │
│    Bool ⊗ Q → (I⊗Q) + (I⊗Q) ≅ Bool ⊗ Q → Bool ⊗ Q                   │
│                                                                      │
│  COMPILATION:                                                        │
│    DistR → pure permutation (0 gates)                                │
│    Case  → controlled gates (6 gates total)                          │
│                                                                      │
│  CIRCUIT:                                                            │
│    X[0]; CH[0,1]; CS[0,1]; X[0]; CS[0,1]; CH[0,1]                   │
│                                                                      │
├──────────────────────────────────────────────────────────────────────┤
│  KEY INSIGHT:                                                        │
│                                                                      │
│  Case on a superposition → controlled gates                          │
│  Both branches execute coherently on |+⟩ control!                    │
└──────────────────────────────────────────────────────────────────────┘

```
