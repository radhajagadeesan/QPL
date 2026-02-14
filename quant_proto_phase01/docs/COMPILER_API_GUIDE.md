# Granthi Compiler API Guide

This guide is for developers extending or embedding the Granthi compiler. It explains the Python core API, compilation functions, and higher-order compilation hooks.

For surface language programming, see `PROGRAMMING_GUIDE.md`.
For IR architecture details, see `IR_DESIGN.md`.

---

## Linearity Checking Warning

> **⚠️ CAUTION: The Python Core API does NOT perform linearity checking.**
>
> ### What Python Checks
>
> The Python compiler **DOES** perform:
> - **Type checking:** Domain and codomain types must match in sequential composition
> - **Wire bounds:** Gate indices must be within the ambient type's width
> - **Structural signatures:** Twist, Assoc, Dist have correct input/output types
>
> ### What Python Does NOT Check
>
> The Python compiler **DOES NOT** perform:
> - **Linearity:** Variables can be used zero times (weakening) or multiple times (contraction)
> - **Context splitting:** The same variable can appear in both sides of a tensor
> - **Unused detection:** Bound variables that are never referenced are silently allowed
>
> ### Consequences
>
> Ill-formed terms compile and produce circuits, but those circuits are **semantically incorrect**.
> For example:
> ```python
> # WRONG: x used twice - compiles but produces incorrect circuit
> Pair(Var("x", Q()), Var("x", Q()))
>
> # WRONG: y never used - compiles but loses information
> LetPair("x", "y", Q(), Q(), pair, Var("x", Q()))
> ```
>
> **The Python compiler trusts that linearity has been verified externally.**
>
> ### Recommendations
>
> 1. **Generate from OCaml:** Use the OCaml surface language (runtime checking) or
>    Linear GADT module (compile-time checking), then bridge to Python.
>
> 2. **Combinator style:** Avoid explicit variables. Use `Seq`, `TenTerm`, `Case` etc.
>    directly on gates and structural operations.
>
> 3. **Manual verification:** If constructing terms with Var/LetPair, carefully audit
>    that each variable is used exactly once.
>
> See `RadhaMSG/SRC_TESTS.md` for the conformance test suite. Linearity rejection tests
> (T3, T6, T8, T10, T12, T14, T15) apply **only to OCaml**, not Python.

---

## Overview

The compiler has two entry points:

| Entry Point | Language | Use Case |
|-------------|----------|----------|
| Surface language | OCaml | User programs with natural syntax |
| Core API | Python | Programmatic AST construction, compiler embedding |

Both produce identical circuits via the same compilation pipeline.

---

## Core API: Types

```python
from lang.types import Q, Unit, Ten, Plus, Arrow, Dual, width

q = Q()                 # Qubit (width 1)
u = Unit()              # Unit (width 0)
qq = Ten(Q(), Q())      # Q ⊗ Q (width 2)
s = Plus(Q(), Q())      # Q + Q (width 2: 1 tag bit + 1 shared payload)
f = Arrow(Q(), Q())     # Q ⊸ Q (width 2: argument + result wires)

w = width(qq)           # Returns 2
w = width(s)            # Returns 2
w = width(f)            # Returns 2
```

### Arrow Type (Linear Function)

Function types `A ⊸ B` are first-class in Python:

```python
from lang.types import Arrow, Q, Ten, width

Arrow(Q(), Q())              # Q ⊸ Q — width 2
Arrow(Ten(Q(), Q()), Q())    # (Q⊗Q) ⊸ Q — width 3
Arrow(Arrow(Q(), Q()), Q())  # (Q⊸Q) ⊸ Q — width 3
```

A function is a **wire bundle**: width(A) argument wires + width(B) result wires.

### Sum Encoding (Option B: Log-Tag + Shared Payload)

Sum types use flat log-sized tag register with shared payload:
- Binary `Plus(A, B)` has width = 1 + max(width(A), width(B))
- Nested sums flatten: `Plus(Plus(Q,Q), Q)` has width 3 (2 tag bits + 1 payload)
- Wire layout: `[tag_bits... | shared_payload...]`
- Tag register stores variant index (0, 1, ..., n-1)

This makes tensor structurals (TwistTen, AssocTen) compile to pure permutations.
Sum structurals (TwistPlus) emit X gates on tag bits.

---

## Core API: Terms

### Composition

```python
from lang.terms import Id, Seq, TenTerm

Id(ty)                  # Identity on type
Seq(f, g)               # Sequential: f ; g
Seq(f, g, h)            # Variadic: f ; g ; h
TenTerm(f, g)           # Parallel: f ⊗ g
```

### Gates

