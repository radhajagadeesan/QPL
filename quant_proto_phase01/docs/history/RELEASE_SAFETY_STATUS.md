> **HISTORICAL RECORD — SeqCut / beta-boundary red-green witness record (all green at the final addendum)**
> Retained verbatim for provenance (checkpoints semantic-seqcut-20260905 / beta-boundary-20260905).  It describes the system as
> it stood at that checkpoint, not the current system.  For current
> documentation start at [`../INDEX.md`](../INDEX.md).

# Release-safety status

> **Addendum 2026-09-05 (later) — checkpoint `beta-boundary-20260905`.**
> Milestone 5 closed the last red: witness **C** is now SUPPORTED in both
> materialization modes — ingress exactly `(0,1,8,9)`, framed action
> exactly `I₂ ⊗ H`, zero leakage, zero phase — by inheriting the
> β-reduced Apply's boundary from the argument artifact's exact ingress
> and the body artifact's exact egress, with the substitution cut
> recorded as a validated `BetaSubstitution` and the closed
> function-value layout preserved as a residual port
> (`COMPILER_INVARIANTS.md`, Invariant B; gates in Part S). The repair is
> boundary-only: commands, phase and pending permutation are pinned
> unchanged. **The Python suite is fully green — zero red witnesses.**

> **Addendum 2026-09-05 — checkpoint `semantic-seqcut-20260905`.**
> Milestones 1–4 of the proof-directed semantic SeqCut plan are complete:
> recorded source-link dataflow behind per-polarity branch projections
> (Part P), Complete/Block consuming those projections with
> antecedent-defined alphabets (Part Q), the self-validating relational
> `seq_cut` join (Part R), and transactional whole-Seq composition through
> one `CutTransport` + `seq_cut` authority for identity, wire-permutation
> and code-permutation cuts (the Part-L positive gates; see
> `COMPILER_INVARIANTS.md`, Invariant S). Witness **D** is now green: the
> curried selector compiles to its exact pinned circuit in both modes.
> The executable red set is **C only** — the two
> `test_C_noncontiguous_beta_ingress_and_action` modes — deferred to the
> Milestone-5 beta-boundary repair. The category table and per-witness
> notes below predate this addendum and are retained as the historical
> record of the `031a40f` stabilization checkpoint.

**Baseline:** `031a40f`, branch `zenodo/frame-safety-hardening`.

This is a **stabilization checkpoint**, not a release candidate. It retains
explicit red correctness counterexamples by design. It is **not** Zenodo-ready.

Witnesses live in `python/tests/test_release_safety.py`. A passing count is
not evidence; each entry below is an exact counterexample or it is not a gate.

**Two kinds of check, not to be conflated:**

* **Semantic gates** — run both materialization modes, use the artifact's own
  recorded frames, compare against an independently constructed expected
  matrix, check the actual global phase, `rtol=0`, `atol=1e-10`. These are
  A, C, D, G and the three closed controls.
* **Compile-only non-rejection checks** — assert only that the guard does not
  reject a valid placement. They make **no** action, phase or leakage claim
  and must never be described as "exact".

---

## Categories

| category | witnesses |
|---|---|
| SUPPORTED | A, G, and the closed controls `H⊕I`, `I⊕X`, `H⊕S` |
| KNOWN RED | C, D |
| FAILS CLOSED | F (after the guard) |
| UNRESOLVED | E |
| UNCOVERED | B |

---

## Evidence

| witness | mode | compile | expected vs action | phase | leakage | frame codes |
|---|---|---|---|---|---|---|
| **A** `P_L` | F / T | ok | exact `I₆⊗X` | 0 | 0 | in = out = `(0,1,4,5,8,9,10,11,12,13,…)` |
| **A** `P_R` | F / T | ok | exact `I₆⊗X`, equal to `P_L` | 0 | 0 | in = out, as above |
| **A** distributor | F / T | ok | zero-gate | 0 | 0 | in = out |
| **C** noncontiguous β | F | ok | **not established** | 0 | **1.4142** | in `(0,4,8,12)`, expected `(0,1,8,9)`; out `(0,1,8,9)` |
| **C** noncontiguous β | T | ok | **not established** | 0 | **1.4142** | in `(0,4,8,12)`, out `(0,4,8,12)` |
| **D** curried `H⊕S⊕T` | F / T | ok | **not established** | 0 | **0.7071** | in = out = `(0,1,2,3,4,5)` |
| **E** qswitch η | F / T | ok | **not evaluable** | — | — | 14 qubits, in dim 1, out dim 16384 |
| **F** ctrl_ho | F / T | **UnsupportedFrame** | unevaluated | — | — | rejected before emission |
| **G** captured fn | F / T | ok | exact `H` | 0 | 0 | in = out = `(0,1)` |
| control `H⊕I` | F / T | ok | exact `H⊕I` | 0 | 0 | truthful |
| control `I⊕X` | F / T | ok | exact `I⊕X` | 0 | 0 | truthful |
| control `H⊕S` | F / T | ok | exact `H⊕S` | 0 | 0 | truthful |
| guard non-rejection ×2 | F / T | ok | *compile-only — no claim* | — | — | — |

---

## Notes per witness

