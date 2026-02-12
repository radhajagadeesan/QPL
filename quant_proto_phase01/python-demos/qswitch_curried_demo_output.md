
==========================================================================
  QSWITCH CURRIED TYPE DERIVATION
==========================================================================


We want to derive the type of:

    QSwitch = λb. λf. λg. λx. case b of
                | Left(u)  => (Left(u), f(g(x)))
                | Right(u) => (Right(u), g(f(x)))

Working inside-out...


==========================================================================
  1. TYPING THE BRANCHES
==========================================================================


In the Left branch, we have in scope:
    u : I           (payload from Left)
    x : A           (from λx)
    f : A ⊸ A       (from λf)
    g : A ⊸ A       (from λg)

Derivation:
    ─────────────────────────────────────
    x : A
    ─────────────────────────────────────  (App)
    g(x) : A
    ─────────────────────────────────────  (App)
    f(g(x)) : A
    ─────────────────────────────────────  (Inj-L)
    Left(u) : I + I = Bool
    ─────────────────────────────────────  (Pair)
    (Left(u), f(g(x))) : Bool ⊗ A


Similarly, Right branch:
    ─────────────────────────────────────
    (Right(u), g(f(x))) : Bool ⊗ A

Both branches have the same type: Bool ⊗ A  ✓


==========================================================================
  2. TYPING THE CASE
==========================================================================


The case expression:

    b : Bool
    ───────────────────────────────────────────────────────────
    Left branch  : Bool ⊗ A    (consuming u : I from b)
    Right branch : Bool ⊗ A    (consuming u : I from b)
    ───────────────────────────────────────────────────────────
    case b of Left(u) => ... | Right(u) => ...  :  Bool ⊗ A


LINEARITY CHECK:
    • b is consumed by the case (its tag controls the branches)
    • u : I has width 0 (unit payload)
    • Left(u)/Right(u) reconstructs a Bool in output
    • The tag qubit "passes through" — not duplicated!


==========================================================================
  3. BUILDING UP THE LAMBDAS
==========================================================================

Types we'll use:
    A = Q                      width = 1
    Bool = I + I               width = 1
    A ⊸ A                      width = 2
    Bool ⊗ A                   width = 2

Lambda abstraction (inside-out):

    λx. case b of ...          : A ⊸ (Bool ⊗ A)
                                 width = 3
                                 (uses b, f, g from outer scope)

    λg. λx. case b of ...      : (A ⊸ A) ⊸ A ⊸ (Bool ⊗ A)
                                 width = 5
                                 (uses b, f from outer scope)

    λf. λg. λx. case b of ...  : (A ⊸ A) ⊸ (A ⊸ A) ⊸ A ⊸ (Bool ⊗ A)
                                 width = 7
                                 (uses b from outer scope)

    λb. λf. λg. λx. case ...   : Bool ⊸ (A ⊸ A) ⊸ (A ⊸ A) ⊸ A ⊸ (Bool ⊗ A)
                                 width = 8


==========================================================================
  4. THE FULL TYPE
==========================================================================


┌─────────────────────────────────────────────────────────────────────────┐
│                                                                         │
│  QSwitch : Bool ⊸ (A ⊸ A) ⊸ (A ⊸ A) ⊸ A ⊸ (Bool ⊗ A)                 │
│                                                                         │
│  Or with explicit parentheses (⊸ is right-associative):                │
│                                                                         │
│  QSwitch : Bool ⊸ ((A ⊸ A) ⊸ ((A ⊸ A) ⊸ (A ⊸ (Bool ⊗ A))))           │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘

Total width: 8 wires


==========================================================================
  5. WIRE LAYOUT
==========================================================================


Since A ⊸ B has width = width(A) + width(B), we can compute the wire layout.

For A = Q:
    • Bool    = 1 wire   (tag qubit)
    • A ⊸ A   = 2 wires  (argument slot + result slot)
    • A       = 1 wire   (target qubit)
    • Bool⊗A  = 2 wires  (output tag + output value)

Full layout (8 wires):

    INPUT SIDE (exposed by lambdas):
    ┌─────────────────────────────────────────────────────────────────┐
    │  Wire 0   │  Wire 1   Wire 2  │  Wire 3   Wire 4  │   Wire 5   │
    │ ┌───────┐ │ ┌───────┬───────┐ │ ┌───────┬───────┐ │ ┌────────┐ │
    │ │   b   │ │ │ f_arg │ f_res │ │ │ g_arg │ g_res │ │ │   x    │ │
    │ └───────┘ │ └───────┴───────┘ │ └───────┴───────┘ │ └────────┘ │
    │   Bool    │      A ⊸ A        │      A ⊸ A        │     A      │
    └─────────────────────────────────────────────────────────────────┘

    OUTPUT SIDE (result of computation):
    ┌─────────────────────────────────────────────────────────────────┐
    │                                       Wire 6       Wire 7      │
    │                                     ┌───────────┬────────────┐ │
    │                                     │   ctrl'   │   result   │ │
    │                                     └───────────┴────────────┘ │
    │                                          Bool ⊗ A              │
    └─────────────────────────────────────────────────────────────────┘