```python
from lang.terms import H, S, X, Y, Z, T, Tdg, Sdg, CX, CZ, CS, CH, CCX, Rz, Rx, Ry, Phase

# All gates take wire index and ambient type
ty = Ten(Q(), Q())

# Single-qubit
H(0, ty)                # Hadamard on wire 0
S(1, ty)                # S gate on wire 1
X(0, ty), Y(0, ty), Z(0, ty)  # Pauli gates
T(0, ty), Tdg(0, ty)    # T and T-dagger
Sdg(0, ty)              # S-dagger

# Two-qubit
CX(0, 1, ty)            # CNOT: control 0, target 1
CZ(0, 1, ty)            # Controlled-Z
CS(0, 1, ty)            # Controlled-S
CH(0, 1, ty)            # Controlled-H

# Parameterized
Rz(0.5, 0, ty)          # Rz(θ) on wire 0
Rx(0.5, 0, ty)          # Rx(θ) on wire 0
Ry(0.5, 0, ty)          # Ry(θ) on wire 0
Phase(0.5, 0, ty)       # Global phase gate

# Three-qubit
ty3 = Ten(Ten(Q(), Q()), Q())
CCX(0, 1, 2, ty3)       # Toffoli
```

### Structural Primitives

All structural primitives compile to **pure wire permutations** (no gates).

```python
from lang.terms import (
    TwistTen, TwistPlus,
    AssocTenL, AssocTenR, AssocPlusL, AssocPlusR,
    DistL, DistR
)

# Tensor isomorphisms
TwistTen(a, b)          # a ⊗ b → b ⊗ a
AssocTenL(a, b, c)      # (a ⊗ b) ⊗ c → a ⊗ (b ⊗ c)
AssocTenR(a, b, c)      # a ⊗ (b ⊗ c) → (a ⊗ b) ⊗ c

# Sum isomorphisms (pure permutations with one-hot encoding)
TwistPlus(a, b)         # a + b → b + a (swaps tags and data)
AssocPlusL(a, b, c)     # (a + b) + c → a + (b + c)
AssocPlusR(a, b, c)     # a + (b + c) → (a + b) + c

# Distributivity (pure permutations)
DistL(a, b, c)          # (a + b) ⊗ c → (a ⊗ c) + (b ⊗ c)
DistR(a, b, c)          # a ⊗ (b + c) → (a ⊗ b) + (a ⊗ c)
```

### Higher-Order Terms

Function types in the Python core are represented through higher-order terms:

```python
from lang.terms import Lam, Apply, FunVar, Feedback

# Lambda abstraction: λx:A. body
# Boundary exposure: x is bound to width(dom) input wires
Lam(name, dom, cod, body)

# Function variable (for substitution)
FunVar(name, dom, cod)    # Variable x : dom ⊸ cod

# Function application
# Boundary splicing: connects argument wires to function's input slot
Apply(f, arg)

# Feedback (reserved for future use)
Feedback(k, body)         # Loop k wires back (not currently compiled)
```

### Full Source Language Terms

For building terms with explicit variable binding:

```python
from lang.terms import Var, Pair, LetPair

# Variable reference: identity on variable's wire range
Var(name, ty)             # x : A (looks up wire range in env)

# Tensor introduction: (t, u) : A ⊗ B
Pair(fst, snd)

# Tensor elimination: let (x, y) = t in u
# Binds x to first width(A) wires, y to next width(B) wires
LetPair(x, y, ty_x, ty_y, pair, body)
```

**Example: Destructuring a pair**
```python
from lang.terms import Var, Pair, LetPair, Id, H, Seq
from lang.types import Q, Ten

# let (x, y) = id : Q⊗Q in (H(x), y)
pair_term = Id(Ten(Q(), Q()))
body = Pair(
    Seq(Var("x", Q()), H(0, Q())),  # Apply H to x
    Var("y", Q())                    # Keep y unchanged
)
lp = LetPair("x", "y", Q(), Q(), pair_term, body)
```

Compilation tracks an **environment** mapping variable names to `(start, width)` wire ranges.

### Exponentials of Involutions

For a structural involution `P : A → A` where P² = id:

```python
from lang.terms import ExpSwap, ExpInvolution

# exp_i(θ, P) : A → A where P : A → A is involutive
# Typing: if P : A → A and P² = id, then ExpInvolution(θ, P) : A → A
ExpInvolution(theta, body, ty_total)

# Atomic exponential of SWAP (building block)
ExpSwap(theta, i, j, ty_total)  # exp(iθ · SWAP) on wires i, j
```

**Type signature:**
```
ExpInvolution : (θ: float, P: Term, ty: Ty) → Term
  where P : A → A and P² = id
  result type: A → A
```

At compile time, `ExpInvolution`:
1. Compiles body P to WirePerm π
2. Verifies π is involutive (π² = identity)
3. Decomposes π into disjoint transpositions
4. Emits `ExpSwap(θ, a, b)` for each transposition (a, b)

---

## Permutation Module

```python
from core.perm import WirePerm, is_involution, decompose_involution

# Create permutation
p = WirePerm([1, 0])    # Swap wires 0 and 1

# Check involution
assert is_involution(p)  # p ∘ p = identity

# Decompose into transpositions
swaps = decompose_involution(p)  # [(0, 1)]
```

