# Granthi Demos

Demonstrations of Granthi language features and compilation.

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
| ExpInvolution | `exp_twist_demo.py` | Exponentials of structural involutions |
| Pauli Conjugation | `pauli_conjugation_demo.py` | Qubit as I+I, Pauli identity verification |

### OCaml Demos

| Demo | File | Description |
|------|------|-------------|
| QSwitch (OCaml) | `surface/demos/qswitch_demo.ml` | QSwitch in OCaml surface language |
| QSwitch (HO) | `surface/demos/qswitch_ho_demo.ml` | Higher-order QSwitch showing type signature |

---

## QSwitch Demos

Multiple demos showing different aspects of the quantum switch combinator.

### QSwitch (pipeline) — `quantum_switch_demo.py`

Comprehensive demo showing the full Granthi compiler pipeline on QSwitch:

**Run:**
```bash
PYTHONPATH=src python demos/quantum_switch_demo.py
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
PYTHONPATH=src python demos/qswitch_demo.py
```

### QSwitch (term) — `qswitch_term_demo.py`

Shows QSwitch built as an actual Term using Case (copairing):

```
QSwitch[H,S] = DistR(I,I,Q) ; Case(I⊗Q, I⊗Q, H;S, S;H)
```

**Run:**
```bash
PYTHONPATH=src python demos/qswitch_term_demo.py
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
PYTHONPATH=src python demos/qswitch_abstract_demo.py
```

**What it shows:**
1. Arrow type widths: Q⊸Q has width 2
2. Input wire layout: [f_arg | f_res | g_arg | g_res | tag | x] = 6 wires
3. Output wire layout: [tag | x'] = 2 wires
4. LetPair structure for destructuring
5. Instantiation with H, S

### QSwitch (OCaml HO) — `surface/demos/qswitch_ho_demo.ml`

OCaml surface language demo showing higher-order QSwitch:

**Run:**
```bash
cd surface && dune exec demos/qswitch_ho_demo.exe
```

**What it shows:**
1. QSwitch type: `(Q→Q) → (Q→Q) → ((I+I)⊗Q → (I+I)⊗Q)`
2. Instantiation with H and S
3. Elaboration to Core IR with controlled gates

### QSwitch (abstract circuit) — `qswitch_abstract_circuit_theory_demo.py` (THEORY ONLY)

Shows the **abstract QSwitch circuit structure** in curried form with NO instantiation:

```
QSwitch = λb. λf. λg. λx. case b of
            | Left(u)  ⇒ (Left(u), f(g(x)))
            | Right(u) ⇒ (Right(u), g(f(x)))
```

**Run:**
```bash
PYTHONPATH=src python demos/qswitch_abstract_circuit_theory_demo.py
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
PYTHONPATH=src python demos/qswitch_instantiation_demo.py
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
PYTHONPATH=src python demos/qswitch_curried_theory_demo.py
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
PYTHONPATH=src python demos/exp_twist_demo.py
```

**What it verifies (by extracting unitaries from compiled circuits):**

| Term | Gates | Unitary |
|------|-------|---------|
| `TwistTen(Q,Q)` | 0 | SWAP (permutation only) |
| `exp_i(π/4, twist)` | 3 | XXPhase, YYPhase, ZZPhase |
| `exp_i(π/4, twist) ; exp_i(π/4, twist)` | 6 | = exp_i(π/2, twist) |

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
PYTHONPATH=src python demos/pauli_conjugation_demo.py
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
PYTHONPATH=src python demos/<demo_name>.py
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
PYTHONPATH=src python demos/case_demo.py --circuits
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

---

## Video Recording (QSwitch)

For creating video demos with visual timing:

```bash
cd quant_proto_phase01
PYTHONPATH=src python demos/qswitch_demo_video.py
```

With asciinema:
```bash
pip install asciinema
asciinema rec -c "PYTHONPATH=src python demos/qswitch_demo_video.py" qswitch_demo.cast
asciinema play qswitch_demo.cast
```
