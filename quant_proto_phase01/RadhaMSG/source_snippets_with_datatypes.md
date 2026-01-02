# Rewritten Source-Level Algorithmic Snippets (with Surface `datatype` Decls)

**Notes (implementation-facing):**
- These are **surface programs** intended to elaborate into the locked 0–4C core.
- `(+)` is **monoidal** (not a coproduct). The `datatype` blocks below are **surface declarations** that expand to a chosen `(+)`/`⊗` representation; they do **not** assume `inl/inr` or coproduct laws.
- `Nat[k]` is treated as a **compile-time index** (finite, non-recursive), consistent with the certified fragment.

---

## Snippet 6.1 — Deutsch–Jozsa (Unitary Core)

### Datatypes / type aliases used

```ml
datatype Unit = U of Unit

(* A single classical bit at the boundary (surface-level). *)
datatype Bit =
  | Zero of Unit
  | One  of Unit

(* Finite index used at compile time (no recursion, no runtime iteration). *)
datatype Nat[k] =
  | Z  of Unit
  | S1 of Unit
  | S2 of Unit
  ...
  | Sk of Unit

(* Opaque quantum register type families (compile-time indexed). *)
type QBit
type QReg[n]      (* n is a Nat[k]-index / parameter *)
```

### Assumed primitives (opaque unitary atoms / library)

```ml
unitary atom H     : QBit ⊸ QBit
unitary atom Hn    : QReg[n] ⊸ QReg[n]
unitary atom Uf    : (QReg[n] ⊗ QBit) ⊸ (QReg[n] ⊗ QBit)

(* preparations (standard library) *)
unitary atom ket0n : Unit ⊸ QReg[n]
unitary atom ket1  : Unit ⊸ QBit
```

### Program

```ml
def deutschJozsa[n] : Unit ⊸ (QReg[n] ⊗ QBit) =
  λu.
    let x  = Hn (ket0n u) in
    let y  = H  (ket1  u) in
    let (x1, y1) = Uf (x ⊗ y) in
    let x2 = Hn x1 in
    (x2 ⊗ y1)
```

---

## Snippet 6.2 — Hidden Subgroup Problem (Standard Oracle Form)

### Datatypes / type aliases used

```ml
datatype Unit = U of Unit

(* Abstract group and output types (opaque, user- or library-supplied). *)
type G
type X
```

### Assumed primitives

```ml
unitary atom uniformG : Unit ⊸ G
unitary atom zeroX    : Unit ⊸ X
unitary atom Uf       : (G ⊗ X) ⊸ (G ⊗ X)
unitary atom QFTG     : G ⊸ G
```

### Program

```ml
def HSP_core : Unit ⊸ (G ⊗ X) =
  λu.
    let g  = uniformG u in
    let x  = zeroX    u in
    let (g1, x1) = Uf (g ⊗ x) in
    let g2 = QFTG g1 in
    (g2 ⊗ x1)
```

---

## Snippet 6.3 — Hidden Subgroup Problem (Phase-Kickback Variant)

### Datatypes / type aliases used

```ml
datatype Unit = U of Unit

type G
type X
type ZN            (* e.g. a finite phase register; abstract here *)
```

### Assumed primitives

```ml
unitary atom uniformG : Unit ⊸ G
unitary atom chiZN    : Unit ⊸ ZN
unitary atom kick     : (G ⊗ ZN) ⊸ (G ⊗ ZN)
unitary atom QFTG     : G ⊸ G
```

### Program

```ml
def HSP_phase : Unit ⊸ G =
  λu.
    let g  = uniformG u in
    let z  = chiZN    u in
    let (g1, _z1) = kick (g ⊗ z) in
    let g2 = QFTG g1 in
    g2
```

---

## Snippet 6.4 — Simon’s Algorithm (Unitary Core)

### Datatypes / type aliases used

```ml
datatype Unit = U of Unit

(* Finite index used at compile time. *)
datatype Nat[k] =
  | Z  of Unit
  | S1 of Unit
  | S2 of Unit
  ...
  | Sk of Unit

type Z2n[n]        (* n is a Nat[k]-index / parameter *)
type Y
```

### Assumed primitives

```ml
unitary atom uniformZ2n : Unit ⊸ Z2n[n]
unitary atom zeroY      : Unit ⊸ Y
unitary atom Uf         : (Z2n[n] ⊗ Y) ⊸ (Z2n[n] ⊗ Y)
unitary atom QFT2n      : Z2n[n] ⊸ Z2n[n]
```

### Program

```ml
def Simon_core[n] : Unit ⊸ (Z2n[n] ⊗ Y) =
  λu.
    let x = uniformZ2n u in
    let y = zeroY      u in
    let (x1, y1) = Uf (x ⊗ y) in
    let x2 = QFT2n x1 in
    (x2 ⊗ y1)
```

---