---

## Compilation

### Basic Compilation

```python
from compile.to_pytket import compile, Compiled

result: Compiled = compile(term, materialize=False, explain=False)

# Result fields:
result.circuit          # pytket Circuit
result.perm             # WirePerm (final wire permutation)
result.log              # List[str] if explain=True
```

### Higher-Order Compilation

Higher-order terms (Lam, Apply, FunVar) are compiled directly via **cup/cap wiring**:

- A function `A ⊸ B` is physically width(A) + width(B) wires
- `Lam` exposes argument wires as input boundary
- `Apply` connects argument wires to function's input slot (boundary splicing)

```python
from compile.to_pytket import compile

# compile() handles higher-order terms directly
result = compile(lam_apply_term)
```

---

## Involution Certification (exp_i)

The compiler provides involution checking for `ExpInvolution`. The body must be a
**wire permutation involution** (structural operation that compiles to a self-inverse
permutation with no gates).

```python
from lang.terms import TwistTen, ExpInvolution
from lang.types import Q, Ten
from compile.to_pytket import compile

# TwistTen (SWAP) is involutive: SWAP ∘ SWAP = id
swap = TwistTen(Q(), Q())
ty = Ten(Q(), Q())

# Create exp(iθ · SWAP)
term = ExpInvolution(theta=0.5, body=swap, ty_total=ty)

# Compile - verifies involution and emits ExpSwap atoms
result = compile(term, materialize=True)
# Produces XXPhase, YYPhase, ZZPhase gates
```

If the body is not a wire-permutation involution, compilation raises an error:
```
InvolutionError: ExpInvolution body must be involutive (π² ≠ id)
```

**Note:** `TwistPlus` on sum types emits an X gate (tag flip), not a wire permutation.
Use `TwistTen` on tensor types for ExpInvolution.

---

## Example: Building and Compiling

```python
from lang.types import Q, Ten
from lang.terms import Seq, H, CX
from compile.to_pytket import compile

# Build term
ty = Ten(Q(), Q())
bell = Seq(H(0, ty), CX(0, 1, ty))

# Compile
result = compile(bell)

# Inspect
print(f"Qubits: {result.circuit.n_qubits}")
print(f"Gates: {result.circuit.n_gates}")
for cmd in result.circuit.get_commands():
    print(f"  {cmd}")
```

---

## Example: QSwitch via Core API

```python
from lang.terms import H, S, Seq, CS, CH, X
from lang.types import Q, Ten
from compile.to_pytket import compile

ty = Ten(Q(), Q())

# QSwitch(H, S): case ctrl of Left => S;H | Right => H;S
# Anti-control pattern: X; controlled-gates; X for left branch
qswitch_hs = Seq(
    X(0, ty),         # flip tag for anti-control
    CS(0, 1, ty),     # controlled-S (left branch)
    CH(0, 1, ty),     # controlled-H (left branch)
    X(0, ty),         # restore tag
    CH(0, 1, ty),     # controlled-H (right branch)
    CS(0, 1, ty),     # controlled-S (right branch)
)

result = compile(qswitch_hs)
# 6 gates on 2 qubits
```

---

## Example: Structural Operations

```python
from lang.types import Q, Ten, Plus
from lang.terms import TwistTen, TwistPlus, DistR
from compile.to_pytket import compile

a, b, c = Q(), Q(), Q()

# TwistTen: Q ⊗ Q → Q ⊗ Q (pure wire permutation)
twist_ten = TwistTen(a, b)
result = compile(twist_ten)
assert result.circuit.n_gates == 0  # No gates!
assert result.perm.new_to_old == [1, 0]  # Swaps wires

# TwistPlus: Q + Q → Q + Q (X gate on tag bit)
twist_plus = TwistPlus(a, b)
result = compile(twist_plus)
assert result.circuit.n_gates == 1  # X gate on tag
# Identity wire perm (tag flip is symbolic, lowered to X gate)

# DistR: Q ⊗ (Q + Q) → (Q ⊗ Q) + (Q ⊗ Q) (pure permutation)
dist = DistR(a, b, c)
result = compile(dist)
assert result.circuit.n_gates == 0  # No gates!
```

---

## Running Python Programs

```bash
cd quant_proto_phase01
PYTHONPATH=src python my_program.py
```

---

## Further Reading

- `API_REFERENCE.md` — Complete API signatures
- `IR_DESIGN.md` — IR architecture and compilation semantics
- `demos/python/qswitch_demo.py` — Working higher-order example
- `demos/python/qswitch_abstract_circuit_demo.py` — Abstract QSwitch circuit diagrams (no instantiation)
- `demos/python/qswitch_instantiation_demo.py` — QSwitch[H,H] vs QSwitch[H,S] with simplification analysis
- `surface/demos/` — OCaml E2E demos (full pipeline to circuits)
