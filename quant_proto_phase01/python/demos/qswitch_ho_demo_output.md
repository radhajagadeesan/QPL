# QSwitch Higher-Order Demo (OCaml)

Run with: `cd ocaml && dune exec demos/qswitch_ho_demo.exe`

---

```

==========================================================================
  QSWITCH AS A HIGHER-ORDER FUNCTION
==========================================================================

==========================================================================
  PART 1: Type Definitions
==========================================================================

QSwitch type:
  ((Q → Q) → ((Q → Q) → (((I + I) ⊗ Q) → ((I + I) ⊗ Q))))

Expanded:
  QSwitch : (Q → Q) → (Q → Q) → ((I + I) ⊗ Q → (I + I) ⊗ Q)

In words:
  QSwitch takes two single-qubit operations f and g,
  and returns a circuit on (control ⊗ target) that applies
  f;g when control=|0⟩ and g;f when control=|1⟩.

==========================================================================
  PART 2: Abstract QSwitch Definition
==========================================================================
Abstract QSwitch (conceptually):

  QSwitch = λf:(Q→Q). λg:(Q→Q). λx:(Bool⊗Q).
              let (ctrl ⊗ tgt) = x in
                case ctrl of
                  | Left(u)  => f ; g   (* apply f then g *)
                  | Right(u) => g ; f   (* apply g then f *)

When we instantiate f=H and g=S:

  QSwitch H S = λx:(Bool⊗Q).
                  let (ctrl ⊗ tgt) = x in
                    case ctrl of
                      | Left(u)  => H[1] ; S[1]
                      | Right(u) => S[1] ; H[1]

==========================================================================
  PART 3: Building QSwitch[H, S]
==========================================================================

QSwitch[H,S] term:
  λx:((I + I) ⊗ Q). let (ctrl ⊗ tgt) : (I + I) ⊗ Q = x in case ctrl of Left(u) => H[1] ; S[1] | Right(u) => S[1] ; H[1]

Applied to identity (triggers elaboration):
  (λx:((I + I) ⊗ Q). let (ctrl ⊗ tgt) : (I + I) ⊗ Q = x in case ctrl of Left(u) => H[1] ; S[1] | Right(u) => S[1] ; H[1] id[((I + I) ⊗ Q)])

==========================================================================
  PART 4: Elaboration to Core IR
==========================================================================

Elaborated Core IR:
  id[((I + I) ⊗ Q)] ; X[0] ; C0-H[1] ; C0-S[1] ; X[0] ; C0-S[1] ; C0-H[1]

Explanation:
  - λ and let-tensor are eliminated (β-reduction, offset tracking)
  - case ctrl of ... becomes anti-controlled + controlled gates
  - X[0] flips the tag for anti-control pattern

==========================================================================
  PART 5: Other Instantiations
==========================================================================
The same abstract QSwitch can be instantiated differently:

QSwitch[X, Z]:
  id[((I + I) ⊗ Q)] ; X[0] ; C0-X[1] ; C0-Z[1] ; X[0] ; C0-Z[1] ; C0-X[1]

QSwitch[H;T, S]:
  id[((I + I) ⊗ Q)] ; X[0] ; C0-H[1] ; C0-T[1] ; C0-S[1] ; X[0] ; C0-S[1] ; C0-H[1] ; C0-T[1]


==========================================================================
  SUMMARY
==========================================================================

┌────────────────────────────────────────────────────────────────────────┐
│  HIGHER-ORDER QSWITCH                                                  │
├────────────────────────────────────────────────────────────────────────┤
│                                                                        │
│  TYPE:    QSwitch : (Q→Q) → (Q→Q) → (Bool⊗Q → Bool⊗Q)                 │
│                                                                        │
│  MEANING: Takes two single-qubit operations f, g                       │
│           Returns a circuit that applies them in superposition         │
│           of orderings: f;g when ctrl=0, g;f when ctrl=1               │
│                                                                        │
│  INSTANTIATION:                                                        │
│           QSwitch H S → X[0]; CH; CS; X[0]; CS; CH                    │
│           QSwitch X Z → X[0]; CX; CZ; X[0]; CZ; CX                    │
│                                                                        │
│  KEY INSIGHT:                                                          │
│           Higher-order in the surface language                         │
│           First-order in the compiled circuit                          │
│           λ and App elaborate away via β-reduction                     │
│                                                                        │
└────────────────────────────────────────────────────────────────────────┘


==========================================================================
  DEMO COMPLETE
==========================================================================
```
