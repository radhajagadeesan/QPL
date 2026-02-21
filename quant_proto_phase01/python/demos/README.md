# Python Demos

Demonstrations of Granthi language features and compilation using the Python API.

> **Note:** For OCaml E2E demos that compile through the full pipeline to circuits, see `ocaml/demos/`.

---

## Available Demos

| Demo | File | Description |
|------|------|-------------|
| **QSwitch (pipeline)** | `quantum_switch_demo.py` | **Full Surface→Elaboration→Circuit pipeline demo** |
| QSwitch (basic) | `qswitch_demo.py` | Higher-order quantum switch combinator |
| QSwitch (term) | `qswitch_term_demo.py` | QSwitch as Case term with DistR |
| QSwitch (abstract) | `qswitch_abstract_demo.py` | Abstract QSwitch type and wire layout |
| **QSwitch (abstract circuit)** | `qswitch_abstract_circuit_theory_demo.py` | **THEORY: Abstract QSwitch circuit diagrams (no instantiation)** |
| **QSwitch (instantiation)** | `qswitch_instantiation_demo.py` | **QSwitch with ONE vs TWO functions, simplification analysis** |
| **QSwitch (curried)** | `qswitch_curried_theory_demo.py` | **THEORY: Curried λb.λf.λg.λx type derivation** |
| **Zn Controlled Phase** | `zn_controlled_phase_demo.py` | **Z2, Z4, Z5 controlled phase rotation via Ctrl** |
| ExpInvolution | `exp_twist_demo.py` | Exponentials of structural involutions |
| Pauli Conjugation | `pauli_conjugation_demo.py` | Qubit as I+I, Pauli identity verification |

---

## QSwitch Demos

Multiple demos showing different aspects of the quantum switch combinator.

### QSwitch (pipeline) — `quantum_switch_demo.py`

Comprehensive demo showing the full Granthi compiler pipeline on QSwitch:

**Run:**
```bash
PYTHONPATH=python/src python python/demos/quantum_switch_demo.py
```

**What it shows:**
1. Surface language representation of QSwitch
2. Elaboration to Core IR with controlled gates
3. Circuit compilation and gate output
4. The anti-control pattern (X sandwiches)

**Key insight:** Demonstrates how a higher-order quantum program becomes a first-order circuit through the full compilation pipeline.

### QSwitch (basic) — `qswitch_demo.py`

Original QSwitch demo showing the combinator and compilation.

**Run:**
```bash
PYTHONPATH=python/src python python/demos/qswitch_demo.py
```

### QSwitch (term) — `qswitch_term_demo.py`

Shows QSwitch built as an actual Term using Case (copairing):

```
QSwitch[H,S] = DistR(I,I,Q) ; Case(I⊗Q, I⊗Q, H;S, S;H)
```

**Run:**
```bash
PYTHONPATH=python/src python python/demos/qswitch_term_demo.py
```

**What it shows:**
1. Type definitions: Bool = I+I, wire layouts
2. DistR transforms Bool⊗Q → (I⊗Q)+(I⊗Q)
3. Case with H;S (left) and S;H (right) branches
4. Compiled circuit: 6 gates (X, CH, CS, X, CS, CH)

### QSwitch (abstract) — `qswitch_abstract_demo.py`

Shows the **abstract QSwitch type signature** before instantiation:

```
QSwitch : (Q⊸Q) ⊗ (Q⊸Q) ⊗ Bool ⊗ Q → Bool ⊗ Q
```

**Run:**
```bash
PYTHONPATH=python/src python python/demos/qswitch_abstract_demo.py
```

**What it shows:**
1. Arrow type widths: Q⊸Q has width 2
2. Input wire layout: [f_arg | f_res | g_arg | g_res | tag | x] = 6 wires
3. Output wire layout: [tag | x'] = 2 wires
4. LetPair structure for destructuring
5. Instantiation with H, S

### QSwitch (OCaml oterm) — `ocaml/demos/abstract_qswitch_oterm_e2e.ml`

OCaml surface language demo showing higher-order QSwitch as a lambda term:

**Run:**
```bash
cd ocaml && dune exec demos/abstract_qswitch_oterm_e2e.exe
```

**What it shows:**
1. QSwitch type: `(Q→Q) ⊗ (Q→Q) ⊗ Bool ⊗ Q → Bool ⊗ Q`
2. Full source language: Lam, LetPair, Var, App, PlusMap
3. Instantiation with concrete gate pairs and unitary verification

### QSwitch (abstract circuit) — `qswitch_abstract_circuit_theory_demo.py` (THEORY ONLY)

Shows the **abstract QSwitch circuit structure** in curried form with NO instantiation:

```
QSwitch = λb. λf. λg. λx. case b of
            | Left(u)  ⇒ (Left(u), f(g(x)))
            | Right(u) ⇒ (Right(u), g(f(x)))
```

**Run:**
```bash
PYTHONPATH=python/src python python/demos/qswitch_abstract_circuit_theory_demo.py
```

**What it shows:**
1. Curried type: `Bool ⊸ (A ⊸ A) ⊸ (A ⊸ A) ⊸ A ⊸ (Bool ⊗ A)`
2. Wire layout (8 total): `[b|f_arg|f_res|g_arg|g_res|x] → [b'|result]`
3. Abstract circuit diagram showing function wire routing
4. Branch-by-branch routing diagrams
5. Quantum CASE circuit with anti-control pattern
6. Abstract function application (Apply as pure wiring)

**Key insight:** The abstract QSwitch is **pure routing + control** with 0 gates. The control qubit `b` passes through to the output.

### QSwitch (instantiation) — `qswitch_instantiation_demo.py`

Shows QSwitch instantiated with concrete functions, with **simplification analysis**:

**Run:**
```bash
PYTHONPATH=python/src python python/demos/qswitch_instantiation_demo.py
```

**What it shows:**

**Section 1: ONE function (f = g)**
- Simplification analysis: both branches compute f∘f
- For f = H: H² = I, so QSwitch[H,H] = Identity
- Circuit: 6 gates (all cancel to identity)
- Verification: unitary = identity matrix

**Section 2: TWO functions (f ≠ g, non-commuting)**
- Simplification analysis: HS ≠ SH, no simplification possible
- Matrix calculation showing non-commutativity
- Circuit: 6 gates (X; CH; CS; X; CS; CH)
- Execution traces for |0⟩, |1⟩, and |+⟩ inputs

**Key insight:** QSwitch is only non-trivial when f and g don't commute.

### QSwitch (curried) — `qswitch_curried_theory_demo.py` (THEORY ONLY)

**Step-by-step type derivation** for the curried QSwitch (pedagogical focus):

**Run:**
```bash
PYTHONPATH=python/src python python/demos/qswitch_curried_theory_demo.py
```

**What it shows:**
1. Branch typing (what each case branch returns)
2. Case expression typing
3. Lambda abstraction built inside-out
4. Full type: `Bool ⊸ (A ⊸ A) ⊸ (A ⊸ A) ⊸ A ⊸ (Bool ⊗ A)`
5. Comparison with tensored version (same width via currying isomorphism)
6. Linearity verification (each variable used exactly once)
7. Semantic traces for |0⟩, |1⟩, and |+⟩ inputs

**Key insight:** The control qubit `b` appears in both input AND output. It's not consumed — it passes through and becomes entangled with the result.

---

## Zn Controlled Phase Demo

Demonstrates the `Ctrl` combinator for controlled operations on cyclic groups:

**Run:**
```bash
PYTHONPATH=python/src python python/demos/zn_controlled_phase_demo.py
```

**What it shows:**

| Group | Tag Width | Gates | Example |
|-------|-----------|-------|---------|
| Z2 (Bool) | 1 bit | 1 | CZ on control + target |
| Z4 | 2 bits | 2 | CS + CZ (binary decomposition) |
| Z5 | 3 bits | 3 | CRz(2π/5) + CRz(4π/5) + CRz(8π/5) |

**Key insight:** Phase selection uses binary decomposition. For Zn with n-bit register:
- Phase(k) = Σᵢ tᵢ × (2ⁱ × 2π/n) where tᵢ are tag bits
- Each bit contributes a controlled rotation: CRz(2π×2ⁱ/n)

This achieves O(log n) gate count for coherent control over n-element groups.

---

## Z₈ Coherent Action Demo

Demonstrates `NPlusMap` (n-ary coherent sum eliminator) with cyclic group actions:

**Run:**
```bash
PYTHONPATH=python/src python python/demos/z8_coherent_action_demo.py
```

**What it shows:**

| Group | Summands | Tag Bits | Payload | Total Qubits | Gates |
|-------|----------|----------|---------|--------------|-------|
| Z₄ | 4 × Q | 2 | 1 | 3 | 12 |
| Z₅ | 5 × Q | 3 | 1 | 4 | 25 |
| Z₈ | 8 × Q | 3 | 1 | 4 | 32 |

**Key insight:** NPlusMap compiles directly against the flat ⌈log₂(n)⌉ tag encoding
using per-branch X-flip + multi-controlled gates + X-unflip. This avoids the
binary-tree nesting problem that makes binary PlusMap inadequate for n > 2.

**Properties verified:**
- Block-diagonal unitary structure (each branch acts independently)
- Functoriality (composition law)
- Non-power-of-2 support (Z₅: unused tag values act as identity)

---

## ExpInvolution Demo

Infrastructure test verifying the composition law for exponentials of involutions:

```
exp_i(θ, P) ; exp_i(θ, P) = exp_i(2θ, P)
```

For θ = π/4 and P = Twist (SWAP):
```
exp_i(π/4, twist) ; exp_i(π/4, twist) = exp_i(π/2, twist) = i·SWAP
```

| Format | File | Requirements |
|--------|------|--------------|
| Static output | `exp_twist_demo_output.md` | None (just read) |
| Python script | `exp_twist_demo.py` | Python + pytket |

**Run:**
```bash
cd quant_proto_phase01
PYTHONPATH=python/src python python/demos/exp_twist_demo.py
```

**What it verifies (by extracting unitaries from compiled circuits):**

| Term | Gates | Unitary |
|------|-------|---------|
| `TwistTen(Q,Q)` | 0 | SWAP (permutation only) |
| `exp_i(π/4, twist)` | 1 | UnitaryNqBox (direct unitary synthesis) |
| `exp_i(π/4, twist) ; exp_i(π/4, twist)` | 2 | = exp_i(π/2, twist) |

**Key result:** The composition of two exp_i(π/4) equals exp_i(π/2), verified by:
1. Compiling each term to pytket circuit
2. Extracting actual unitary via `circuit.get_unitary()`
3. Comparing matrices mathematically (up to global phase)

---

## Pauli Conjugation Demo

Verifies the Pauli identity using qubit represented as `I + I` (one-hot encoding):

```
exp_i(π/4, X) ; Z ; exp_i(-π/4, X) = Y
```

Where:
- Qubit = `I + I` (2 one-hot tag wires)
- X = `twist+[I,I]` (structural swap)
- Z = `Z[1]` (Z gate on wire 1)
- Y = `twist ; S[1] ; Sdg[0]` (swap + phases)

| Format | File | Requirements |
|--------|------|--------------|
| Static output | `pauli_conjugation_demo_output.md` | None (just read) |
| Python script | `pauli_conjugation_demo.py` | Python + pytket |

**Run:**
```bash
cd quant_proto_phase01
PYTHONPATH=python/src python python/demos/pauli_conjugation_demo.py
```

**What it verifies:**

| Term | Gates | Logical Unitary |
|------|-------|-----------------|
| `twist+[I,I]` | 1 | Pauli-X |
| `Z[1]` | 1 | Pauli-Z |
| `twist ; S[1] ; Sdg[0]` | 3 | Pauli-Y |
| `exp_i(π/4,X) ; Z ; exp_i(-π/4,X)` | 7 | = Y (up to phase) |

**Key insight:** The one-hot encoding of `I + I` maps:
- Logical |0⟩ → physical |10⟩
- Logical |1⟩ → physical |01⟩

This allows Pauli matrices to be implemented as structural operations (X) or gates on specific wires (Z, Y).

---

## Running Demos

All demos require:
```bash
pip install pytket
```

Run from the `quant_proto_phase01` directory:
```bash
cd quant_proto_phase01
PYTHONPATH=python/src python python/demos/<demo_name>.py
```

### Live Execution Confirmation

All demos display **live compilation confirmation**:
```
============================================================
  LIVE EXECUTION: Demo Name
  All compilations are real - no fabricated output
============================================================

  [COMPILING term_name...] OK - 6 gates on 2 qubits
```

This confirms that compilations are actually running, not displaying pre-recorded output.

### Circuit Diagrams (--circuits flag)

Most demos support the `--circuits` flag to display ASCII circuit diagrams:

```bash
PYTHONPATH=python/src python python/demos/case_demo.py --circuits
```

This will show circuit diagrams like:
```
────────────────────────────────────────────────────────────
Circuit Diagram: QSwitch(H, S)
────────────────────────────────────────────────────────────
q[0]: ───[X]─────●─────[X]─────●─────
              ───│──────────────│───
q[1]: ───────[H]───────────[S]─────
```

**Demos supporting --circuits:**
- `algorithmic_snippets_demo.py`
- `case_demo.py`
- `exp_twist_demo.py`
- `pauli_conjugation_demo.py`
- `qswitch_demo.py`
- `qswitch_term_demo.py`
- `qswitch_abstract_demo.py`
- `qswitch_instantiation_demo.py`
- `quantum_switch_demo.py`
- `short_circuit_demo.py`

---

## HTML Animation (QSwitch)

Open `qswitch_demo.html` in any browser for an interactive demo.

Controls:
- **▶ Play Demo** — animated line-by-line output
- **⏩ Show All** — show everything immediately
- **↺ Reset** — start over

