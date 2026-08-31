# The n-quantum-switch in Granthi

This document walks through what the artifact ships for the higher-order
n-quantum-switch `QS_n`, what construction it uses, how the demos are
organized by n, and where the scaling wall sits.

## The higher-order type

The pure higher-order n-quantum-switch has type

$$
\mathsf{QS}_n :
P_n \otimes \bigotimes_{i=1}^{n} (A \multimap A)
\longrightarrow
P_n \otimes (A \multimap A)
$$

where `P_n = ℂ[S_n]` is the coherent control over permutations, and its
action on basis states of `P_n` is

$$
|\pi\rangle \otimes (f_1, \ldots, f_n)
\;\longmapsto\;
|\pi\rangle \otimes f_{\pi(n)} \circ \cdots \circ f_{\pi(1)}.
$$

## Implemented via the Araújo–Costa–Brukner dummy-register simulator

Granthi's shipped `QS_n` demos use the **fixed-order dummy-register
simulator** of Araújo, Costa and Brukner (Appendix C) / Taddei et al.
(Appendix A.2). Under η-expansion of the target, the whole
construction becomes first-order end-to-end (no sum type carries a
function payload, so the first-order sum-payload restriction of
`docs/LIMITATIONS.md §4` is respected).

Encode the permutation as `C = (C_1, …, C_n)` with `C_k = π(k)`. With a
target register `T ≃ A` and one dummy register `D_i ≃ A` per `f_i`,
define

$$
R(c) = \sum_{i=1}^{n} |i\rangle\!\langle i|_c \otimes \mathrm{SWAP}_{T, D_i},
\qquad
F = I_T \otimes f_1^{D_1} \otimes \cdots \otimes f_n^{D_n},
$$

and

$$
\widetilde{\mathsf{QS}}_n = \prod_{k=1}^{n} R(C_k)\, F\, R(C_k)
: P_n \otimes T \otimes \bigotimes_i D_i \longrightarrow \text{same}.
$$

Trace-through gives, for every `π ∈ S_n`,

$$
|\pi\rangle |\psi\rangle_T \bigotimes_i |a_i\rangle_{D_i}
\;\longmapsto\;
|\pi\rangle \cdot \left(f_{\pi(n)} \cdots f_{\pi(1)} |\psi\rangle\right)_T
\otimes \bigotimes_i \left(f_i^{n-1} |a_i\rangle\right)_{D_i}.
$$

The dummies pick up `f_i^{n-1}` **independent of π** — the
"clean-garbage lemma". Superpositions of permutations are preserved
exactly. Each `f_i` is called `n` times, giving `n²` total oracle calls.

`R(C_k)` is the coherent selected-SWAP of `T` with `D_{C_k}`. It is
built via Granthi's `control` combinator on the arity-`n` datatype,
whose balanced-binary tag encoding gives a **log-depth binary dispatch
tree** over `⌈log₂ n⌉` tag qubits.

## Shipped demos

**By n:**

| Demo | n | A | Control encoding | Verification |
|:---|:---:|:---:|:---|:---|
| `qs2_dummy_sim_e2e.ml` | 2 | Q | 2 subregisters of 1 tag qubit each | 3/3 fid 1.0 (clean-garbage lemma as full 5-qubit unitary equality) |
| `qs3_pn_dummy_sim_e2e.ml` | 3 | Q | Single P_3 = ℂ[S_3] via arity-8 padded datatype (3 tag qubits, 6 slots + 2 |id⟩ duplicates) | 5/5 fid 1.0 (clean-garbage lemma as full 7-qubit unitary equality) |

**Other n=2 forms** (different construction axes):

| Demo | What it shows |
|:---|:---|
| `qswitch_instantiated_e2e.ml` | Closed concrete qswitch on `H`, `S` |
| `qswitch_eta_endoQ_e2e.ml` | η-expanded at `A = Q ⊸ Q` (higher-order payload made first-order via full η-expansion) |
| `qswitch_eta_expansion_e2e.ml` | Generic η-expansion at any first-order payload `A` |
| `abstract_qswitch_oterm_e2e.ml` | Abstract qswitch as an open term with function-value inputs (`oapp`, `olam`, split witnesses) |

## Scaling and the verification wall

The construction pattern extends to arbitrary `n` by the same template:

- **Control register.** Either the direct `P_n = ℂ[S_n]` encoding (arity-`n!` datatype, `⌈log₂ n!⌉` tag qubits, padded to a power of 2), or the `n`-subregister form (`n` datatypes of arity `n`, each `⌈log₂ n⌉` tag qubits, `n · ⌈log₂ n⌉` total). The `qs3` demo demonstrates the direct P_n form; `qs2` demonstrates the subregister form. Both work; the subregister form is what the Araújo–Costa–Brukner analysis literally writes down.

- **Router `R(C_k)`.** Via the `control` combinator on the arity-`n` datatype. `⌈log₂ n⌉` tag qubits give a log-depth binary dispatch tree; each of the `n` branches is a wire-permutation swapping `T` with the `k`-th dummy (built from `assoc_tensor` + `twist_tensor` chains, materialized to real SWAP gates when controlled).

- **Round.** `round(C_k) = R(C_k) ; (id_D ⊗ F) ; R(C_k)`. When `F² = I` (achieved by choosing each `f_i` to be an involution — e.g., any Pauli or Hadamard), `round(C_k)² = id`, giving a clean structural involution check.

- **Full simulator.** Compose `n` rounds sequentially. For the direct P_n encoding, no inter-round routing is needed (the control register threads through each round unchanged, since `control` is coherent-case-preserving). For the subregister form, each round accesses a different `C_k`, so a small rotation of the control tensor is needed between rounds.

### Verification wall

`qs2` (n=2, 5 qubits total) and `qs3` (n=3, 7 qubits total) are both
well under pytket's `get_unitary` ceiling (~11 qubits), so both admit
the clean-garbage lemma as a full unitary equality check.

At **n = 4**, a concrete-gate version would need `2 tag + 1 target + 4
dummies = 7` qubits (fine), but the *abstract* form with per-round
function value inputs would need `⌈log_2 24⌉ + n² · 2·w(A) + 1 + n =
5 + 32 + 1 + 4 = 42` qubits — beyond `get_unitary`. Compile-only
verification is still available (the term type-checks and compiles);
semantic unitary equality is not.

At **n = 8**, the concrete-gate form is `3 + 1 + 8 = 12` qubits and
sits right at the edge of `get_unitary`; the abstract form is
`⌈log₂ 40320⌉ + 8² · 2 + 1 + 8 = 16 + 128 + 1 + 8 = 153` qubits — well
past the wall. Compile-only verification remains available.

### Bug adjacent to router construction

An earlier attempt at `qs8_log_tree_router_e2e.ml` (12 qubits, standalone
`R(c)` at n=8) compiled cleanly to 32 gates but hit pytket's
`get_unitary` ceiling on the involution check `R;R = id`. That file was
removed in favor of `qs3_pn_dummy_sim`, which uses the same `control`
combinator at arity 8 (with padding) and is fully verifiable.

## Summary

The n-quantum-switch story shipped end-to-end at n ∈ {2, 3} with full
clean-garbage unitary verification. The construction template
generalizes to arbitrary n by the same `control`-combinator + log-depth
router + `n`-round assembly; verification via `eq_circ` is bounded by
pytket's `get_unitary` ceiling at the concrete-gate wire count
(~11 qubits ⇒ n ≤ 8 concrete, n ≤ 3 abstract).
