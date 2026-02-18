# QSwitch Instantiation Demo Output

Run with: `PYTHONPATH=python/src python python/demos/qswitch_instantiation_demo.py --circuits`

This demo shows **compositional construction** of QSwitch: the circuit structure
comes from the abstract QSwitch combinator, with concrete gates H and S plugged in.

---

## Section 1: Compositional Construction

```
KEY INSIGHT: QSwitch is built COMPOSITIONALLY
──────────────────────────────────────────────

The QSwitch circuit is NOT built by directly embedding gates.
Instead, it's built by COMPOSING:

  1. ABSTRACT STRUCTURE: The QSwitch combinator (fixed shape)
  2. CONCRETE GATES: The functions f and g (parameters)

ABSTRACT QSWITCH STRUCTURE:

    def make_qswitch(f, g):
        '''
        QSwitch = DistL ; Case(
            left  = (Id_I ⊗ g) ; (Id_I ⊗ f),   -- g then f
            right = (Id_I ⊗ f) ; (Id_I ⊗ g)    -- f then g
        )
        '''
        left_branch  = Seq(TenTerm(Id(I), g), TenTerm(Id(I), f))
        right_branch = Seq(TenTerm(Id(I), f), TenTerm(Id(I), g))
        return Seq(DistL, Case(left_branch, right_branch))

INSTANTIATION:

    QSwitch[H, S] = make_qswitch(H, S)

The circuit structure comes from the COMBINATOR.
The concrete behavior comes from the GATES.
```

---

## Section 2: Abstract QSwitch Type

```
QSWITCH TYPE SIGNATURE:

    QSwitch : (Q → Q) → (Q → Q) → (Bool ⊗ Q) → (Bool ⊗ Q)
              ───────   ───────   ─────────────────────────
                 f         g           input → output

    Parameters:
      f : Q → Q    (first function, width 1)
      g : Q → Q    (second function, width 1)

    Input/Output: Bool ⊗ Q
      Wire 0: control qubit (Bool = I + I, width 1)
      Wire 1: target qubit (Q, width 1)
      Total width: 2

SEMANTICS:

    |0⟩|ψ⟩  →  |0⟩ f(g(ψ))     (g first, then f)
    |1⟩|ψ⟩  →  |1⟩ g(f(ψ))     (f first, then g)
    |+⟩|ψ⟩  →  superposition of both orders!

CONCRETE GATE TERMS:
  H = H(0, Q())  :  Q → Q
  S = S(0, Q())  :  Q → Q
```

---

## Section 3: QSwitch[H, H] — Same Function (f = g)

```
SIMPLIFICATION ANALYSIS:

    When f = g, both branches compute the SAME thing:

        |0⟩|ψ⟩  →  |0⟩ f(f(ψ))
        |1⟩|ψ⟩  →  |1⟩ f(f(ψ))     ← IDENTICAL!

    The control qubit has NO EFFECT.

    For f = H:  H² = I (Hadamard is self-inverse)
    Therefore:  QSwitch[H, H] = Identity!


COMPOSITIONAL CONSTRUCTION:

    qswitch_hh = make_qswitch(H, H)
    Type: ((I ⊕ I) ⊗ Q) → ... (width 2)
```

**Compiled Circuit:**
```
Circuit: 6 gates on 2 qubits
Permutation: [0, 1]
Gates:
  X on [0]
  CH on [0, 1]
  CH on [0, 1]
  X on [0]
  CH on [0, 1]
  CH on [0, 1]

Circuit Diagram:
q[0]: ───[X]─────●────●──[X]─────●────●──
q[1]: ─────────[H]──[H]────────[H]──[H]──
```

**Verification:**
```
Unitary equals identity matrix? True

CONFIRMED: QSwitch[H, H] = Identity

The 6 gates completely cancel because H² = I.
This demonstrates: when f = g, QSwitch degenerates.
```

---

## Section 4: QSwitch[H, S] — Different Functions (f ≠ g)

```
NON-COMMUTATIVITY CHECK:

    H ∘ S ≠ S ∘ H  (Hadamard and S-gate don't commute)

    Therefore the two branches produce DIFFERENT results:
        |0⟩|ψ⟩  →  |0⟩ H(S(ψ))     (S then H)
        |1⟩|ψ⟩  →  |1⟩ S(H(ψ))     (H then S)

    NO SIMPLIFICATION POSSIBLE — this is the true quantum switch!


COMPOSITIONAL CONSTRUCTION:

    qswitch_hs = make_qswitch(H, S)
    Type: ((I ⊕ I) ⊗ Q) → ... (width 2)
```

