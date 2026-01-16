# QSwitch Demo - Expected Output

> **Note:** This file documents the expected output in readable Markdown format.
> Run `qswitch_demo.py` or `qswitch_demo_video.py` for console output.

## 1. QSwitch Definition

```
QSwitch : (Q→Q) → (Q→Q) → (QBool ⊗ Q → QBool ⊗ Q)

QSwitch(f, g)(ctrl, data) =
  case ctrl of
  | Zero => (ctrl, g;f data)   -- apply g then f
  | One  => (ctrl, f;g data)   -- apply f then g
```

## 2. Abstract QSwitch(f, g) Circuit

The quantum case elaborates to controlled gates:

```
anti-controlled-g ; f ; controlled-g
```

Expanded circuit structure:

```
Circuit for QSwitch(f, g):
  X q[0];        -- flip ctrl for anti-control
  C-g q[0],q[1]; -- g if ctrl was 0 (now 1)
  X q[0];        -- restore ctrl
  f q[1];        -- f unconditionally
  C-g q[0],q[1]; -- g if ctrl is 1

Wire 0: ctrl (control qubit)
Wire 1: data (target qubit)
```

Verification:
```
ctrl=0: X flips to 1, C-g fires, X flips back, f applied, C-g doesn't fire
        → data sees: g ; f ✓

ctrl=1: X flips to 0, C-g doesn't fire, X flips back, f applied, C-g fires
        → data sees: f ; g ✓
```

## 3. QSwitch(H, S) Instantiation

Substituting f=H, g=S:

```
QSwitch(H, S)(ctrl, data) =
  | Zero => (ctrl, S;H data)
  | One  => (ctrl, H;S data)
```

## 4. QSwitch(H, S) Circuit (First-Order, 2 qubits)

```
Circuit:
  X q[0];
  CS q[0], q[1];
  X q[0];
  H q[1];
  CS q[0], q[1];

Qubits: 2
Gates:  5
```

Semantics:
```
  |0⟩|ψ⟩ → |0⟩(S;H)|ψ⟩
  |1⟩|ψ⟩ → |1⟩(H;S)|ψ⟩
```

## 5. QSwitch(H, S) GOI Form (4 qubits)

Higher-order representation `(QSwitch†) ⊗ QSwitch`:

```
Wire Layout:
  Wire 0: ctrl*  (negative/dual)
  Wire 1: data*  (negative/dual)
  Wire 2: ctrl   (positive)
  Wire 3: data   (positive)

Circuit:
  CSdg q[0], q[1];
  X q[2];
  X q[0];
  H q[1];
  CS q[2], q[3];
  CSdg q[0], q[1];
  X q[2];
  H q[3];
  X q[0];
  CS q[2], q[3];

Qubits: 4
Gates:  10
```

## 6. Summary

| Form | Qubits | Gates | Description |
|------|--------|-------|-------------|
| QSwitch(f,g) abstract | 2 | 5 | X; C-g; X; f; C-g |
| QSwitch(H,S) first-order | 2 | 5 | X; CS; X; H; CS |
| QSwitch(H,S) GOI | 4 | 10 | Doubled conjugation form |
