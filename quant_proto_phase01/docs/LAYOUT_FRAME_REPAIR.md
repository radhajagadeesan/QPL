# Layout-frame repair: gate-free distributivity for all four distributors

**Status:** Implemented in the boundary-frame / Align round. Filed as a design
outline 2026-08-30; superseded by this record of what was actually built.

The original note argued the case for `dist_l` only and left the composition
side deferred, with `demos/dist_l_naturality_probe` (full-unitary fidelity 0.5)
as the standing witness. That witness now passes exactly, and the repair covers
`DistL`, `DistR`, `UndistL` and `UndistR` uniformly.

**Central invariant.** A judgment type determines the semantic boundary space,
but does not uniquely determine its physical embedding. The derivation selects
the boundary frames; mismatched frames are reconciled at the splice by Align,
never by changing the source type or the example.

---

## 1. What a frame is

`Frame` is an exact embedding, not a hint:

| field | meaning |
|---|---|
| `logical` | the interface type |
| `n_qubits` | physical register width |
| `codes` | `codes[k]` is the physical basis index of the k-th semantic label |
| `expr` | the symbolic construction, validated against `codes` |
| `sectors` | per-summand code sets and the **set** of tag words each spans |
| `ports` | sub-interface placements, possibly **sector-conditioned** |

`Compiled` carries `input_frame`, `output_frame`, `input_ports`,
`output_ports` and `global_phase`. `WirePerm` is retained as an
**optimization**, not as the semantic representation.

Correctness is judged on the code space, exactly (`rtol=0`):

$$
U_{\text{sem}} = (u_{\text{out}})^{\dagger}\, G\, u_{\text{in}},
\qquad
\text{leak} = \lVert (I - u_{\text{out}} u_{\text{out}}^{\dagger})\, G\, u_{\text{in}} \rVert .
$$

## 2. Distributors are gate-free, in one shared layout

A distributor moves no data. It reinterprets **one** physical layout under two
logical types, in two mirror-image orientations:

| orientation | interface | layout |
|---|---|---|
| left  | $(A \oplus B) \otimes C \to (A \otimes C) \oplus (B \otimes C)$ | `[ tag \| summand payload \| C ]` |
| right | $A \otimes (B \oplus C) \to (A \otimes B) \oplus (A \otimes C)$ | `[ tag \| A \| summand payload ]` |

`Undist*` select the same layout with the two readings exchanged.

The width comes from the **selected layout** — the sum side — not from the
judgment types. Sizing from the types instead gives a 5-qubit domain against a
4-qubit codomain and wrongly suggests no gate-free distributor exists. This is
why frame selection must be independent of allocation: `allocation_width`
reads `select_frames`, rather than computing a second width policy of its own.

### 2.1 The two readings do not share a code list

This is the subtle point, and getting it wrong is silent.

A frame's `codes[k]` is the physical index of **its own** k-th semantic label,
so the two readings must each be enumerated in their own canonical order:

```
dist_l   dom (A+B)(x)C        : summand outer, C inner
         cod (A(x)C)+(B(x)C)  : summand outer, C inner     -- coincide
dist_r   dom A(x)(B+C)        : A outer, summand inner
         cod (A(x)B)+(A(x)C)  : summand outer, A inner      -- DIFFER
```

So `dist_l` is the identity on semantic labels, while `dist_r` is a
**non-trivial permutation** — and both are realised by a zero-gate circuit,
because the relabelling is a change of frame. Reusing one code list for both
of `dist_r`'s frames makes it silently compute the identity instead of the
canonical iso, while every "input and output codes are identical" assertion
still passes. That defect reached the working tree and was caught by the
`abstract_qswitch_oterm_e2e` demo (5/5 → 3/5, fidelity 0.0625), not by the
unit suite, whose oracle was wrong in the same direction.

Tests now compare against a distributivity oracle built independently of the
compiler, and assert `dist ; undist = id` at zero gates.

### 2.2 Sector-conditioned placement

A fixed wire tuple cannot express "wire 1 in sector 0, wires 1–2 in sector 1".
`Port.by_sector` carries the tag-conditioned placement; `Sector.tag_values` is
a **set** of tag words, since a summand may span several.

## 3. Align at the splice

Where a producer's output frame and a consumer's input frame disagree, the
splice inserts

$$
A\, u_C^{-} = u_P^{+}, \qquad G_C \mapsto A\,G_C\,A^{\dagger},
\qquad L^{\pm} \mapsto A L^{\pm} .
$$

Chronologically this is emitted as `A† ; G_C ; A`, **not** `A ; G_C ; A†`. The
tests assert the matrix equation, so the orientation cannot silently invert.

- The valid-code map is partial; it is extended over the unused code space in
  a fixed ascending order. This is a backend requirement, not tidiness:
  `ToffoliBox` rejects a partial permutation outright.
- The effective output frame is $A u_C^{+}$, which is recorded and propagated
  to the next splice — never recomputed from a type.
- Align **fails closed** on unequal register widths or unequal semantic
  dimensions. It never silently widens; a common ambient frame with typed
  residual ports must be selected first.
- Fast paths: frames agree → identity, zero gates; a pure wire permutation →
  folded into the running `WirePerm`; otherwise one exact permutation box.

## 4. What the tests lock down

- all four distributors: zero-gate, zero-leakage, exact against an
  independent oracle, in both materialization modes;
- `dist ; undist = id` in both orientations;
- the distributivity-naturality square (the former fidelity-0.5 witness);
- direct, nested, and chained splices; Encode/Decode composition;
- tensor placement, including that residual wires do not collide;
- frame serialization round-trips through the OCaml bridge **structurally** —
  logical type, symbolic expression, sectors, ports (including
  sector-conditioned placements) and the exact global phase.

---

The intended story is preserved and now holds for all four constructors:
**distributors themselves remain gate-free, while the compiler explicitly
carries the semantic address information needed to compose them correctly.**
