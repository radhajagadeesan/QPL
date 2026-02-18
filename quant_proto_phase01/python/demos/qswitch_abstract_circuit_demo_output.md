
==========================================================================
  ABSTRACT QSWITCH - Pure Higher-Order Structure
==========================================================================


TYPE SIGNATURE (Curried Form):
──────────────────────────────

    QSwitch : Bool ⊸ (A ⊸ A) ⊸ (A ⊸ A) ⊸ A ⊸ (Bool ⊗ A)

    Where:
      A ⊸ A  = linear function type, width = 2 wires
      Bool   = I + I (sum type), width = 1 wire
      A      = single qubit, width = 1 wire
      Bool⊗A = output pair, width = 2 wires

    Total width: 8 wires

    Note: Bool appears in BOTH input and output!
    The control qubit is not consumed — it passes through.


==========================================================================
  1. Wire Layout (Curried Form)
==========================================================================


For the curried type:  Bool ⊸ (A ⊸ A) ⊸ (A ⊸ A) ⊸ A ⊸ (Bool ⊗ A)

Each lambda exposes its argument wires in order:

INPUT WIRES (6 total):
──────────────────────

    ┌─────────────────────────────────────────────────────────────────┐
    │                                                                 │
    │  Wire 0  │  Wire 1   Wire 2  │  Wire 3   Wire 4  │   Wire 5    │
    │ ┌──────┐ │ ┌──────┬────────┐ │ ┌──────┬────────┐ │ ┌────────┐  │
    │ │  b   │ │ │f_arg │ f_res  │ │ │g_arg │ g_res  │ │ │   x    │  │
    │ └──────┘ │ └──────┴────────┘ │ └──────┴────────┘ │ └────────┘  │
    │   Bool   │      A ⊸ A        │      A ⊸ A        │     A       │
    │   (λb)   │      (λf)         │      (λg)         │    (λx)     │
    │                                                                 │
    └─────────────────────────────────────────────────────────────────┘

    Layout follows lambda nesting (outermost first):
      • b occupies wire  [0]     — control qubit
      • f occupies wires [1, 2]  — first function bundle
      • g occupies wires [3, 4]  — second function bundle
      • x occupies wire  [5]     — target qubit

    Functions are WIRE BUNDLES:  A ⊸ B  ≅  A* ⊗ B  ≅  A ⊗ B  (self-dual)


OUTPUT WIRES (2 total):
───────────────────────

    ┌─────────────────────────────────────────────────────────────────┐
    │                                                                 │
    │                                       Wire 6       Wire 7      │
    │                                     ┌───────────┬────────────┐ │
    │                                     │    b'     │   result   │ │
    │                                     └───────────┴────────────┘ │
    │                                          Bool ⊗ A              │
    │                                                                 │
    └─────────────────────────────────────────────────────────────────┘

    The control qubit b passes through to the output!


==========================================================================
  2. Abstract Term Structure
==========================================================================


QSWITCH AS A TERM (Curried Form):
─────────────────────────────────

    QSwitch = λb. λf. λg. λx. case b of
                | Left(u)  ⇒ (Left(u), f(g(x)))
                | Right(u) ⇒ (Right(u), g(f(x)))

    Where:
      b : Bool        (control qubit)
      f : A ⊸ A       (first function)
      g : A ⊸ A       (second function)
      x : A           (target)


TYPE:
─────

    QSwitch : Bool ⊸ (A ⊸ A) ⊸ (A ⊸ A) ⊸ A ⊸ (Bool ⊗ A)

    Note: Bool appears in BOTH input and output!
    The control qubit passes through — it's not consumed.


SEMANTICS:
──────────

    │0⟩ f g ψ  ↦  │0⟩ ⊗ f(g(ψ))        (g first, then f)
    │1⟩ f g ψ  ↦  │1⟩ ⊗ g(f(ψ))        (f first, then g)
    │+⟩ f g ψ  ↦  (│0⟩⊗f(g(ψ)) + │1⟩⊗g(f(ψ))) / √2
                   SUPERPOSITION of causal orders!


LINEARITY:
──────────

    Each variable is used exactly once:
      • b — consumed by case, reconstructed as Left(u)/Right(u) in output
      • f — used once in each branch (f(g(x)) or f(x))
      • g — used once in each branch (g(x) or g(f(x)))
      • x — used once (passed to first function in chain)
      • u — unit payload, width 0


==========================================================================
  3. Abstract Circuit Diagram
==========================================================================


