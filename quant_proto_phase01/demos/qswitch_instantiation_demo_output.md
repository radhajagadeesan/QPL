
==========================================================================
  QSWITCH INSTANTIATION DEMO
==========================================================================


This demo shows QSwitch instantiated with concrete functions.
For the abstract QSwitch structure, see: qswitch_abstract_circuit_demo.py

Recall the abstract QSwitch semantics:
    │0⟩│ψ⟩  →  │0⟩ f(g(ψ))     (apply g then f)
    │1⟩│ψ⟩  →  │1⟩ g(f(ψ))     (apply f then g)


==========================================================================
  SECTION 1: QSwitch with ONE Function (f = g)
==========================================================================


┌─────────────────────────────────────────────────────────────────────────┐
│  SIMPLIFICATION ANALYSIS (before compiling)                             │
└─────────────────────────────────────────────────────────────────────────┘

When f = g (same function applied to both slots), the QSwitch semantics
become:

    │0⟩│ψ⟩  →  │0⟩ f(f(ψ))     (apply f then f)
    │1⟩│ψ⟩  →  │1⟩ f(f(ψ))     (apply f then f)
                  ─────────
                  IDENTICAL!

OBSERVATION: Both branches compute the SAME thing: f ∘ f

CONSEQUENCE: The control qubit has NO EFFECT on the output!
             The QSwitch degenerates to unconditional f ∘ f.


ALGEBRAIC SIMPLIFICATION:
─────────────────────────

    QSwitch[f, f] ≡ Id_ctrl ⊗ (f ∘ f)

    The control qubit passes through unchanged.
    The target gets f applied twice, regardless of control.


SPECIAL CASE: f = H (Hadamard)
──────────────────────────────

    H ∘ H = H² = I    (Hadamard is self-inverse)

    Therefore:
        QSwitch[H, H] ≡ Id_ctrl ⊗ I = Id

    The ENTIRE circuit simplifies to IDENTITY!


┌─────────────────────────────────────────────────────────────────────────┐
│  CIRCUIT (QSwitch[H, H])                                                │
└─────────────────────────────────────────────────────────────────────────┘

Type: ((I ⊕ I) ⊗ Q) → ((I ⊗ Q) ⊕ (I ⊗ Q))
      (width 2 → width 2)

Compiling QSwitch[H, H]...

Gate count: 6

Gate sequence:
    X q[0];
    CH q[0], q[1];
    CH q[0], q[1];
    X q[0];
    CH q[0], q[1];
    CH q[0], q[1];

CIRCUIT DIAGRAM:
────────────────

    ctrl ──X───●───●───X───●───●──
           │   │   │   │   │   │
    tgt  ─────CH──CH─────CH──CH───


VERIFICATION:
─────────────

    Unitary equals identity matrix? True

    ✓ CONFIRMED: QSwitch[H, H] = Identity

    The 6 gates completely cancel:
      • X;X = I (the two X gates cancel)
      • CH;CH = I (controlled-H squared is identity)
      • CH;CH = I (second pair also cancels)


==========================================================================
  SECTION 2: QSwitch with TWO Functions (f ≠ g)
==========================================================================


┌─────────────────────────────────────────────────────────────────────────┐
│  SIMPLIFICATION ANALYSIS (before compiling)                             │
└─────────────────────────────────────────────────────────────────────────┘

When f ≠ g (different functions), the QSwitch semantics are:

    │0⟩│ψ⟩  →  │0⟩ f(g(ψ))     (apply g then f)
    │1⟩│ψ⟩  →  │1⟩ g(f(ψ))     (apply f then g)
                  ─────────
                  DIFFERENT!

QUESTION: Can we simplify?

ANSWER: Only if f and g COMMUTE, i.e., f ∘ g = g ∘ f


EXAMPLE: f = H, g = S
─────────────────────

    H ∘ S  =  HS  (Hadamard then S-gate)
    S ∘ H  =  SH  (S-gate then Hadamard)

    Do they commute?

    H = 1/√2 [1   1]      S = [1  0]
             [1  -1]          [0  i]

    HS = 1/√2 [1   i]     SH = 1/√2 [1   1]
              [1  -i]               [i  -i]

    HS ≠ SH   →   H and S do NOT commute!