### A — SUPPORTED
Unequal-width distributivity naturality with `A=Q, B=Q⊗Q, C=Q`. Both paths of
the square give the same exact 12-dimensional action `I₆⊗X`, built from
primitives; zero leakage; the distributor itself stays zero-gate.

### B — UNCOVERED
The `Seq` wire-permutation Align fast path has **no witness**. The candidate
(`TwistTen(Q,Z3)` spliced into a consumer) proved frame-identical —
`prod_out == cons_in == (0,1,2,3,4,5)`, `align_is_identity` true — so it never
reached the fast path. It was removed rather than left as a `pytest.skip`: a
skip reads as "fine" in a summary line. **The path is not claimed to be
supported.** No public-source witness has been found.

### C, D — KNOWN RED (boundary/artifact correctness blockers)
Nonzero leakage proves the recorded frames do **not** describe the artifact,
and for C the recorded ingress `(0,4,8,12)` is not the placement the
derivation makes (`(0,1,8,9)`). False recorded frames are already a
compositional correctness failure.

It is **not** claimed that the emitted gates are wrong under every possible
embedding. The action comparisons in these tests are computed through the same
untruthful frames and so say nothing independent about the physical circuit.
Establishing that would require testing under the actual physical embedding,
which has not been done.

C also shows a mode-dependent output frame (`(0,1,8,9)` unmaterialized versus
`(0,4,8,12)` materialized).

### E — UNRESOLVED (oracle blocked, not a compiler blocker)
`get_unitary` refusing 14 qubits is a **harness** limitation. A codeword
harness (`codeword_columns`) was written and **validated against a circuit
whose dense framed action is already known**, so scalable simulation is
available in principle.

E remains unresolved because the artifact is a closed function **value**: one
input codeword, and an output frame spanning all 2^14 basis states. A leakage
check against a code space that *is* the whole space is vacuous, and
`block_diag(U₀,U₁)` is a statement about the function's action on arguments,
not about the value's encoding — stating it needs the applied form as a source
term, which this pass does not have.

The earlier version of this test split the compiled action into blocks and
compared them with each other. That is not an independent oracle and could not
have detected a wrong-but-block-diagonal result. It has been removed.

### F — FAILS CLOSED (after the guard)
Three separate facts, kept apart:

1. **Compiler blocker (confirmed).** The open-branch placement overlaps:
   physical wire 0 is claimed by both the tag placement and the context
   placement. Before the guard this surfaced from inside the backend as
   `RuntimeError: Multiple operation arguments reference q[1]`.
2. **Absent feature (separate).** No `completed_dimension`; `Port` carries no
   `owner_id`. Recorded as absent, never synthesized by a test.
3. **Unevaluated.** Action, phase and leakage are not evaluated, because
   compilation does not produce a circuit.

### G — SUPPORTED
Smallest captured-function case, `(λf. λp. f p) H`, applied to a qubit: exact
`H`, zero leakage, zero phase, truthful frames, both modes.

The gate requires success and exactness. An earlier version also accepted
`UnsupportedFrame`; that escape hatch has been removed. On a witness that
demonstrably works, accepting a refusal would silently absorb a future
regression into "failed closed".

---

## The guard

`_check_open_placement` in `python/src/compile/to_pytket.py` is a
**pre-emission safety guard only**. It repairs no placement, infers no frame,
and adds no metadata. It uses evidence already computed on that path — the
tag/payload/context physical placements and each command's mapped argument
list — and rejects:

* a non-injective placement within one role;
* a physical wire claimed by two different roles;
* an operation that would receive the same physical wire twice.

It runs **immediately before the offending command-bearing branch is
emitted** — not before all compilation globally. Compilation of the enclosing
term proceeds normally until that branch is reached.

Its diagnostic is deterministic and names the construct, the wire and the two
conflicting roles:

```
PlusMap right: physical wire 0 is claimed by both the tag placement [0]
and the context placement [0, 1, 2, 3]. The derivation does not identify
that coordinate with itself, so the branch cannot be emitted. Failing
closed before emission.
```

**Guard-path coverage.** Instrumenting `_check_open_placement` shows which
witnesses actually reach it:

| witness | reaches the guard |
|---|---|
| direct open `PlusMap` with `env` (the two non-rejection checks) | yes — `PlusMap left` |
| F1 ctrl_ho | yes — `PlusMap right`, and it fires |
| closed controls `H⊕I`, `I⊕X`, `H⊕S` | **no** |

The closed controls are therefore **semantic regression controls** proving the
guard commit changed no working circuit — they are not guard-path coverage,
and are not claimed to be. All three are exact in both modes: `H⊕I`, `I⊕X`,
and `H⊕S` (both branches open, `H` on the left summand and `S` on the right).

No successful circuit changed: the legacy suite is 734 passed, identical to
the baseline.

---

## Deferred

1. **β-path derivation preparation.** `type_of` does recursively recheck terms
   and raises on ill-typed ones, but returns only a `DomCod` pair — no
   derivation-selected cuts or placements. `select_frames` is driven by that
   bare pair and `go` takes no derivation input. What is absent is not
   typechecking but **canonical derivation preparation**. Root cause of C and D.
2. **A witness for the wire-permutation splice (B).**
3. **An applied-form source term for the qswitch oracle (E).**
4. **Completed-dimension and port provenance metadata (F2).**