ABSTRACT QSWITCH CIRCUIT (Curried Wire Layout):
───────────────────────────────────────────────

    b     (0) ────┬─────────────────────────────────────────────────────────┬─── b'
                  │                                                         │
    f_arg (1) ════╪═════════════════════════════════════════════════════╗   │
                  │                                                     ║   │
    f_res (2) ════╪═════════════════════════════════════════════════════╬═══╪═══╗
                  │                                                     ║   │   ║
    g_arg (3) ════╪═════════════════════════════════════════════════╗   ║   │   ║
                  │                                                 ║   ║   │   ║
    g_res (4) ════╪═════════════════════════════════════════════════╬═══╬═══╪═══╬═══╗
                  │                                                 ║   ║   │   ║   ║
                  └─────────────────────────────────────────────────╨───╨───┼───╨───╨──┐
                                        QUANTUM CASE                        │          │
                                                                            │          │
                    │0⟩: route  x → g_arg → g_res → f_arg → f_res → result │          │
                    │1⟩: route  x → f_arg → f_res → g_arg → g_res → result │          │
                                                                            │          │
                  ┌─────────────────────────────────────────────────────────┘          │
    x     (5) ────┴────────────────────────────────────────────────────────────────────┴─── result


    Legend:
      ════  Function wires (routed differently based on b)
      ────  Data wires (b passes through, x is transformed)


==========================================================================
  4. Routing per Branch
==========================================================================


BRANCH Left (b = │0⟩): Apply g then f
──────────────────────────────────────

    Wiring: x → g_arg,  g_res → f_arg,  f_res → result

    ┌─────────────────────────────────────────────────────────────────┐
    │                                                                 │
    │   b     (0) ────────────────────────────────────────→ b'        │
    │                                                                 │
    │   f_arg (1) ←───────────────────────────┐                       │
    │                                         │                       │
    │   f_res (2) ────────────────────────────┼───────────→ result    │
    │                                         │                       │
    │   g_arg (3) ←───────────┐               │                       │
    │                         │               │                       │
    │   g_res (4) ────────────┼───────────────┘                       │
    │                         │                                       │
    │   x     (5) ────────────┘                                       │
    │                                                                 │
    │   Flow: x ──→ [g] ──→ [f] ──→ result                           │
    │                                                                 │
    └─────────────────────────────────────────────────────────────────┘


BRANCH Right (b = │1⟩): Apply f then g
───────────────────────────────────────

    Wiring: x → f_arg,  f_res → g_arg,  g_res → result

    ┌─────────────────────────────────────────────────────────────────┐
    │                                                                 │
    │   b     (0) ────────────────────────────────────────→ b'        │
    │                                                                 │
    │   f_arg (1) ←───────────┐                                       │
    │                         │                                       │
    │   f_res (2) ────────────┼───────────────┐                       │
    │                         │               │                       │
    │   g_arg (3) ←───────────┼───────────────┘                       │
    │                         │                                       │
    │   g_res (4) ────────────┼───────────────────────────→ result    │
    │                         │                                       │
    │   x     (5) ────────────┘                                       │
    │                                                                 │
    │   Flow: x ──→ [f] ──→ [g] ──→ result                           │
    │                                                                 │
    └─────────────────────────────────────────────────────────────────┘


==========================================================================
  5. The Quantum CASE Circuit
==========================================================================


CASE STRUCTURE:
───────────────

    Case : (A + B) → (C + D)

    Input:  sum type with tag qubit
    Output: sum type, tag preserved

    │tag⟩ = │0⟩  :  apply LEFT routing
    │tag⟩ = │1⟩  :  apply RIGHT routing
    │tag⟩ = │+⟩  :  BOTH routings in superposition!


ANTI-CONTROL PATTERN:
─────────────────────

    Standard controlled operations fire when control = │1⟩.
    But LEFT branch must fire when control = │0⟩!

    Solution: X-gate sandwich (anti-control pattern)

    ┌─────────────────────────────────────────────────────────────────┐
    │                                                                 │
    │  ANTI-CONTROLLED OPERATION: fires when control = │0⟩            │
    │                                                                 │
    │      ctrl ───X───●───X───          Equivalent to:               │
    │              │   │   │                                          │
    │      tgt  ───────R───────          "Route R when ctrl = │0⟩"    │
    │                                                                 │
    │  How it works:                                                  │
    │    1. X flips ctrl:  │0⟩ → │1⟩,  │1⟩ → │0⟩                     │
    │    2. Controlled-R:  fires when ctrl = │1⟩ (original │0⟩)      │
    │    3. X restores:    │1⟩ → │0⟩,  │0⟩ → │1⟩                     │
    │                                                                 │
    │  Net effect: R applied iff original ctrl was │0⟩                │
    │                                                                 │
    └─────────────────────────────────────────────────────────────────┘


CASE COMPILATION STRUCTURE:
───────────────────────────

    ┌─────────────────────────────────────────────────────────────────┐
    │                                                                 │
    │   ctrl ───X───●─────────────X───●─────────────                  │
    │           │   │             │   │                               │
    │           │   │ LEFT        │   │ RIGHT                         │
    │           │   │ routing     │   │ routing                       │
    │           │   │             │   │                               │
    │   wires ──────┴─────────────────┴─────────────                  │
    │                                                                 │
    │           └─────────────┘   └─────────────┘                     │
    │            anti-control       control                           │
    │            (fires on 0)      (fires on 1)                       │
    │                                                                 │
    └─────────────────────────────────────────────────────────────────┘


