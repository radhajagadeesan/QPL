# Granthi Demos

Demonstrations of Granthi language features and compilation.

---

## Available Demos

| Demo | File | Description |
|------|------|-------------|
| QSwitch | `qswitch_demo.py` | Higher-order quantum switch combinator |
| ExpInvolution | `exp_twist_demo.py` | Exponentials of structural involutions |
| Pauli Conjugation | `pauli_conjugation_demo.py` | Qubit as I+I, Pauli identity verification |

---

## QSwitch Demo

Demonstrates QSwitch, a higher-order quantum programming combinator.

| Format | File | Requirements |
|--------|------|--------------|
| Static output | `qswitch_demo_output.md` | None (just read) |
| HTML animation | `qswitch_demo.html` | Any browser |
| Python script | `qswitch_demo.py` | Python + pytket |
| Video script | `qswitch_demo_video.py` | Python + pytket |
| Detailed walkthrough | `quantum_switch_demo.py` | Python + pytket |

**Run:**
```bash
cd quant_proto_phase01
PYTHONPATH=src python demos/qswitch_demo.py
```

**What it shows:**
1. QSwitch definition with higher-order type signature
2. Abstract circuit: `anti-controlled-g ; f ; controlled-g`
3. Instantiation: QSwitch(H, S) substitution
4. Compiled circuit: 5 gates on 2 qubits
5. GOI form: 10 gates on 4 qubits (doubled conjugation)

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
