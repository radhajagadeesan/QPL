# QSwitch Demos

Demonstrations of QSwitch, a higher-order quantum programming combinator.

## Quick Start

| Format | File | Requirements |
|--------|------|--------------|
| Static output | `qswitch_demo_output.md` | None (just read) |
| HTML animation | `qswitch_demo.html` | Any browser |
| Python script | `qswitch_demo.py` | Python + pytket |
| Video script | `qswitch_demo_video.py` | Python + pytket |
| Detailed walkthrough | `quantum_switch_demo.py` | Python + pytket |

---

## 1. Static Output (`qswitch_demo_output.md`)

For those who just want to see the results without running code.

**View:** Open in any markdown viewer or text editor.

---

## 2. HTML Animation (`qswitch_demo.html`)

Interactive browser-based demo with play/pause controls.

**View:** Open in any web browser (works offline).

Controls:
- **▶ Play Demo** — animated line-by-line output
- **⏩ Show All** — show everything immediately
- **↺ Reset** — start over

---

## 3. Runnable Script (`qswitch_demo.py`)

For those with the infrastructure installed.

**Requirements:**
```bash
pip install pytket
```

**Run:**
```bash
cd quant_proto_phase01
PYTHONPATH=src python demos/qswitch_demo.py
```

---

## 4. Video Recording Script (`qswitch_demo_video.py`)

For creating video demos with visual timing.

**Direct run:**
```bash
cd quant_proto_phase01
PYTHONPATH=src python demos/qswitch_demo_video.py
```

**With asciinema:**
```bash
pip install asciinema
cd quant_proto_phase01
asciinema rec -c "PYTHONPATH=src python demos/qswitch_demo_video.py" qswitch_demo.cast
asciinema play qswitch_demo.cast
```

---

## 5. Detailed Walkthrough (`quantum_switch_demo.py`)

Educational demo showing the full pipeline from surface syntax to circuit.

**Run:**
```bash
cd quant_proto_phase01
PYTHONPATH=src python demos/quantum_switch_demo.py
```

---

## What the Demo Shows

1. **Part 1: QSwitch Definition** — Higher-order type signature
2. **Part 2: Abstract Circuit** — `anti-controlled-g ; f ; controlled-g`
3. **Part 3: Instantiation** — QSwitch(H, S) substitution
4. **Part 4: Compiled Circuit** — 5 gates on 2 qubits
5. **Part 5: GOI Form** — 10 gates on 4 qubits (doubled conjugation)

**Key insight:** QSwitch elaborates to controlled gates:
```
X[0]; C-g[0,1]; X[0]; f[1]; C-g[0,1]
```

For QSwitch(H, S):
```
X[0]; CS[0,1]; X[0]; H[1]; CS[0,1]
```
