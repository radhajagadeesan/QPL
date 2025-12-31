# Phase 3 Extraction & Normalization

**Developer-Facing Algorithmic Checklist & Pseudocode**  
**Companion to:** Phase 3 GOI Design Specification  
**Audience:** Implementing engineer  

---

## 0. Purpose of This Document

This document gives **implementation-grade guidance** for Phase 3, focusing on:

- GOI normalization
- feedback ("yanking") eliminability checks
- extraction logic

It is written so a developer can implement Phase 3 **without making semantic decisions**.

All algorithms here are **sound-by-construction** and intentionally incomplete.

---

## 1. Core Data Structures (Assumed)

### 1.1 WirePerm

Assumed existing from Phases 0–2.

Capabilities:
- `compose(p: WirePerm) -> WirePerm`
- `apply_new_to_old(i: int) -> int`
- `restrict(indices: Set[int]) -> WirePerm`

---

### 1.2 GateAtom

Minimal interface:

```python
class GateAtom:
    gate_name: str
    wires: List[int]  # physical wire indices
```

Constraints:
- Gate atoms are **opaque**.
- No algorithm may rewrite inside a gate atom.
- Only wire indices may change.

---

### 1.3 LoopSpec (Canonical Phase 3 Form)

```python
class LoopSpec:
    k: int  # number of loop wires
```

Interpretation:
- Loop the last `k` output wires back to the last `k` input wires.

---

### 1.4 GOIArtifact

```python
class GOIArtifact:
    n_in: int
    n_out: int
    perm: WirePerm
    atoms: List[GateAtom]
    loops: List[LoopSpec]
```

Phase 3 assumes **at most one** loop, but code should tolerate a list.

---

## 2. Normalization Pass

### 2.1 Goal

Push *all structural effects* into `WirePerm`, leaving gate atoms untouched.

---

### 2.2 Normalization Invariant (Firewall)

> Structural rewrites may move gates around, but never rewrite inside a gate atom.

---

### 2.3 normalize_goi(goi)

```python
def normalize_goi(goi: GOIArtifact) -> GOIArtifact:
    perm = goi.perm
    new_atoms = []

    for atom in goi.atoms:
        new_wires = [perm.apply_new_to_old(i) for i in atom.wires]
        new_atoms.append(GateAtom(atom.gate_name, new_wires))

    return GOIArtifact(
        n_in=goi.n_in,
        n_out=goi.n_out,
        perm=identity_perm(goi.n_out),
        atoms=new_atoms,
        loops=goi.loops
    )
```

Explanation:
- All permutation effects are pushed onto atom wire indices.
- The resulting `perm` is reset to identity.
- Loop structure is preserved verbatim.

---

## 3. Loop Wire Identification

### 3.1 Canonical Loop Wire Set

For a loop of size `k`:

```python
def loop_wires(goi: GOIArtifact, loop: LoopSpec) -> Set[int]:
    start = goi.n_out - loop.k
    return set(range(start, goi.n_out))
```

Assumption:
- Output and input loop wires align canonically.

---

## 4. Yankability (Eliminability) Check

### 4.1 Definition

A loop is **yankable** iff:

> No gate atom touches any loop wire after normalization.

---

### 4.2 is_yankable(goi)

```python
def is_yankable(goi: GOIArtifact) -> bool:
    for loop in goi.loops:
        L = loop_wires(goi, loop)
        for atom in goi.atoms:
            if any(w in L for w in atom.wires):
                return False
    return True
```

Notes:
- This is deliberately conservative.
- Any false negative is acceptable; false positives are not.

---

## 5. Boundary Permutation Collapse

### 5.1 Purpose

When a loop is yankable, compute its **net routing effect** on the external boundary.

---

### 5.2 collapse_feedback(goi)

```python
def collapse_feedback(goi: GOIArtifact) -> WirePerm:
    # Conceptual outline:
    # 1. Treat loop wires as internal.
    # 2. Compute induced permutation on external wires only.

    external = set(range(goi.n_out - goi.loops[0].k))
    return goi.perm.restrict(external)
```

Explanation:
- Loop wires are existentially eliminated.
- Only the boundary-visible routing is retained.

Implementation detail:
- Exact implementation depends on WirePerm representation.

---

## 6. Extraction Pass

### 6.1 try_extract(goi)

```python
def try_extract(goi: GOIArtifact):
    goi = normalize_goi(goi)

    if not is_yankable(goi):
        return goi  # ResidualGOI

    new_perm = collapse_feedback(goi)

    return (
        goi.atoms,  # identical atom list
        new_perm
    )
```

---

## 7. Determinism Checklist

Before returning an extracted result, verify:

- Atom order is unchanged from compilation order.
- Atom wire indices are fully concrete.
- Boundary permutation is deterministic.

---

## 8. Failure Semantics

Failure to extract:

- is **not an error**
- must return the full residual `GOIArtifact`
- must preserve all structural and atomic information

---

## 9. Forward Compatibility Notes

### 9.1 ZX Integration

Future passes may:
- rewrite `GOIArtifact` before `try_extract`
- prove additional yankability conditions

They must never alter extracted results.

---

### 9.2 Analytic / Lie Operators

- Treated as `GateAtom`s
- Automatically respected by yankability check

---

## 10. Developer Summary

- Implement normalization first.
- Then implement yankability conservatively.
- Then collapse routing when allowed.
- Never rewrite gate atoms.
- Never error on failure to extract.

Phase 3 correctness relies on *what you refuse to do*, not what you attempt.

