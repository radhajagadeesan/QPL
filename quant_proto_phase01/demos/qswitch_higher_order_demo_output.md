# QSwitch Higher-Order Demo Output

Run with: `PYTHONPATH=src python demos/qswitch_higher_order_demo.py`

---

```
==========================================================================
  QUANTUM SWITCH AS A HIGHER-ORDER COMBINATOR
==========================================================================


TYPE SIGNATURE:

    QSwitch : (Q → Q) → (Q → Q) → (Q ⊗ Q → Q ⊗ Q)

In curried form:

    QSwitch : (Q → Q) → ((Q → Q) → (Q ⊗ Q → Q ⊗ Q))

SEMANTICS:

    QSwitch f g (ctrl, tgt) =
        | ctrl = |0⟩  →  (f ; g)(tgt)      -- f then g
        | ctrl = |1⟩  →  (g ; f)(tgt)      -- g then f
        | α|0⟩ + β|1⟩ →  α|0⟩(f;g)|ψ⟩ + β|1⟩(g;f)|ψ⟩   -- superposition!

The quantum switch applies two operations in BOTH ORDERS simultaneously
when the control qubit is in superposition.


==========================================================================
  1. QSwitch as a combinator (before instantiation)
==========================================================================


QSwitch is a higher-order function that takes two operations and returns
a quantum circuit. Before we give it concrete gates, it's just a recipe:

    QSwitch : (Q → Q) → (Q → Q) → (Q ⊗ Q → Q ⊗ Q)

    QSwitch f g = λ(ctrl, tgt).
        case ctrl of
            | |0⟩ → (f ; g)(tgt)
            | |1⟩ → (g ; f)(tgt)

IMPLEMENTATION via controlled gates:

    QSwitch f g = X[0] ; C-f[0,1] ; C-g[0,1] ; X[0] ; C-g[0,1] ; C-f[0,1]
                  ───────────────────────────   ─────────────────────────
                        anti-ctrl (f;g)               ctrl (g;f)
                     fires when ctrl=|0⟩           fires when ctrl=|1⟩


==========================================================================
  2. Partial application: QSwitch(H)
==========================================================================


Apply QSwitch to just the first argument:

    QSwitch H : (Q → Q) → (Q ⊗ Q → Q ⊗ Q)

This is still a function waiting for the second operation g.
It "remembers" that f = H and will apply H in both branches.

Conceptually:

    QSwitch H = λg. λ(ctrl, tgt).
        case ctrl of
            | |0⟩ → (H ; g)(tgt)
            | |1⟩ → (g ; H)(tgt)

qswitch_H = QSwitch('H')  -- partially applied
qswitch_H : (Q → Q) → (Q ⊗ Q → Q ⊗ Q)

==========================================================================
  3. Full application: QSwitch(H)(S)
==========================================================================


Apply the second argument:

    QSwitch H S : Q ⊗ Q → Q ⊗ Q

Now we have a concrete circuit:
    - When ctrl=|0⟩: apply H then S to target
    - When ctrl=|1⟩: apply S then H to target

QSwitch H S : Q ⊗ Q → Q ⊗ Q

Term: Seq(X(i=0, ty_total=Ten(left=Q(), right=Q())), Seq(CH(i=0, j=1, ty_total=Ten(left=Q(), right=Q())), Seq(CS(i=0, j=1, ty_total=Ten(left=Q(), right=Q())), Seq(X(i=0, ty_total=Ten(left=Q(), right=Q())), Seq(CS(i=0, j=1, ty_total=Ten(left=Q(), right=Q())), CH(i=0, j=1, ty_total=Ten(left=Q(), right=Q())))))))

==========================================================================
  4. Compiled circuit
==========================================================================

Qubits: 2
Gates:  6

Commands:
  X q[0];
  CH q[0], q[1];
  CS q[0], q[1];
  X q[0];
  CS q[0], q[1];
  CH q[0], q[1];

Circuit diagram:

  q[0] ──X───●───●───X───●───●──
            │   │       │   │
  q[1] ────CH──CS──────CS──CH──

Trace:
  - X[0] flips ctrl
  - CH[0,1]; CS[0,1] = controlled H;S (fires when ctrl now |1⟩, was |0⟩)
  - X[0] restores ctrl
  - CS[0,1]; CH[0,1] = controlled S;H (fires when ctrl is |1⟩)


==========================================================================
  5. Other instantiations
==========================================================================

QSwitch is parametric — we can instantiate with different gates:

  QSwitch(H, S): Hadamard and S-gate
    Gates: X → CH → CS → X → CS → CH

  QSwitch(X, Z): Pauli X and Z
    Gates: X → CX → CZ → X → CZ → CX

  QSwitch(H, X): Hadamard and Pauli X
    Gates: X → CH → CX → X → CX → CH


==========================================================================
  6. Summary
==========================================================================


┌──────────────────────────────────────────────────────────────────────────┐
│  QSWITCH AS A HIGHER-ORDER COMBINATOR                                    │
├──────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  Type:    QSwitch : (Q→Q) → (Q→Q) → (Q⊗Q → Q⊗Q)                         │
│                                                                          │
│  Partial: QSwitch H : (Q→Q) → (Q⊗Q → Q⊗Q)      -- waiting for g         │
│                                                                          │
│  Full:    QSwitch H S : Q⊗Q → Q⊗Q              -- concrete circuit      │
│                                                                          │
│  Circuit: X[0]; CH[0,1]; CS[0,1]; X[0]; CS[0,1]; CH[0,1]                │
│                                                                          │
├──────────────────────────────────────────────────────────────────────────┤
│  KEY INSIGHT: Higher-order quantum programming!                          │
│                                                                          │
│  QSwitch takes FUNCTIONS as arguments and produces a circuit that        │
│  applies them in superposition of different orders.                      │
│                                                                          │
│  This is impossible classically — you can only apply f-then-g OR         │
│  g-then-f, not both simultaneously.                                      │
└──────────────────────────────────────────────────────────────────────────┘

```