COHERENCE PRESERVATION:
───────────────────────

    The X-gate trick preserves quantum coherence because:

    • X is self-inverse: X² = I
    • X│+⟩ = │+⟩  (superposition unchanged!)
    • Both branches execute coherently on superposition input

    For │+⟩ input:
      X creates temporary basis change, doesn't collapse superposition.
      Both routings happen simultaneously in different branches of
      the quantum state.


==========================================================================
  6. Function Application (Abstract)
==========================================================================


APPLY OPERATION:
────────────────

    Apply(f, x) where f : A ⊸ B and x : A

    In our wire-bundle encoding:
      • f is represented as wires [f_arg │ f_res]
      • x is a value on some wire(s)

    Apply CONNECTS:
      • x → f_arg    (feed input to function's argument slot)
      • f_res → out  (function's result slot becomes output)

    ┌─────────────────────────────────────────────────────────────────┐
    │                                                                 │
    │  Before Apply:           After Apply:                           │
    │                                                                 │
    │  f_arg ─────────         x ──────┐                              │
    │                                  │                              │
    │  f_res ─────────                 ▼                              │
    │                          f_arg ──┴── f_res ──→ output           │
    │  x     ─────────                                                │
    │                          (wires connected/identified)           │
    │                                                                 │
    └─────────────────────────────────────────────────────────────────┘

    Apply is PURE WIRING - no gates, just wire identification.


NESTED APPLICATION f(g(x)):
───────────────────────────

    ┌─────────────────────────────────────────────────────────────────┐
    │                                                                 │
    │  x ─────────→ g_arg                                             │
    │                                                                 │
    │               g_res ─────────→ f_arg                            │
    │                                                                 │
    │                                 f_res ─────────→ output         │
    │                                                                 │
    │  Flow: x ──→ [g] ──→ [f] ──→ output                            │
    │                                                                 │
    └─────────────────────────────────────────────────────────────────┘


==========================================================================
  7. Type Verification
==========================================================================


Verifying that computed types match the diagrams above:

  Bool = I + I                    width = 1  (claimed: 1) ✓
  A = Q                           width = 1  (claimed: 1) ✓
  A ⊸ A                           width = 2  (claimed: 2) ✓
  Bool ⊗ A                        width = 2  (claimed: 2) ✓
  Full curried type               width = 8  (claimed: 8) ✓

  Input wires: 1 + 2 + 2 + 1 = 6  (claimed: 6) ✓
  Output wires: 2  (claimed: 2) ✓

  ✓ ALL TYPE WIDTHS VERIFIED - diagrams match computed types

==========================================================================
  SUMMARY
==========================================================================


┌─────────────────────────────────────────────────────────────────────────┐
│                                                                         │
│  ABSTRACT QSWITCH (Curried Form)                                       │
│                                                                         │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  TERM:                                                                  │
│      QSwitch = λb. λf. λg. λx. case b of                               │
│                  | Left(u)  ⇒ (Left(u), f(g(x)))                       │
│                  | Right(u) ⇒ (Right(u), g(f(x)))                      │
│                                                                         │
│  TYPE:                                                                  │
│      QSwitch : Bool ⊸ (A ⊸ A) ⊸ (A ⊸ A) ⊸ A ⊸ (Bool ⊗ A)             │
│                                                                         │
│  WIRES (8 total):                                                       │
│      Input:  [b│f_arg│f_res│g_arg│g_res│x]  (6 wires from lambdas)     │
│      Output: [b'│result]                     (2 wires)                  │
│                                                                         │
│  SEMANTICS:                                                             │
│      │0⟩ f g ψ  ↦  │0⟩ f(g(ψ))      (g then f)                         │
│      │1⟩ f g ψ  ↦  │1⟩ g(f(ψ))      (f then g)                         │
│      │+⟩ f g ψ  ↦  entangled superposition of both orders!             │
│                                                                         │
│  STRUCTURE:                                                             │
│      • b passes through (not consumed, appears in output)              │
│      • f, g are WIRE BUNDLES (2 wires each)                            │
│      • Case branches on b with coherent quantum control                │
│      • Apply connects wires (pure routing, no gates)                   │
│      • Anti-control pattern: X-sandwich for Left branch                │
│                                                                         │
│  KEY INSIGHT:                                                           │
│      The abstract QSwitch is pure ROUTING + CONTROL structure.         │
│      It defines HOW to compose f and g based on b,                     │
│      without specifying WHAT f and g are.                              │
│                                                                         │
│      This is INDEFINITE CAUSAL ORDER as a circuit primitive.           │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘

