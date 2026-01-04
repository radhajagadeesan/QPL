# QSwitch(H, S) Demo - Expected Output

This document shows the expected output from the QSwitch demo for those who want to see the results without running the code.

## 1. QSwitch Definition

```
QSwitch(f, g) : QBool ⊗ Q → QBool ⊗ Q

  case ctrl of
  | Zero => (ctrl, g;f data)   -- apply g then f
  | One  => (ctrl, f;g data)   -- apply f then g
```

## 2. QSwitch(H, S) Instantiation

```
QSwitch(H, S)(ctrl, data) =
  | Zero => (ctrl, S;H data)
  | One  => (ctrl, H;S data)

Semantics:
  |0⟩|ψ⟩ → |0⟩(S;H)|ψ⟩
  |1⟩|ψ⟩ → |1⟩(H;S)|ψ⟩
```

## 3. First-Order Circuit (2 qubits)

When applied directly:

```
Circuit (ctrl=q[0], data=q[1]):
  X q[0];
  CS q[0], q[1];
  X q[0];
  H q[1];
  CS q[0], q[1];

Qubits: 2
Gates:  5
```

## 4. GOI Conjugation Form (4 qubits)

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

## 5. GOI Verification: twist ⊗ twist = id

```
twist⊗_{Q,Q} GOI artifact:
  perm=[1, 0, 3, 2]
  atoms=()

After trace (twist ; twist):
  perm=[0, 1, 2, 3]  (identity)
  atoms=()

Result: twist ; twist = id ✓
```

## 6. GOI Verification: H;S Composition

```
⟦H⟧ = (H ⊗ H) on 2 wires
⟦S⟧ = (Sdg ⊗ S) on 2 wires

After goi_seq + execute_trace:
  Wire 0 (Q*): Sdg, H  = (H;S)† = S†;H†
  Wire 1 (Q):  H, S    = H;S

Total: 4 gates on 2 qubits ✓
```
