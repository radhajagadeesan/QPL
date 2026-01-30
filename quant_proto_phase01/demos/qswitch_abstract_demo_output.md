# QSwitch Abstract Demo Output

Run with: `PYTHONPATH=src python demos/qswitch_abstract_demo.py`

---

```

======================================================================
  QSWITCH WITH ABSTRACT FUNCTION ARGUMENTS
======================================================================


TYPE SIGNATURE:

    QSwitch : Bool ⊗ Q ⊗ (Q→Q) ⊗ (Q→Q) → Bool ⊗ Q

TYPE ENCODINGS:

    Bool   = I + I           width = 1 (log-tag encoding)
    Q→Q    ≡ Q* ⊗ Q ≡ Q ⊗ Q  width = 2 (self-dual)

    Input  = Bool ⊗ Q ⊗ (Q→Q) ⊗ (Q→Q)
           = (I+I) ⊗ Q ⊗ (Q⊗Q) ⊗ (Q⊗Q)
           width = 6

    Output = Bool ⊗ Q
           width = 2


======================================================================
  1. Wire Layout
======================================================================


INPUT WIRES (6 total):

    ┌─────────────────────────────────────────────────────────┐
    │  Wire 0: ctrl (Bool tag)     ─── control qubit          │
    │  Wire 1: tgt  (Q)            ─── target qubit           │
    │  Wire 2: f.in (Q)            ─┐                         │
    │  Wire 3: f.out (Q)           ─┴─ function f : Q → Q     │
    │  Wire 4: g.in (Q)            ─┐                         │
    │  Wire 5: g.out (Q)           ─┴─ function g : Q → Q     │
    └─────────────────────────────────────────────────────────┘

OUTPUT WIRES (2 total):

    ┌─────────────────────────────────────────────────────────┐
    │  Wire 0: ctrl (Bool tag)     ─── passed through         │
    │  Wire 1: result (Q)          ─── f;g(tgt) or g;f(tgt)   │
    └─────────────────────────────────────────────────────────┘

FUNCTION ENCODING:

    A function f : Q → Q is represented as 2 wires:

        f.in  ●───[ f ]───● f.out

    "Applying" f to x means connecting x to f.in via Cap,
    then f.out becomes the result.


======================================================================
  2. QSwitch Semantics
======================================================================


SEMANTICS:

    QSwitch (ctrl, tgt, f, g) =
        case ctrl of
        | Left  → (ctrl, (f ; g)(tgt))    -- apply f then g
        | Right → (ctrl, (g ; f)(tgt))    -- apply g then f

WIRE ROUTING:

    When ctrl = |0⟩ (Left):

        tgt ──●                      ●── result
              │                      │
              └──→ f.in   f.out ──→ g.in   g.out ──┘

        Route: tgt → f → g → result

    When ctrl = |1⟩ (Right):

        tgt ──●                      ●── result
              │                      │
              └──→ g.in   g.out ──→ f.in   f.out ──┘

        Route: tgt → g → f → result

    When ctrl = superposition:

        Both routes execute coherently!
        The target qubit is routed through BOTH orderings simultaneously.


======================================================================
  3. Building the Term
======================================================================


In our linear λ-calculus, QSwitch is built using:

    λ(ctrl, tgt, f, g).
        let (ctrl', tgt') = case ctrl of
            | Left  → Cap(g) ∘ Cap(f) ∘ (tgt, f, g)   -- f;g
            | Right → Cap(f) ∘ Cap(g) ∘ (tgt, g, f)   -- g;f
        in (ctrl', tgt')

Where Cap connects a value to a function's input wire:

    Cap : Q* ⊗ Q → I

    Applying f to x:  Cap(f.in, x) produces f.out as result

Term components:
  f = FunVar('f', Q, Q)  -- represents f : Q → Q
  g = FunVar('g', Q, Q)  -- represents g : Q → Q


======================================================================
  4. Instantiation: QSwitch(ctrl, tgt, H, S)
======================================================================


When we instantiate f = H and g = S, the abstract wires become concrete gates:

    f.in ──[ H ]── f.out    becomes    ──[ H ]──
    g.in ──[ S ]── g.out    becomes    ──[ S ]──

The controlled routing becomes controlled gates:

    case ctrl of Left → H;S | Right → S;H

    ═══════════════════════════════════════════════════════

    X[ctrl]; CH[ctrl,tgt]; CS[ctrl,tgt]; X[ctrl]; CS[ctrl,tgt]; CH[ctrl,tgt]
    ─────────────────────────────────────  ─────────────────────────────────
           anti-controlled (H;S)                  controlled (S;H)

Instantiated circuit (f=H, g=S):
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

    ctrl ──X───●───●───X───●───●──
               │   │       │   │
    tgt  ─────CH──CS──────CS──CH──


======================================================================
  5. The Higher-Order Insight
======================================================================


┌──────────────────────────────────────────────────────────────────────┐
│  ABSTRACT vs INSTANTIATED                                            │
├──────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ABSTRACT (with f, g as parameters):                                 │
│                                                                      │
│      QSwitch : Bool ⊗ Q ⊗ (Q→Q) ⊗ (Q→Q) → Bool ⊗ Q                  │
│                                                                      │
│      Input: 6 wires (ctrl, tgt, f.in, f.out, g.in, g.out)           │
│      The circuit conditionally ROUTES through f or g                 │
│                                                                      │
│  INSTANTIATED (f=H, g=S):                                            │
│                                                                      │
│      QSwitch[H,S] : Bool ⊗ Q → Bool ⊗ Q                              │
│                                                                      │
│      Input: 2 wires (ctrl, tgt)                                      │
│      The circuit uses CONTROLLED GATES (CH, CS)                      │
│                                                                      │
├──────────────────────────────────────────────────────────────────────┤
│  KEY INSIGHT:                                                        │
│                                                                      │
│  In the abstract version, functions ARE wires.                       │
│  "Applying" a function = connecting wires via Cap.                   │
│  "Controlled apply" = controlled wire routing.                       │
│                                                                      │
│  At instantiation, abstract wires become concrete gates,             │
│  and controlled routing becomes controlled gates.                    │
└──────────────────────────────────────────────────────────────────────┘


======================================================================
  6. Type-Level View
======================================================================


The curried type signature with Bool outermost:

    QSwitch : Bool → Q → (Q→Q) → (Q→Q) → Bool ⊗ Q

Uncurrying (how we encode it):

    QSwitch : Bool ⊗ Q ⊗ (Q→Q) ⊗ (Q→Q) → Bool ⊗ Q

Partial application sequence:

    QSwitch                     : Bool⊗Q⊗(Q→Q)⊗(Q→Q) → Bool⊗Q
    QSwitch |0⟩                 : Q⊗(Q→Q)⊗(Q→Q) → Bool⊗Q
    QSwitch |0⟩ |ψ⟩             : (Q→Q)⊗(Q→Q) → Bool⊗Q
    QSwitch |0⟩ |ψ⟩ H           : (Q→Q) → Bool⊗Q
    QSwitch |0⟩ |ψ⟩ H S         : Bool⊗Q                   (result!)

Wire consumption:

    Start with 6 wires: [ctrl, tgt, f.in, f.out, g.in, g.out]
    After routing:      [ctrl, result]  (2 wires)

    The f and g wires are "consumed" by application (Cap).

```
