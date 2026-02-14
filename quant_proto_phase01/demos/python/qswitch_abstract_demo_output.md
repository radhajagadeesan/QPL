# Abstract QSwitch Demo (Python)

Run with: `PYTHONPATH=src python demos/qswitch_abstract_demo.py`

---

```

==========================================================================
  ABSTRACT QSWITCH (Higher-Order Term)
==========================================================================


==========================================================================
  1. Type Definitions
==========================================================================


TYPE DEFINITIONS:

    Q ⊸ Q       width = 2 (argument wire + result wire)
    Bool        width = 1 (tag qubit)

    Input:  (Q⊸Q) ⊗ (Q⊸Q) ⊗ Bool ⊗ Q   width = 6
    Output: Bool ⊗ Q                     width = 2

Wire layout for input:
    [f_arg | f_res | g_arg | g_res | tag | x]
    [  0   |   1   |   2   |   3   |  4  | 5]


==========================================================================
  2. Abstract QSwitch Term Structure
==========================================================================


The abstract QSwitch has this structure:

    QSwitch =
      let (f, rest) = input in           -- f : Q ⊸ Q
      let (g, rest2) = rest in           -- g : Q ⊸ Q
      let (b, x) = rest2 in              -- b : Bool, x : Q
      case b of
        | Left(u)  => (b, Apply(f, Apply(g, x)))  -- f(g(x)) when b=|0⟩
        | Right(u) => (b, Apply(g, Apply(f, x)))  -- g(f(x)) when b=|1⟩

Note: f and g are FUNCTION VALUES, not gates. They are wire bundles
representing the function's argument-slot and result-slot.


==========================================================================
  3. Building the Abstract QSwitch Term
==========================================================================


After destructuring:
    f     : Q ⊸ Q           width = 2
    rest  : (Q⊸Q) ⊗ Bool ⊗ Q   width = 4
    g     : Q ⊸ Q           width = 2
    rest2 : Bool ⊗ Q         width = 2
    b     : Bool             width = 1
    x     : Q                width = 1


==========================================================================
  4. Instantiation: QSwitch[H, S]
==========================================================================


To instantiate QSwitch with specific gates H and S, we would:

1. Create function values for H and S (as 2-wire bundles)
2. Tensor them with Bool ⊗ Q input
3. Apply the abstract QSwitch

However, for now we use the DIRECT approach from qswitch_term_demo.py:

    QSwitch[H,S] = DistR(I,I,Q) ; Case(I⊗Q, I⊗Q, H;S, S;H)

This bypasses the higher-order structure and builds the instantiated
circuit directly using Case.

QSwitch[H,S] type: (I ⊗ (I ⊕ Q)) → ((I ⊗ Q) ⊕ (I ⊗ Q))

Compiled circuit (6 gates):
  X q[0];
  CH q[0], q[1];
  CS q[0], q[1];
  X q[0];
  CS q[0], q[1];
  CH q[0], q[1];

==========================================================================
  5. Summary
==========================================================================


┌────────────────────────────────────────────────────────────────────────┐
│  ABSTRACT QSWITCH                                                      │
├────────────────────────────────────────────────────────────────────────┤
│                                                                        │
│  TYPE:                                                                 │
│    QSwitch : (Q⊸Q) ⊗ (Q⊸Q) ⊗ Bool ⊗ Q → Bool ⊗ Q                     │
│                                                                        │
│  WIRE LAYOUT:                                                          │
│    Input:  [f_arg | f_res | g_arg | g_res | tag | x]  (6 wires)       │
│    Output: [tag | x']  (2 wires)                                       │
│                                                                        │
│  SEMANTICS:                                                            │
│    |0⟩|ψ⟩ → |0⟩(f∘g)(ψ)                                               │
│    |1⟩|ψ⟩ → |1⟩(g∘f)(ψ)                                               │
│                                                                        │
│  KEY INSIGHT:                                                          │
│    Functions f, g are WIRE BUNDLES (Q ⊗ Q wires each).                │
│    LetPair destructures input to bind f, g, b, x to wire ranges.      │
│    Apply connects wires (boundary splicing).                           │
│    Case branches on tag with coherent quantum control.                 │
│                                                                        │
│  INSTANTIATION:                                                        │
│    QSwitch[H, S] → X[0]; CH; CS; X[0]; CS; CH                         │
│    QSwitch[X, Z] → X[0]; CX; CZ; X[0]; CZ; CX                         │
│                                                                        │
└────────────────────────────────────────────────────────────────────────┘


==========================================================================
  DEMO COMPLETE
==========================================================================
```