CONSEQUENCE: NO SIMPLIFICATION POSSIBLE
───────────────────────────────────────

    Since H ∘ S ≠ S ∘ H, the two branches produce genuinely
    different results. The control qubit MATTERS.

    Both branches must be compiled with controlled gates.
    This is the TRUE quantum switch with indefinite causal order.


┌─────────────────────────────────────────────────────────────────────────┐
│  CIRCUIT (QSwitch[H, S])                                                │
└─────────────────────────────────────────────────────────────────────────┘

Type: ((I ⊕ I) ⊗ Q) → ((I ⊗ Q) ⊕ (I ⊗ Q))
      (width 2 → width 2)

Compiling QSwitch[H, S]...

Gate count: 6

Gate sequence:
    X q[0];
    CS q[0], q[1];
    CH q[0], q[1];
    X q[0];
    CH q[0], q[1];
    CS q[0], q[1];

CIRCUIT DIAGRAM:
────────────────

    ctrl ──X───●───●───X───●───●──
           │   │   │   │   │   │
    tgt  ─────CS──CH─────CH──CS───

    Where:
      X       = Pauli-X (bit flip) for anti-control
      CH      = Controlled-Hadamard
      CS      = Controlled-S (phase gate)


EXECUTION TRACE:
────────────────

    Input │0⟩│ψ⟩ (Left branch → f(g(x)) = H(S(x))):
      X         →  │1⟩│ψ⟩
      CS        →  │1⟩ S│ψ⟩      (fires, ctrl=1)
      CH        →  │1⟩ HS│ψ⟩     (fires, ctrl=1)
      X         →  │0⟩ HS│ψ⟩
      CH        →  │0⟩ HS│ψ⟩     (skips, ctrl=0)
      CS        →  │0⟩ HS│ψ⟩     (skips, ctrl=0)
      Output: │0⟩ H(S|ψ⟩)  ✓   (applied S then H = f∘g)

    Input │1⟩│ψ⟩ (Right branch → g(f(x)) = S(H(x))):
      X         →  │0⟩│ψ⟩
      CS        →  │0⟩│ψ⟩        (skips, ctrl=0)
      CH        →  │0⟩│ψ⟩        (skips, ctrl=0)
      X         →  │1⟩│ψ⟩
      CH        →  │1⟩ H│ψ⟩      (fires, ctrl=1)
      CS        →  │1⟩ SH│ψ⟩     (fires, ctrl=1)
      Output: │1⟩ S(H|ψ⟩)  ✓   (applied H then S = g∘f)

    Input │+⟩│ψ⟩ = (│0⟩ + │1⟩)/√2 │ψ⟩:
      BOTH branches execute coherently!
      Output: (│0⟩ H(S|ψ⟩) + │1⟩ S(H|ψ⟩)) / √2
      This is INDEFINITE CAUSAL ORDER!


==========================================================================
  SUMMARY
==========================================================================


┌─────────────────────────────────────────────────────────────────────────┐
│  QSWITCH INSTANTIATION COMPARISON                                       │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  QSwitch[f, f]  (ONE function, f = g):                                  │
│  ─────────────────────────────────────                                  │
│    Simplification: Both branches identical → f ∘ f                      │
│    Control qubit: IRRELEVANT (passes through)                           │
│    Example: QSwitch[H, H] = Identity (H² = I)                           │
│    Gates: 6 (but all cancel to identity)                                │
│                                                                         │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  QSwitch[f, g]  (TWO functions, f ≠ g, non-commuting):                  │
│  ─────────────────────────────────────────────────────                  │
│    Simplification: NONE (f∘g ≠ g∘f)                                     │
│    Control qubit: ESSENTIAL (determines operation order)                │
│    Example: QSwitch[H, S] → genuine quantum switch                      │
│    Gates: 6 (X; CS; CH; X; CH; CS)                                      │
│                                                                         │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  KEY INSIGHT:                                                           │
│    QSwitch is only non-trivial when f and g DON'T commute.             │
│    Commutativity [f,g] = 0  →  QSwitch[f,g] = f∘g (no switch)          │
│    Non-commutativity        →  true indefinite causal order             │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘

