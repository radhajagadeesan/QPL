# Worked Example: Surface → Phase 4C (GOI‑Corrected)

---

## 1. Goal

Demonstrate a structural involution and exponential **with explicit GOI meaning**.

---

## 2. Surface Program

```ml
datatype Bool[A,B] =
  | F of A
  | T of B

swap : Bool[A,B] → Bool[B,A]
swap = λx.
  case x of
    F(a) => T(a)
    T(b) => F(b)

phaseSwap = expᵢ(π/7, swap)
```

---

## 3. Elaboration

- `Bool[A,B]` ≔ `A (+) B`
- `swap` elaborates to structural `(+)` re‑indexing
- No surface constructs remain

---

## 4. GOI Compilation

Compile `swap` with `materialize=False`:

```
WirePerm = p_swap   (on GOI boundary)
```

Check:

```
p_swap ∘ p_swap = id
```

This is involution **on the GOI interface**, not outputs.

---

## 5. Exponential

Because `swap` is certified involutive:

```
expᵢ(π/7, swap)
```

is accepted and elaborates to an opaque unitary atom.

---

## 6. Result

```
(Circuit = [ExpI(π/7, p_swap)], WirePerm = p_swap)
```

No residual GOI. No Phase 4B.

---

## 7. Key Takeaway

All reasoning occurs on **GOI boundary permutations**.
