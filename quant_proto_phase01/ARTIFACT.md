# SPLASH 2026 Artifact — Granthi / QPL

Higher-Order Quantum Programming via Unitary Wiring — artifact accompanying
the OOPSLA 2026 submission.

Target badges: **Available**, **Functional**, **Reusable**, **Results Reproduced**.

---

## 1. Getting Started (< 5 minutes)

The artifact ships as a Docker image with the full toolchain baked in:
Debian 12, OCaml 4.14, dune and ppxlib (>= 0.37) from opam, Python 3.11,
pytket pinned at 2.11.0.

```bash
# from the artifact directory (the one containing Dockerfile)
docker build -t granthi-ae .
docker run --rm -it granthi-ae
# inside the container, you land at /work with `opam env` already loaded.
```

If the reviewer prefers native install instead of Docker, see §7.

## 2. Kick-the-Tires (~1 minute)

```bash
docker run --rm granthi-ae artifact/kick-the-tires.sh
```

Checks: `dune build` succeeds, one small OCaml demo runs end-to-end
(elaborate → bridge → Python compile → pytket circuit), one Python
`pytest` module passes, and one demo's output matches the committed
`.output` file byte-for-byte.

Exit code 0 = all four checks passed.

## 3. Full Reproduction (~5–10 minutes)

```bash
docker run --rm -v "$PWD/artifact/results:/work/artifact/results" granthi-ae \
    artifact/reproduce.sh
```

Runs the complete v1.0.x verification surface: `dune build`, the full
`dune runtest` (including the `let%source` frontend compile-pass/reject
harness, the 34-row Source counterpart coverage harness, datatype
invariants, and the compiled documentation examples), then **all 34
demos** from `ocaml/demos/manifest.tsv` — 32 golden demos byte-diffed
against committed `.output` files and 2 intentional no-fixture dumps —
and finally the full Python `pytest` suite.  A missing golden is a
failure, not a skip.

Exit code 0 only on the exact expected outcome
(32 golden + 2 no-fixture + all suites green).

## 4. Claims Table

Every row is a paper example. The **Claim** column names the structural
property the artifact verifies. Verification is via the demo's own printed
assertions (`PASS`/`SUCCESS`/composition-law checks/`eq_circ` fidelity checks)
plus a byte-for-byte `diff` against a committed reference output.

Sections refer to the accompanying paper.

| # | Paper location | Example | Demo | Claim verified |
|---|---|---|---|---|
| 1 | §10 | Standard algorithms (Deutsch–Jozsa, HSP, Simon, Bell, GHZ) | `ocaml/demos/algorithms_e2e.ml` | Each algorithm compiles end-to-end; circuit qubit counts match spec |
| 2 | §4, §5, §10 | Higher-order `ctrl` combinator | `ocaml/demos/ctrl_lambda_e2e.ml` | ctrl instantiations compile; verified against meta-level |
| 3 | §10 | Nested ctrl applications | `ocaml/demos/verify_nested_ctrl_e2e.ml` | Nested composition preserves semantics |
| 4 | §10 | Nested λ application | `ocaml/demos/nested_apply_e2e.ml` | Boundary splicing composes correctly |
| 5 | §4, §8, §10 | Abstract QSwitch (open, 4 Fredkins) | `ocaml/demos/abstract_qswitch_oterm_e2e.ml` | U†U = I; partial trace over function wires matches meta-level QSwitch |
| 6 | §8, §10, §11 | Closed qSwitch\_{H,S} on two qubits | `ocaml/demos/qswitch_instantiated_e2e.ml` | Compiles to expected two-qubit circuit; semantics match |
| 7 | §4, §5, §10 | Phase-marked short-circuit AND (routeW^q, −1 phase) | `ocaml/demos/short_circuit_e2e.ml` | routeW^q involutive; and\_sc^q involutive; phase interference verified |
| 8 | §5 | Fractional-swap `exp(iθ · twist)`, θ = π/4, π/2 | `ocaml/demos/exp_twist_e2e.ml` | Composition law: `exp(iπ/4)² = exp(iπ/2) = i·SWAP` |
| 9 | §5 | Branch-swap exponentials E12, E23 on Q ⊕ (Q ⊕ Q) | `ocaml/demos/exp_swap_T3_e2e.ml` | Composition law holds; E12 and E23 non-commute (fidelity 0.8125) |
| 10 | §4, §9 | ℤn kick, binary tag encoding, CRz decomposition | `ocaml/demos/zn_controlled_phase_e2e.ml` | kick\_n = product of ⌈log₂ n⌉ CRz gates |
| 11 | §4 | ℤ_n group ops (add, neg) illustrated at ℤ_5 | `ocaml/demos/zn_group_ops_e2e.ml` | Group laws verified at circuit level |
| 12 | §4 | User-defined finite datatypes | `ocaml/demos/datatype_demo.ml` | Datatype registration and elaboration |
| 13 | §10 | SELECT combinator, n = 2 | `ocaml/demos/abstract_select_2_e2e.ml` | SELECT compiles for n = 2 |
| 14 | §10 | SELECT curried, n = 3 | `ocaml/demos/curried_select_3_e2e.ml` | Curried SELECT compiles |
| 15 | §10 | SELECT curried, non-distributive variant | `ocaml/demos/curried_select_3_ndist_e2e.ml` | Alternative distribution compiles equivalently |
| 16 | §10 | Nested SELECT | `ocaml/demos/nested_select_e2e.ml` | Nested SELECT composes |
| 17 | §8 | n-ary sum PlusMap compilation walkthrough | `ocaml/demos/n_plusmap_e2e.ml` | n-ary Plus compiles per compilation rules |
| 18 | (all) | Python core regression suite | `python/tests/` | 100% pass |