==========================================================================
  6. COMPARISON WITH TENSORED VERSION
==========================================================================

The tensored version from earlier:

    QSwitch : (A ⊸ A) ⊗ (A ⊸ A) ⊗ Bool ⊗ A  →  Bool ⊗ A

    Input width:  6
    Output width: 2
    Total width:  8

The curried version:

    QSwitch : Bool ⊸ (A ⊸ A) ⊸ (A ⊸ A) ⊸ A ⊸ (Bool ⊗ A)

    Total width:  8


Both have 8 wires total! This is the currying isomorphism at work:

    A ⊸ B ⊸ C  ≅  A ⊗ B ⊸ C

The difference is just in how we group the inputs:
    • Curried:  each λ exposes its argument wires sequentially
    • Tensored: all inputs arrive as one big tensor product


==========================================================================
  7. LINEARITY VERIFICATION
==========================================================================


Let's verify each variable is used exactly once:

    λb. λf. λg. λx. case b of
      | Left(u)  => (Left(u), f(g(x)))
      | Right(u) => (Right(u), g(f(x)))

Variable usage:
    ┌──────────┬───────────────────────────────────────────────────────┐
    │ Variable │ Usage                                                 │
    ├──────────┼───────────────────────────────────────────────────────┤
    │ b        │ Consumed by case (tag qubit controls branch)         │
    │ u        │ Used once in Left(u) or Right(u) — width 0 anyway    │
    │ f        │ Used once: f(g(x)) in Left, f(x) in Right            │
    │ g        │ Used once: g(x) in Left, g(f(x)) in Right            │
    │ x        │ Used once: passed to g in Left, to f in Right        │
    └──────────┴───────────────────────────────────────────────────────┘

QUANTUM SUBTLETY:
    In superposition (b = |+⟩), both branches execute coherently!

    But this is OK because:
    • f and g are WIRE BUNDLES, not classical functions
    • The routing (which wires connect) is controlled by b
    • In superposition, both routings happen simultaneously
    • This is exactly "indefinite causal order"


==========================================================================
  8. SEMANTIC VERIFICATION
==========================================================================


Let's trace the semantics for different inputs:

CASE 1: b = |0⟩ (Left)
────────────────────────
    Input:  |0⟩ |f⟩ |g⟩ |ψ⟩

    case |0⟩ of Left(u) => (Left(u), f(g(ψ)))

    Output: |0⟩ |f(g(ψ))⟩

    (Control passes through, operations applied as g then f)


CASE 2: b = |1⟩ (Right)
─────────────────────────
    Input:  |1⟩ |f⟩ |g⟩ |ψ⟩

    case |1⟩ of Right(u) => (Right(u), g(f(ψ)))

    Output: |1⟩ |g(f(ψ))⟩

    (Control passes through, operations applied as f then g)


CASE 3: b = |+⟩ (Superposition)
────────────────────────────────
    Input:  |+⟩ |f⟩ |g⟩ |ψ⟩  =  (|0⟩ + |1⟩)/√2 |f⟩ |g⟩ |ψ⟩

    BOTH branches execute coherently!

    Output: (|0⟩|f(g(ψ))⟩ + |1⟩|g(f(ψ))⟩) / √2

    The control qubit is now ENTANGLED with which order was applied.
    This is INDEFINITE CAUSAL ORDER!


==========================================================================
  SUMMARY
==========================================================================


┌─────────────────────────────────────────────────────────────────────────┐
│                                                                         │
│  QSwitch = λb. λf. λg. λx. case b of                                   │
│              | Left(u)  => (Left(u), f(g(x)))                          │
│              | Right(u) => (Right(u), g(f(x)))                         │
│                                                                         │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  TYPE:  Bool ⊸ (A ⊸ A) ⊸ (A ⊸ A) ⊸ A ⊸ (Bool ⊗ A)                    │
│                                                                         │
│  WIDTH: 8 wires total (same as tensored version)                       │
│                                                                         │
│  SEMANTICS:                                                             │
│    |0⟩ f g ψ  ↦  |0⟩ f(g(ψ))        (g then f)                         │
│    |1⟩ f g ψ  ↦  |1⟩ g(f(ψ))        (f then g)                         │
│    |+⟩ f g ψ  ↦  entangled!         (indefinite causal order)          │
│                                                                         │
│  LINEARITY: ✓ All variables used exactly once                          │
│                                                                         │
│  KEY INSIGHT:                                                           │
│    The control qubit b appears in BOTH input and output.               │
│    It's not consumed — it passes through and becomes entangled         │
│    with the result. This preserves quantum information.                │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘

