# Coherent ⊕-introduction (`Sum_αβ`): design outline

**Status:** Design outline, filed 2026-08-30. Not yet implemented.

**Motivation.** The formal source calculus contains a coherent ⊕-introduction
rule alongside its ⊕-map rule:

$$
\dfrac{\Gamma_1 \vdash W_1 : A \qquad \Gamma_2 \vdash W_2 : B}
      {\Gamma_1, \Gamma_2 \vdash [W_1 \mid W_2] : A \oplus B}
$$

whose emitter target is a `Block_αβ^sum` (distinct from the `Block_αβ^map`
emitted for `Map_αβ(R_1, R_2) : (A ⊕ B) ⊸ (C ⊕ D)`). The artifact
currently ships the `Map` family end-to-end (`PlusMap`, `NPlusMap`,
`PhasedPlusMap`, `case_hom`, `datatype control`, additive
associativity/symmetry/distributivity) but does not expose a first-class
coherent ⊕-introduction constructor.

**Why Sum is not derivable in the current DSL.** Under the natural
reading, `Sum` is the special case of `Map` where the source type is
tensor unit `I`. Even though the OCaml surface has `val one : [`One] ty`
at the type level, it has **no term-level introduction rule for a
value of type `one`** — grepping the interface shows no
`(unit, [`One]) prog` constructor, no `unit_intro`, no `star`. The
would-be derivation

```
osum α β A B W_1 W_2 split
  = omap0 one one (state_prep_of A W_1) (state_prep_of B W_2)
```

requires `state_prep_of : (Γ, X) oterm → (unit, one ⊸ X) prog`, i.e., a
morphism from `I` to `X`. No such morphism can be built from the current
primitive kit (`var` at type `one` yields identity-shaped
`(one * unit, one) prog`; there is no `one ⊸ Q` or `one ⊸ A` primitive
for any non-`one` A). So Sum is genuinely absent from the shipped
artifact — not merely "not yet exposed as sugar".

---

## Repair outline (agreed 2026-08-30, deferred)

Sum is added to the DSL as its own primitive, and compiled by mirroring
the `Map` emitter with the source side blank (no input tag, no input
payload). All the DSL machinery around Sum — open-term contexts,
context-splitting witnesses, split-driven branch consumption, the
first-order guard on payload types, branch compilation to sub-circuits —
is copied verbatim from the `oplusmap` / `PlusMap` path.

### 1. OCaml surface

New smart constructor mirroring `oplusmap`'s signature, with two changes:
(a) no source-summand types (`'a ty -> 'b ty` in oplusmap becomes the
*output* summand types), and (b) return a **value** type
`[`Plus of 'a * 'b]` rather than a **morphism** type.

```ocaml
val osum : Complex.t -> Complex.t
        -> 'a ty -> 'b ty
        -> ('g1, 'a) oterm -> ('g2, 'b) oterm
        -> ('g1, 'g2, 'g) split
        -> ('g, [`Plus of 'a * 'b]) oterm
```

Compare with `oplusmap`:

```ocaml
val oplusmap : 'a ty -> 'b ty                                  (* A_src, B_src args *)
            -> ('g1, 'c) oterm -> ('g2, 'd) oterm
            -> ('g1, 'g2, 'g) split
            -> ('g, [`Lolli of [`Plus of 'a * 'b]              (* source sum in Lolli *)
                              * [`Plus of 'c * 'd]]) oterm
```

Same context/split/branch plumbing. The `osum` constructor validates
`|α|² + |β|² = 1` and enforces the first-order guard on `'a` and `'b`
(payload types must be first-order).

### 2. Bridge IR

New `TSum` tag carrying `(α, β, ty_left, ty_right, W_1, W_2)`. JSON
encoding parallel to `TPhasedPlusMap`.

### 3. Python term class

```python
@dataclass(frozen=True, slots=True)
class Sum:
    alpha: complex
    beta: complex
    ty_left: Ty      # A
    ty_right: Ty     # B
    left: Term       # W_1 : Γ_1 → A (open, uses Γ_1)
    right: Term      # W_2 : Γ_2 → B (open, uses Γ_2)
```

Structurally parallel to `PhasedPlusMap`, minus the source-summand
type fields.

### 4. Emitter

Essentially `PhasedPlusMap` Strategy A, minus the input-tag anti-control
block. Given output offset `off` for a term of type `Plus(A, B)`:

1. Allocate a fresh tag qubit at position `off`.
2. Prep the tag to `α|0⟩ + β|1⟩` via a one-qubit state-prep unitary
   (Rz-Ry-Rz decomposition from `|0⟩`, or Hadamard + phase if `|α| = |β|`
   simplifies to a phase-only prep).
3. Compile `W_1` as a sub-circuit acting on `Γ_1` wires, producing A
   output at wire positions `off+1 .. off+w(A)`.
4. Anti-control the sub-circuit gates on the tag qubit.
5. Compile `W_2` as a sub-circuit acting on `Γ_2` wires, producing B
   output at wire positions `off+1 .. off+w(B)`.
6. Control the sub-circuit gates on the tag qubit.
7. Output layout: tag at `off`, payload at `off+1 .. off+max(w(A),w(B))`.

The `Γ_1` and `Γ_2` input wires remain in the physical circuit as
resource inputs (per linear typing, they are consumed by W_1 and W_2
respectively — nothing is discarded).

### 5. Design questions to resolve before implementation

- **α, β semantics.** Two options: (i) amplitudes (`|α|²+|β|²=1`,
  general one-qubit state prep, more expressive), or (ii) unit-modulus
  phases (`|α|=|β|=1`, tag prepped via Hadamard + one phase gate,
  simpler emitter, matches the `phased_omap0` idiom). Provisionally lean
  toward (i) amplitudes to match how the paper notation reads.

- **Ancilla allocation story.** The output type `Plus(A, B)` has payload
  width `max(w(A), w(B))` and one tag qubit; the input side has
  `|Γ_1| + |Γ_2|` context wires. Total wire budget of the compiled Sum
  is `|Γ_1| + |Γ_2| + 1 + (any additional ancillas needed)`. Whether the
  existing `compile` allocator handles state-prep-shaped terms (output
  wires > input wires) is worth confirming as the first implementation
  step; if not, a small extension is needed there.

### 6. Tests

- `osum α β A B W_1 W_2` at basis (α=1, β=0) equals the compiled
  circuit for the `inl(W_1)` embedding at the same contexts.
- Similarly (α=0, β=1) → `inr(W_2)`.
- At (α, β) = (1/√2, 1/√2), the output is verifiable via unitary
  equality against a hand-built reference that prepares tag=|+⟩ and
  anti/controlled emits W_1 / W_2.
- Composition with `case_hom` or `omap0` on the sum output round-trips
  identity where expected.

---

**This document records the design agreed in discussion; the
implementation is deferred to a follow-up.** Estimated 1-2 hours of
focused work following the PhasedPlusMap emitter template plus the
above tests.