**Compiled Circuit:**
```
Circuit: 6 gates on 2 qubits
Permutation: [0, 1]
Gates:
  X on [0]
  CS on [0, 1]
  CH on [0, 1]
  X on [0]
  CH on [0, 1]
  CS on [0, 1]

Circuit Diagram:
q[0]: ───[X]─────●────●──[X]─────●────●──
q[1]: ─────────[S]──[H]────────[H]──[S]──
```

**Circuit Derivation (from compositional structure):**
```
The circuit comes from the QSwitch COMBINATOR structure:

    QSwitch = DistL ; Case(left, right)

    where Case compiles to anti-control pattern:
        X[ctrl] ; Controlled(left) ; X[ctrl] ; Controlled(right)

With f=H, g=S plugged in:

    left  = TenTerm(Id(I), S) ; TenTerm(Id(I), H)  →  CS ; CH
    right = TenTerm(Id(I), H) ; TenTerm(Id(I), S)  →  CH ; CS

Result:
    X[0] ; CS[0,1] ; CH[0,1] ; X[0] ; CH[0,1] ; CS[0,1]
    ────   ─────────────────   ────   ─────────────────
    flip   anti-controlled     flip   controlled
           (S;H branch)        back   (H;S branch)
```

**Execution Trace:**
```
Input |0⟩|ψ⟩ (left branch → S then H):
  X         →  |1⟩|ψ⟩
  CS        →  |1⟩ S|ψ⟩      (fires)
  CH        →  |1⟩ HS|ψ⟩     (fires)
  X         →  |0⟩ HS|ψ⟩
  CH, CS    →  (skip)
  Output: |0⟩ H(S|ψ⟩)   ✓

Input |1⟩|ψ⟩ (right branch → H then S):
  X         →  |0⟩|ψ⟩
  CS, CH    →  (skip)
  X         →  |1⟩|ψ⟩
  CH        →  |1⟩ H|ψ⟩      (fires)
  CS        →  |1⟩ SH|ψ⟩     (fires)
  Output: |1⟩ S(H|ψ⟩)   ✓

Input |+⟩|ψ⟩:
  BOTH branches execute coherently!
  Output: (|0⟩ H(S|ψ⟩) + |1⟩ S(H|ψ⟩)) / √2
  This is INDEFINITE CAUSAL ORDER!
```

---

## Summary: Compositional Construction

```
COMPOSITIONAL CONSTRUCTION DEMONSTRATED
───────────────────────────────────────

    ┌─────────────────────────────────────────────────────────────────┐
    │                                                                 │
    │   ABSTRACT QSWITCH COMBINATOR                                   │
    │   ════════════════════════════                                  │
    │                                                                 │
    │   make_qswitch(f, g) =                                          │
    │       DistL ; Case(                                             │
    │           left  = (Id ⊗ g) ; (Id ⊗ f),                          │
    │           right = (Id ⊗ f) ; (Id ⊗ g)                           │
    │       )                                                         │
    │                                                                 │
    │   This structure is FIXED — it's the QSwitch combinator.        │
    │                                                                 │
    └─────────────────────────────────────────────────────────────────┘
                              │
                              │ plug in concrete gates
                              ▼
    ┌─────────────────────────────────────────────────────────────────┐
    │                                                                 │
    │   INSTANTIATION                                                 │
    │   ═════════════                                                 │
    │                                                                 │
    │   QSwitch[H, H] = make_qswitch(H, H)  →  Identity (H² = I)      │
    │   QSwitch[H, S] = make_qswitch(H, S)  →  6 gates, non-trivial   │
    │                                                                 │
    │   The circuit structure comes from COMPOSING:                   │
    │     • The abstract QSwitch combinator (provides shape)          │
    │     • The concrete gates H, S (provide behavior)                │
    │                                                                 │
    └─────────────────────────────────────────────────────────────────┘


KEY INSIGHT:

    The QSwitch circuit is built COMPOSITIONALLY:

        Circuit = Combinator(Structure) ∘ Gates(Behavior)

    NOT by directly embedding gates into a flat circuit.

    This is higher-order quantum programming:
    - QSwitch is a COMBINATOR that takes functions as arguments
    - H and S are FUNCTION TERMS that get composed in
    - The final circuit emerges from their composition
```
