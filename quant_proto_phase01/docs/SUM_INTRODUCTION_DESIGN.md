# Coherent ⊕-introduction (`Sum_αβ`): specification

**Status: implemented 2026-08-31 for closed premises.**

Shipped: `Sum` term class, logical typing `(Γ₁ ⊗ Γ₂, A ⊕ B)`, block-synthesis
emitter, Bridge node, and the OCaml `sum_` smart constructor enforcing
|α| = |β| = 1. The indispensable phase test passes:
`Sum_{i,1}(Id₁, Id₁) ⟿ diag(i, 1)`, not identity. An amplitude-normalised
weight is rejected — *"alpha must have modulus 1 (unit-modulus branch weight,
not an amplitude), got |z| = 0.707107"*. Tests:
`python/tests/test_sum_introduction.py` (12).

**Open premises are rejected before emission**, pending the frame inclusions
$j_i^\pm$ — see *The frame-aware round* in `docs/COMPILER_INVARIANTS.md`.

> **Correction notice.** An earlier revision of this document described
> `Sum_αβ` as fresh-tag *state preparation* of $\alpha|0\rangle + \beta|1\rangle$
> with $|\alpha|^2 + |\beta|^2 = 1$. **That was wrong.** The rule is a
> unitary block map $\alpha \widetilde W_1 \oplus \beta \widetilde W_2$ with
> $|\alpha| = |\beta| = 1$ between selected boundary sectors. No amplitude
> preparation occurs. This revision is transcribed from the emitter table
> rather than paraphrased.

## The emitter row

$$
\mathsf{Sum}_{\alpha,\beta}(\mathcal R_1, \mathcal R_2)
\;\longmapsto\;
\mathsf{Block}^{\mathrm{sum}}_{\alpha,\beta}
  \bigl(\mathsf{Emit}(\mathcal R_1), \mathsf{Emit}(\mathcal R_2)\bigr)
$$

This is distinct from the `Map` row, which transforms an *existing* tagged
sum. `Sum` has no sum-typed source; its source is the branch packing of the
two premise contexts.

## Typed definition

Premises

$$
\mathcal R_1 : \Gamma_1 \vdash R_1 : A,
\qquad
\mathcal R_2 : \Gamma_2 \vdash R_2 : B,
\qquad
\mathcal A_i = \mathsf{Emit}(\mathcal R_i).
$$

### Inactive-context completion

Performed **explicitly**, before anything else:

$$
\begin{aligned}
\overline{\mathcal A}_1 &:= \mathsf{Par}\bigl(\mathcal A_1, \mathsf{Wire}_{\Gamma_2}\bigr), \\
\overline{\mathcal A}_2 &:= \mathsf{Par}\bigl(\mathsf{Wire}_{\Gamma_1}, \mathcal A_2\bigr).
\end{aligned}
\tag{Sum-complete}
$$

On selected sectors this means

$$
\widetilde W_1 = W_1 \otimes Y_{\Gamma_2},
\qquad
\widetilde W_2 = Y_{\Gamma_1} \otimes W_2 .
\tag{Sum-through}
$$

Then pad both completed artifacts with identity wires to a common physical
width $h$, giving fields

$$
\widehat{\mathcal A}_i =
\bigl(h,\ \widehat G_i,\ \widehat L_i^-,\ \widehat L_i^+,\ \widehat p_i^-,\ \widehat p_i^+\bigr),
\qquad
\gamma_1 = \alpha,\quad \gamma_2 = \beta,
\quad |\alpha| = |\beta| = 1 .
$$

## Reference recursive-binary packing

$$
Q = 1 + h, \qquad \tau_1 = 0, \quad \tau_2 = 1,
\qquad
\widehat\jmath_i |\psi\rangle = |\tau_i\rangle \otimes |\psi\rangle .
\tag{Sum-tag}
$$

Source and target packings:

$$
P_{\mathrm{sum}}^- = P_{\Gamma_1,\Gamma_2}^{\mathrm{br}},
\qquad
P_{\mathrm{sum}}^+ = P_{A,B} .
\tag{Sum-pack}
$$

The source packing is the **branch packing** — not an existing input-sum
layout:

$$
P_{\Gamma_1,\Gamma_2}^{\mathrm{br}}\, \iota_i |\psi\rangle
=
|\tau_i\rangle \otimes |\psi\rangle \otimes |0^{\,h-q_i}\rangle .
\tag{Sum-source-pack}
$$

Gate operator:

$$
G_{\mathrm{sum}}
=
\sum_{i=1}^{2} |\tau_i\rangle\!\langle\tau_i| \otimes \gamma_i \widehat G_i .
\tag{Sum-G}
$$

Placement and frame fields are uniquely determined on each branch by

$$
p_{\mathrm{sum}}^\epsilon P_{\mathrm{sum}}^\epsilon \iota_i
= \widehat\jmath_i \widehat p_i^\epsilon
\tag{Sum-p}
$$

$$
L_{\mathrm{sum}}^\epsilon p_{\mathrm{sum}}^\epsilon P_{\mathrm{sum}}^\epsilon \iota_i
= \widehat\jmath_i \widehat L_i^\epsilon \widehat p_i^\epsilon,
\qquad \epsilon \in \{-, +\},
\tag{Sum-L}
$$

with the fixed lexicographic extension on the unused complement.
Equivalently, on the selected code sectors:

$$
\left.\operatorname{Circ}\bigl(\mathsf{Block}^{\mathrm{sum}}_{\alpha,\beta}\bigr)\right|_{C_{\mathrm{sum}}^-} j_i^-
= j_i^+ \gamma_i \widetilde W_i,
\qquad i = 1, 2 .
\tag{Sum-selected}
$$

Because the ranges of $j_1^\epsilon, j_2^\epsilon$ are orthogonal and jointly
exhaust $C_{\mathrm{sum}}^\epsilon$, this determines a unitary between the
selected sectors.

## Flat-backend realization

**Do not copy $Q = 1 + h$ literally into the flat backend when $A$ or $B$ is
itself sum-headed.** Use the canonical maximal-sum-frame inclusions
$j_i^\epsilon$ (see `COMPILER_INVARIANTS.md`, layout policy).

The layout-independent executable contract is

$$
W_{\mathrm{sum}}^{\mathrm{sel}}
=
j_1^+ \alpha \widetilde W_1 (j_1^-)^\dagger
+
j_2^+ \beta \widetilde W_2 (j_2^-)^\dagger .
\tag{Flat-Sum}
$$

Extended to the invalid-tag complement by the fixed canonical unitary:

$$
G_{\mathrm{sum}}
=
W_{\mathrm{sum}}^{\mathrm{sel}}
+
j_\perp^+ U_\perp (j_\perp^-)^\dagger .
\tag{Flat-Sum-total}
$$

For ordinary non-sum-headed $A, B$ this reduces exactly to the binary
root-tag formula (Sum-G).

## Critical implementation interpretation

This rule **does not** prepare $\alpha|0\rangle + \beta|1\rangle$. The input
selected boundary is *already* an orthogonal direct sum of the two
branch-completed source sectors; the tag is its physical coordinate. The
operation is

$$
\alpha \widetilde W_1 \oplus \beta \widetilde W_2 .
$$

Therefore the implementation must:

1. require $|\alpha| = |\beta| = 1$ — **not** $|\alpha|^2 + |\beta|^2 = 1$;
2. emit **no** Hadamard and no amplitude preparation;
3. preserve every premise circuit's global phase;
4. promote each premise global phase to an **exact-tag conditional phase**;
5. apply $\alpha$ and $\beta$ to their **entire valid branch blocks**.

Items 3–4 are the same invariant enforced elsewhere by the controlled-emission
choke-point; `Sum` is one more consumer of it, not a special case.

## Typing: logical endpoints, not physical packing

$$
\boxed{\ \operatorname{type\_of}(\mathsf{Sum}_{\alpha,\beta}(R_1,R_2)) = (\Gamma_1 \otimes \Gamma_2,\ A \oplus B)\ }
$$

realizing the logical rule

$$
\frac{\Gamma_1 \vdash R_1 : A \qquad \Gamma_2 \vdash R_2 : B}
     {\Gamma_1, \Gamma_2 \vdash [\alpha R_1 \mid \beta R_2] : A \oplus B}
$$

```python
def type_of_sum(t):
    gamma1, a = type_of(t.left)
    gamma2, b = type_of(t.right)
    return tensor_context(gamma1, gamma2), Plus(a, b)
```

**It must not return** `Plus(Complete(Γ₁,Γ₂), Complete(Γ₂,Γ₁))`. That would
confuse a physical boundary packing with an object-language type and expose
the branch-selection tag as source data. It would pass width-based checks
while denoting a different source-language morphism.

*Composition follows from the logical endpoints.* `Seq(Sum(R₁,R₂), F)` with
$F : A \oplus B \to C$ checks only $\operatorname{cod}(\mathsf{Sum}) = A \oplus B
= \operatorname{dom}(F)$, and the composite has source $\Gamma_1 \otimes \Gamma_2$.
`Apply(f, Sum(R₁,R₂))` sees argument type $A \oplus B$ with free-resource
context $\Gamma_1 \otimes \Gamma_2$. Ordinary typing applies unchanged.

### Where the branch packing lives

$P^{\mathrm{br}}_{\Gamma_1,\Gamma_2}$ is a **compilation frame, not a `Ty`**.
The physical register width comes from the block frame, not from
`max(width(logical_dom), width(logical_cod))`. `Seq`/`Apply` check logical
types and compose physical frames separately.

The target frame reads back as $A \oplus B$ but may still carry
inactive-context spectator coordinates — so Sum's physical width can exceed
$\operatorname{width}(A \oplus B)$. See Invariant W in
`COMPILER_INVARIANTS.md`, which is stated over frames for this reason.

**Implementation note (verified 2026-08-31).** This codebase already
separates physical register size from logical type width: `compile()` sizes
its register with `_internal_width(term)`, documented as *"For most terms
this is `max(width(dom), width(cod))`; for higher-order terms we need extra
wires"*, and it recurses compositionally. Sum therefore needs a
`_internal_width` case rather than a `Compiled` frame refactor. Should the
*packing* (the inclusions $j_i^\epsilon$, as opposed to the width) turn out to
need threaded metadata, executable Sum is postponed rather than shipped with
a fabricated source type.

## Tests

**Indispensable phase test.**

$$
\mathsf{Sum}_{i,1}(\mathsf{Id}_1, \mathsf{Id}_1)
\quad\leadsto\quad
\operatorname{diag}(i, 1)
$$

on the two valid codewords — **not** identity. A build that yields identity
here has dropped the branch coefficients.

**Acceptance tests.**

- $\mathsf{NPlusMap}((Z_3, Z_5), (\mathsf{Id}, \mathsf{Id}))$ compiles to
  **exactly three wires** (8 unit leaves, $\lceil\log_2 8\rceil = 3$).
- The same term under **reassociated sum syntax** produces the same canonical
  flat frame — associativity changes logical leaf numbering only, never the
  representation class.

## Relationship to branch-context linearity

(Sum-complete) is inactive-context completion in exactly the sense of
`BRANCH_CONTEXT_LINEARITY.md`: branch 1 acts on $\Gamma_1$ and transports
$\Gamma_2$ unchanged, branch 2 conversely. Neither context is duplicated or
discarded — $\mathsf{Wire}_{\Gamma_j}$ is identity transport, and
(Sum-through) is its selected-sector reading. The two designs share one
concept and should share its vocabulary in the paper.

## Implementation surface (as built)

Deliberately minimal.  The items below were confirmed against the
invariants document and are IMPLEMENTED as described (closed premises
only; the sealed Source surface exposes no introduction — see
`LIMITATIONS.md §8`, the governing statement):

- **OCaml** — smart constructor taking $\alpha, \beta$ (validated
  $|\alpha| = |\beta| = 1$), the two premise terms, and a context-partition
  witness for $\Gamma_1, \Gamma_2$ (the binary `split` already suffices here).
- **Bridge IR** — one new node carrying $(\alpha, \beta, A, B, R_1, R_2)$.
- **Python IR** — matching term class.
- **Emitter** — realize (Flat-Sum): canonical-frame inclusions for both
  sectors, per-branch identity transport of the inactive context, branch
  coefficient applied to the whole valid block, premise global phase promoted
  to exact-tag phase, invalid-tag complement filled by the fixed canonical
  unitary (identity where source and target complement coordinates agree).

No ancilla allocation and no state-prep machinery are required; the earlier
revision's allocator concern does not arise.

**Implementation note.** Each premise's own global phase is already carried by
its `get_unitary()` (pytket respects `add_phase`), so the splat promotes it to
an exact-tag conditional phase automatically; the branch coefficient γ adds
only α or β on top. Folding the premise phase into γ as well double-counts it —
a `GlobalPhase(π)` premise then gave `(−1)·(−1) = +1`. Caught by
`test_premise_global_phase_is_promoted_not_dropped`.