### Non-runtime paper claims (analytical, not diff-checked)

The following paper items are analytical/typing claims with no runtime demo.
Reviewers verify by inspection of the paper and source, not by execution.

- **§5** CPS / Continuation constructions (typing table).
- **§7** Boundary semantics worked computation (dim 4).
- **§11** Qunity comparison — first-order routing pattern
  `QBool ⊗ A ≅ (base ⊗ A) ⊕ (base ⊗ A)` (comparison text).
- **Appendix A** η-expanded identity for a QBool variable in a structured
  context (focused-rules example).
- **Appendix G** Guarded pipeline `pipelineK : E ⊕ ((R ⊸ S) ⊗ R) ⊸ E ⊕ S`
  (n-ary monoidal example).

### A note on gate counts

The paper cites illustrative gate counts (QSwitch, short-circuit, ℤ8). These
depend on pytket's decomposition strategy and its optimization-pass version.
The artifact does **not** diff against exact gate counts to avoid brittleness
across pytket point releases; demos print current counts on the pinned pytket
2.11.0 build for reviewer inspection.

## 5. Reusability — How to Adapt the Artifact

The system is designed to be extended. See:

- `docs/PROGRAMMING_GUIDE.md` — user-facing guide covering all language
  features with worked examples.
- `docs/COMPILER_API_GUIDE.md` — internals of the compiler and extension
  points (adding a gate, adding a type constructor, adding a rewrite).
- `docs/API_REFERENCE.md` — reference documentation.
- `docs/LIMITATIONS.md` — honest inventory of what is and is not supported.
- `docs/OCAML_DSL.md` — the sealed Source API and internal Raw layers.
- `docs/PROGRAMMING_GUIDE.md` — the `let%source` user syntax (the
  public interface), with examples compiled by
  `ocaml/examples/doc_examples.ml`.

Concrete recipes:

- **Add a new gate**: `python/src/lang/terms.py` defines gate atoms;
  `python/src/compile/to_pytket.py` maps them to pytket. Match an existing
  single-qubit gate (e.g. `H` or `X`).
- **Add a new datatype**: use `datatype` in the OCaml surface language.
  `ocaml/demos/datatype_demo.ml` walks through registration.
- **Add a new demo**: create `ocaml/demos/<name>.ml`, add an executable
  stanza in `ocaml/demos/dune`, and (once its output is stable) save its
  stdout to `ocaml/demos/<name>.output` for regression checking.

## 6. Repository Layout

```
quant_proto_phase01/
├── ARTIFACT.md               ← this file
├── Dockerfile                ← reviewer-facing reproducible build
├── LICENSE                   ← MIT
├── README.md                 ← project overview
├── artifact/
│   ├── kick-the-tires.sh     ← smoke test (~1 min)
│   ├── reproduce.sh          ← full claim-by-claim reproduction (~10 min)
│   └── results/              ← output directory (populated on run)
├── ocaml/                    ← OCaml surface language
│   ├── lib/                  ← elaborator, bridge, Linear GADT DSL
│   ├── demos/                ← E2E demos (one per claim) + .output files
│   ├── test/                 ← dune tests
│   └── dune-project
├── python/                   ← Python core compiler + pytket backend
│   ├── src/                  ← lang/, compile/, core/
│   ├── tests/                ← pytest suite
│   └── demos/                ← illustrative Python-side demos
└── docs/                     ← user + developer docs (see docs/INDEX.md)
```

## 7. Native Install (if not using Docker)

Reviewers who prefer bare-metal:

```bash
# 1. OCaml 4.14 via opam
sudo apt install -y opam build-essential git
opam init -y --disable-sandboxing
opam switch create 4.14.2 --yes
eval $(opam env)
opam install -y dune.3.14.0 'ppxlib>=0.37'

# 2. Python 3.11 (or 3.12) venv with pytket
python3 -m venv venv
source venv/bin/activate
pip install pytket==2.11.0 pytest

# 3. Build and test
cd quant_proto_phase01
export PYTHONPATH=$PWD/python/src
(cd ocaml && dune build)
artifact/kick-the-tires.sh
artifact/reproduce.sh
```

## 8. Availability

A DOI has **not** been assigned to this snapshot.  If the release is
archived (e.g., on Zenodo), the identifier will be added here; no
deposit is claimed until then.

License: MIT (see `LICENSE`).

## 9. Known Limitations

See `docs/LIMITATIONS.md`. Highlights:

- `ExpInvolution` circuit size is capped at 3 qubits per emission (a pytket
  `UnitaryNqBox` limit, not a language-level one).
- `ExpInvolution` bodies must be first-order (contain no `Arrow` types) —
  enforced at term construction. See recent change notes.

## 10. Contact

Radha Jagadeesan · radha.jagadeesan@gmail.com
