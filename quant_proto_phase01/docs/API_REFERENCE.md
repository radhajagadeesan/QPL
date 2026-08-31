# Granthi API Reference

Complete reference for types, terms, and compilation functions.

---

## Linearity Warning

> **⚠️ The Python Core API performs type checking but NOT linearity checking.**
>
> - **Type checking:** ✅ Domain/codomain matching, wire bounds, structural signatures
> - **Linearity checking:** ❌ Variables can be duplicated or discarded without error
>
> Ill-formed terms compile to **incorrect circuits**. See `COMPILER_API_GUIDE.md` for details
> and recommendations. For linearity guarantees, use the OCaml surface language or Linear GADT module.

---

## Types (`python/src/lang/types.py`)

| Type | Description | Width |
|------|-------------|-------|
| `Q()` | Single qubit | 1 |
| `Unit()` | Unit type (alias: `I()`) | 0 |
| `Ten(a, b)` | Tensor product a ⊗ b | width(a) + width(b) |
| `Plus(a, b)` | Sum type a + b (Option B) | ceil(log2(n)) + max(width(Aᵢ)) |
| `Dual(a)` | Dual type a* | width(a) (self-dual) |
| `Arrow(a, b)` | Linear function a ⊸ b | width(a) + width(b) |

### Arrow Type (Linear Function)

`Arrow(A, B)` represents the linear function type `A ⊸ B`.

```python
from lang.types import Arrow, Q, Ten, width

arr = Arrow(Q(), Q())           # Q ⊸ Q — width 2
width(arr)                       # 2 (argument + result wires)

arr2 = Arrow(Ten(Q(), Q()), Q())  # (Q⊗Q) ⊸ Q — width 3
width(arr2)                       # 3

# Nested functions
arr3 = Arrow(Arrow(Q(), Q()), Q())  # (Q⊸Q) ⊸ Q — width 3
width(arr3)                          # 3
```

A function value is a **wire bundle**: argument slot + result slot.

### Dual Type

`Dual(A)` represents the dual object A* in the compact-closed category.
Since all our types are self-dual, `width(Dual(A)) = width(A)`.

```python
from lang.types import Dual, dual, Q, Ten

Dual(Q())           # Q* — width 1
dual(Q())           # Same as Dual(Q())
dual(dual(Q()))     # Q — involutive: dual(dual(A)) = A
```

### Option B: Flat Log-Tag Encoding

Sum types use a flat log-sized tag register + shared payload:
- `Plus(A, B)` has ceil(log2(n)) tag qubits + max(width(Aᵢ)) shared payload
- Nested sums flatten: `Plus(Plus(Q,Q), Q)` = ceil(log2(3))=2 tags + max(1)=1 = 3 wires
- Wire layout: `[tag₀ | ... | tag_{k-1} | payload₀ | ... | payload_{W-1}]`
- Invariant: tag encodes index i < n; unused payload wires are |0⟩

**Functions:**
```python
from lang.types import Q, I, Ten, Plus, width, tag_width, payload_width

width(ty: Ty) -> int           # Number of physical wires
tag_width(ty: Ty) -> int       # Number of tag qubits (0 for non-Plus)
payload_width(ty: Ty) -> int   # Shared payload width (= width for non-Plus)
data_width(ty: Ty) -> int      # Data wires excluding tags (= payload_width for Plus)
tag_count(ty: Ty) -> int       # Number of tag qubits (same as tag_width)
flatten_plus(ty: Ty) -> list   # Flatten Plus tree into leaf summands
flatten_tensor(ty: Ty) -> list # Flatten Ten tree into factors
```

---

## Terms (`python/src/lang/terms.py`)

### Identity and Composition

| Term | Signature | Description |
|------|-----------|-------------|
| `Id(ty)` | `Id(ty: Ty)` | Identity on type |
| `Seq(f, g, ...)` | `Seq(*terms)` | Sequential composition (variadic) |
| `TenTerm(f, g)` | `TenTerm(f, g)` | Parallel composition f ⊗ g |

### Structural Isomorphisms

Tensor structurals compile to **pure wire permutations** (no gates).
Sum structurals compile to **symbolic tag permutations** (lowered to gates late).

| Term | Type Signature |
|------|----------------|
| `TwistTen(a, b)` | a ⊗ b → b ⊗ a |
| `TwistPlus(a, b)` | a + b → b + a |
| `AssocTenL(a, b, c)` | (a ⊗ b) ⊗ c → a ⊗ (b ⊗ c) |
| `AssocTenR(a, b, c)` | a ⊗ (b ⊗ c) → (a ⊗ b) ⊗ c |
| `AssocPlusL(a, b, c)` | (a + b) + c → a + (b + c) |
| `AssocPlusR(a, b, c)` | a + (b + c) → (a + b) + c |
| `DistL(a, b, c)` | (a + b) ⊗ c → (a ⊗ c) + (b ⊗ c) |
| `DistR(a, b, c)` | a ⊗ (b + c) → (a ⊗ b) + (a ⊗ c) |
| `UndistL(a, b, c)` | (a ⊗ c) + (b ⊗ c) → (a + b) ⊗ c |
| `UndistR(a, b, c)` | (a ⊗ b) + (a ⊗ c) → a ⊗ (b + c) |

### Control Flow

| Term | Type | Description |
|------|------|-------------|
| `Case(ty_left, ty_right, left, right)` | (A + B) → (C + D) | Bifunctorial case (same as PlusMap) |
| `PlusMap(ty_left, ty_right, left, right)` | (A + B) → (C + D) | Bifunctorial action (⊕-Map) |

**Case signature:**
```python
Case(
    ty_left: Ty,    # Type A (left payload type)
    ty_right: Ty,   # Type B (right payload type)
    left: Term,     # Left branch: A → C
    right: Term     # Right branch: B → D
) -> Term
# Returns: term of type (A + B) → (C + D)
# Tag is preserved: left stays left, right stays right
```

**PlusMap signature (⊕-Map):**
```python
PlusMap(
    ty_left: Ty,    # Type A (left input type)
    ty_right: Ty,   # Type B (right input type)
    left: Term,     # Left branch: A → C
    right: Term     # Right branch: B → D
) -> Term
# Returns: term of type (A + B) → (C + D)
# Tag is preserved: left stays left, right stays right
```

**Compilation (both Case and PlusMap):** Uses the anti-control pattern:
1. X[tag] — flip tag bit
2. Controlled-left — fires when tag was originally 0 (Left)
3. X[tag] — flip tag back
4. Controlled-right — fires when tag was originally 1 (Right)

On superposition inputs, both branches execute coherently (indefinite causal order).

**Case vs PlusMap:**
- Case and PlusMap are semantically identical: both are `f ⊕ g : (A + B) → (C + D)`
- For true copairing (both branches produce the same type C), use branches where C = D

### N-ary Sum Eliminator

| Term | Type | Description |
|------|------|-------------|
| `NPlusMap(summand_types, branches)` | (A₁+...+Aₙ) → (B₁+...+Bₙ) | N-ary coherent sum eliminator |

**NPlusMap signature:**
```python
NPlusMap(
    summand_types: tuple,  # (A₁, ..., Aₙ) — input summand types
    branches: tuple        # (f₁, ..., fₙ) — one morphism per summand, fᵢ : Aᵢ → Bᵢ
) -> Term
# Returns: term of type (A₁ + ... + Aₙ) → (B₁ + ... + Bₙ)
# Domain/codomain built as balanced binary Plus trees via build_plus_tree()
```

**OCaml Linear DSL equivalent:**
```ocaml
val omapn : _ ty array
         -> (unit, [`Lolli of 'a * 'b]) prog array
         -> (unit, [`Lolli of 'c * 'd]) prog
(* omapn summand_types branches — requires at least 2 summand types *)
```

**Compilation:** Per-branch X-flip + multi-controlled gates + X-unflip on flat ⌈log₂(n)⌉ tag encoding.

**Open branches (free variables):** NPlusMap branches may reference variables
bound in the outer environment (free vars). The compiler detects these via
`_ordered_free_vars`, sets up a sub-env mapping names to wire positions,
substitutes deferred-Lam values from `term_env`, and emits the resulting
sub-circuit gates under multi-control. This mirrors the binary `PlusMap`
open-branch path — the deferred-Lam mechanism propagates through any depth
of nested PlusMap/NPlusMap.

**OCaml frontend (higher-order):**
`o_n_plusmap : 'c ty -> ('parts, 'c) branches -> ('g, 'parts) partition -> Lolli oterm`.

Each branch is typed under its **own** branch-local context and carries its
summand type in `BCons`; the `partition` witness proves those contexts are a
total, disjoint cover of `'g`. There is no padding combinator — inactive
resources are identity-transported at lowering time.

If a resource is needed by **every** branch, it does not belong in a
branch-local context: route it through the sum payload with `dist_r` and
recover the tag-preserving form with `undist`. See
`ocaml/demos/n_plusmap_e2e.ml` and `docs/BRANCH_CONTEXT_LINEARITY.md`.

**Type helper:**
```python
build_plus_tree(types: list[Ty]) -> Ty
# Builds balanced binary Plus tree: build_plus_tree([A,B,C,D]) == Plus(Plus(A,B), Plus(C,D))
# Inverse of flatten_plus
```

### Wire-Level Identity (n-ary dist/factor)

| Term | Type | Description |
|------|------|-------------|
| `WireIdentity(dom, cod)` | A → B (width-preserving) | Wire-level identity between two types of equal width |

**Use case:** The n-ary distributivity primitives `n_dist` and `n_factor`
(OCaml frontend) emit as `WireIdentity` at the Bridge level. They convert
between `Z_n ⊗ A` and `⊕^n (b ⊗ A)` at the type level but are identity at
the wire level (both forms share the flat n-ary encoding).

**Type check:** Requires `width(dom) == width(cod)`. **Compile:** zero gates.

**OCaml frontend equivalents:**
```ocaml
val n_dist   : 'a ty array -> 'b ty -> (unit, [`Lolli of 'in_ty * 'out_ty]) prog
val n_factor : 'a ty array -> 'b ty -> (unit, [`Lolli of 'in_ty * 'out_ty]) prog
```

See `ocaml/demos/curried_select_3_ndist_e2e.ml` for the textbook curried
`select_n` formula using these primitives.

### Phase-Weighted Bifunctors

| Term | Type | Description |
|------|------|-------------|
| `PhasedPlusMap(theta, ty_left, ty_right, left, right)` | (A + B) → (C + D) | Phase-weighted bifunctor |
| `PhasedControl(name, arity, phases, dt_rep, a_ty)` | D ⊗ A → D ⊗ A | N-ary phased control |

**PhasedPlusMap signature:**
```python
PhasedPlusMap(
    theta: float,       # Phase angle (z = e^{iθ})
    ty_left: Ty,        # Type A (left input type)
    ty_right: Ty,       # Type B (right input type)
    left: Term,         # Left branch: A → C
    right: Term         # Right branch: B → D
) -> Term
# Returns: term of type (A + B) → (C + D)
# Applies phase e^{iθ} to left branch, identity phase to right
```

**PhasedControl signature:**
```python
PhasedControl(
    name: str,          # Datatype name (for diagnostics)
    arity: int,         # Number of branches k
    phases: list,       # List of k floats (angles θᵢ in radians)
    dt_rep: Ty,         # Datatype representation (sum type)
    a_ty: Ty            # Payload type A
) -> Term
# Returns: term of type D ⊗ A → D ⊗ A where D has k branches
# Applies phase e^{iθᵢ} when control is in branch i
# Uses efficient ⌈log₂(k)⌉ tag encoding
```

**Compilation:**
- PhasedPlusMap: X gates to select tag pattern, controlled-U1 for phase, X gates restore
- PhasedControl: For each non-trivial phase, applies same pattern with multi-controlled U1
- Trivial phases (θ = 0, i.e., z = +1) are optimized away

### Gates

All gates take wire indices and an ambient type `ty_total`.

**Single-qubit gates:**

| Gate | Signature | Description |
|------|-----------|-------------|
| `H(i, ty)` | Hadamard | |
| `X(i, ty)` | Pauli-X | |
| `Y(i, ty)` | Pauli-Y | |
| `Z(i, ty)` | Pauli-Z | |
| `S(i, ty)` | S gate (π/2 phase) | |
| `Sdg(i, ty)` | S-dagger | |
| `T(i, ty)` | T gate (π/4 phase) | |
| `Tdg(i, ty)` | T-dagger | |

**Parameterized single-qubit gates:**

| Gate | Signature | Description |
|------|-----------|-------------|
| `Rx(theta, i, ty)` | X rotation by θ | |
| `Ry(theta, i, ty)` | Y rotation by θ | |
| `Rz(theta, i, ty)` | Z rotation by θ | |
| `Phase(phi, i, ty)` | Global phase e^{iφ} | |

**Two-qubit gates:**

| Gate | Signature | Description |
|------|-----------|-------------|
| `CX(i, j, ty)` | CNOT (control i, target j) | |
| `CZ(i, j, ty)` | Controlled-Z | |
| `CH(i, j, ty)` | Controlled-Hadamard | |
| `CS(i, j, ty)` | Controlled-S | |
| `CSdg(i, j, ty)` | Controlled-S-dagger | |
| `CRz(theta, i, j, ty)` | Controlled-Rz by θ | |

**Three-qubit gates:**

| Gate | Signature | Description |
|------|-----------|-------------|
| `CCX(i, j, k, ty)` | Toffoli (controls i,j, target k) | |
| `CSWAP(c, i, j, ty)` | Fredkin (control c, swap i,j) | |

### Ctrl Combinator (Controlled Operations)

The `Ctrl` combinator provides a principled way to create controlled operations.

**Type signature:**
```
Ctrl(f) : Bool ⊗ A → Bool ⊗ A    where f : A → A
```

**Semantics:**
- When control qubit is |0⟩: identity on A (f not applied)
- When control qubit is |1⟩: apply f to A
- Control qubit passes through unchanged

**Compilation:** Uses inductive construction:
- **Base case:** Primitive gates use built-in controlled versions
  - `Ctrl(H)` → CH, `Ctrl(S)` → CS, `Ctrl(X)` → CX, `Ctrl(Z)` → CZ
  - `Ctrl(Rz(θ))` → CRz(θ), `Ctrl(CX)` → CCX
  - `Ctrl(TwistTen(Q,Q))` → CSWAP
- **Inductive cases:**
  - `Ctrl(f ; g)` = `Ctrl(f) ; Ctrl(g)` (distributes over composition)
  - `Ctrl(f ⊗ g)` = `Ctrl(f) ⊗ Ctrl(g)` (shared control over tensor)
  - `Ctrl(Id)` = Id (identity needs no control)
  - `Ctrl(Ctrl(X))` = CCX (nested control gives multi-controlled)

**Example:**
```python
from lang.terms import Ctrl, H, S, X, Seq, TenTerm
from lang.types import Q, Ten

# Single-qubit controlled gates
Ctrl(H(0, Q()))              # CH : Bool ⊗ Q → Bool ⊗ Q
Ctrl(S(0, Q()))              # CS : Bool ⊗ Q → Bool ⊗ Q

# Controlled sequence
Ctrl(Seq(H(0, Q()), S(0, Q())))  # CH ; CS

# Controlled tensor (shared control)
Ctrl(TenTerm(H(0, Q()), S(0, Q())))  # Ctrl(H) ⊗ Ctrl(S)

# Doubly-controlled (Toffoli)
Ctrl(Ctrl(X(0, Q())))        # CCX : Bool ⊗ (Bool ⊗ Q) → Bool ⊗ (Bool ⊗ Q)
```

### Exponentials of Involutions

**Typing rule:**
```
P : A → A    P² = id
─────────────────────
exp_i(θ, P) : A → A
```

| Term | Type | Description |
|------|------|-------------|
| `ExpInvolution(θ, P, ty)` | A → A | exp(iθ·P) where P : A → A is involution |
| `ExpSwap(θ, i, j, ty)` | Q⊗Q → Q⊗Q | Atomic exp(iθ·SWAP) on wires i, j |

**Signatures:**
```python
ExpInvolution(theta: float, body: Term, ty_total: Ty) -> Term
# Requires: body : A → A and body² = id
# Returns: term of type A → A

ExpSwap(theta: float, i: int, j: int, ty_total: Ty) -> Term
# Returns: term of type ty_total → ty_total
```

**OCaml Linear DSL:**
```ocaml
val exp_i : float -> (unit, [`Lolli of 'a * 'a]) prog
         -> (unit, [`Lolli of 'a * 'a]) prog
(* exp_i theta body — emits Bridge.TExpInvolution *)
```

**ExpSwap unitary:**
```
exp(iθ · SWAP) = cos(θ)·I + i·sin(θ)·SWAP
```

**ExpInvolution compilation:**
1. Compile body P to a unitary matrix U
2. Verify U² ≈ I (involutive check)
3. Compute `cos(θ)·I + i·sin(θ)·U` via direct unitary synthesis
4. Emit the result as a `Unitary1qBox`/`Unitary2qBox`/`Unitary3qBox` (up to 3 qubits)

### Qubit Encoding Isomorphism

| Term | Type | Description |
|------|------|-------------|
| `EncodeQubit()` | Q → I + I | Encode primitive qubit to one-hot |
| `DecodeQubit()` | I + I → Q | Decode one-hot back to primitive qubit |

**Signatures:**
```python
EncodeQubit() -> Term
# Returns: term of type Q → (I ⊕ I)

DecodeQubit() -> Term
# Returns: term of type (I ⊕ I) → Q
```

**Circuits:**
- `encode`: CX[0,1]; X[0] — maps |0⟩⊗|0⟩ → |10⟩, |1⟩⊗|0⟩ → |01⟩
- `decode`: X[0]; CX[0,1] — maps |10⟩ → |0⟩⊗|0⟩, |01⟩ → |1⟩⊗|0⟩

**Properties:**
- `encode ; decode = id` on Q ⊗ |0⟩ subspace
- `decode ; encode = id` on valid I+I states (|01⟩, |10⟩)
- Superposition preserved through roundtrip

**Note:** The ancilla (wire 1) must be |0⟩ for encode, and is returned to |0⟩ by decode.

### Compact-Closed Structure (Cups and Caps)

| Term | Type | Description |
|------|------|-------------|
| `Cup(ty)` | I → A ⊗ A* | Cup (unit introduction) — pure wiring, 0 gates |
| `Cap(ty)` | A* ⊗ A → I | Cap (counit / evaluation) — pure wiring, 0 gates |

Cups and caps are the compact-closed structure enabling higher-order programming.
Since all types are self-dual (A* = A), cup/cap are pure wire allocation/identification.

```python
from lang.terms import Cup, Cap
from lang.types import Q

Cup(Q())   # η_Q : I → Q ⊗ Q*  (allocate 2 wires)
Cap(Q())   # ε_Q : Q* ⊗ Q → I  (connect/identify 2 wires)
```

### Higher-Order Terms

| Term | Description |
|------|-------------|
| `FunVar(name, dom, cod)` | Function variable — identity on A ⊗ B wires |
| `Lam(name, dom, cod, body)` | Lambda abstraction — boundary exposure |
| `Apply(f, arg)` | Function application — boundary splicing |
| `Feedback(k, body)` | Loop k wires back (reserved for future use) |

**Note:** `Feedback` exists for future extensions but currently raises `NotImplementedError` when compiled.

Higher-order terms are compiled directly via cup/cap wiring.
A function `A ⊸ B` is physically `width(A) + width(B)` wires. Lambda exposes wires, application connects them.

### Full Source Language Terms

| Term | Signature | Description |
|------|-----------|-------------|
| `Var(name, ty)` | `Var(name: str, ty: Ty)` | Variable reference — identity on wire range |
| `Pair(fst, snd)` | `Pair(fst: Term, snd: Term)` | Tensor introduction — (t, u) : A ⊗ B |
| `LetPair(x, y, ty_x, ty_y, pair, body)` | See below | Tensor elimination — let (x,y) = t in u |
| `CaseExpr(scrut, x, y, ty_x, ty_y, left, right)` | See below | Case on sum — pattern matching with variable binding |

**LetPair signature:**
```python
LetPair(
    x: str,       # First variable name
    y: str,       # Second variable name
    ty_x: Ty,     # Type of x (A)
    ty_y: Ty,     # Type of y (B)
    pair: Term,   # The pair term t : A ⊗ B
    body: Term    # The body u : C (with x, y in scope)
) -> Term
```

**Compilation:** LetPair binds x to the first width(A) wires and y to the next width(B) wires in the environment, then compiles the body with extended environment.

```python
from lang.terms import Var, Pair, LetPair, Id, H, Seq
from lang.types import Q, Ten

# let (x, y) = id : Q⊗Q in (H(x), y)
pair_term = Id(Ten(Q(), Q()))
body = Pair(Seq(Var("x", Q()), H(0, Q())), Var("y", Q()))
lp = LetPair("x", "y", Q(), Q(), pair_term, body)
```

**CaseExpr signature:**
```python
CaseExpr(
    scrut: Term,   # Scrutinee : A + B
    x: str,        # Variable name for left payload (A)
    y: str,        # Variable name for right payload (B)
    ty_x: Ty,      # Type A (left payload)
    ty_y: Ty,      # Type B (right payload)
    left: Term,    # Left branch body (with x in scope)
    right: Term    # Right branch body (with y in scope)
) -> Term
```

**Compilation:** CaseExpr compiles the scrutinee, then executes both branches coherently via controlled gates (anti-control for left branch, control for right branch).

---

## Compilation (`python/src/compile/to_pytket.py`)

### compile()

Standard compilation to pytket circuit.

```python
from compile.to_pytket import compile, Compiled

result: Compiled = compile(term, materialize=False, explain=False, env=None)

# Parameters:
#   term: Term          — the term to compile
#   materialize: bool   — emit SWAP gates for wire permutations (default False)
#   explain: bool       — populate result.log with compilation trace (default False)
#   env: Env            — optional dict[str, (int, int)] for open terms with free variables

# Result fields:
result.circuit   # pytket Circuit
result.perm      # WirePerm (final wire permutation)
result.log       # List[str] if explain=True
```

---

## Permutations (`python/src/core/perm.py`)

```python
from core.perm import WirePerm, identity, compose, inverse, is_involution, decompose_involution

p = WirePerm([1, 0, 2])      # new_to_old mapping
e = identity(n)              # Identity permutation
q = compose(p2, p1)          # Composition
inv = inverse(p)             # Inverse

old_idx = p.apply_new_to_old(new_idx)
```

### Involution Functions

```python
from core.perm import is_involution, decompose_involution

# Check if permutation is involutive (p ∘ p = id)
is_involution(p: WirePerm) -> bool

# Decompose involution into disjoint transpositions
# Requires: is_involution(p) == True
decompose_involution(p: WirePerm) -> List[Tuple[int, int]]
```

**Example:**
```python
p = WirePerm([1, 0, 3, 2])   # Two swaps: (0,1) and (2,3)
assert is_involution(p)
swaps = decompose_involution(p)  # [(0, 1), (2, 3)]
```

---

## Type Checking (`python/src/typing_/check.py`)

```python
from typing_.check import type_of, assert_well_typed

dom, cod = type_of(term)     # Get domain and codomain
assert_well_typed(term)      # Raises TypeCheckError if invalid
```

---

## Example: Complete Workflow

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

## Example: Exponential of Involution

```python
from lang.types import Q, Plus
from lang.terms import TwistPlus, ExpInvolution
from compile.to_pytket import compile

# TwistPlus(Q, Q) is involutive: swap ∘ swap = id
ty = Plus(Q(), Q())
twist = TwistPlus(Q(), Q())

# exp(i * 0.5 * twist)
term = ExpInvolution(theta=0.5, body=twist, ty_total=ty)
result = compile(term)

# Produces ExpSwap gates for each transposition in the permutation
```

---

## Invariants

1. **Tensor structurals = pure permutation** — no gates, only wire reordering
2. **Sum structurals = symbolic tag rewrites** — tracked in TaggedPerm, lowered late
3. **No SWAPs by default** — only with `materialize=True`
4. **Gates are reindexed** — through `WirePerm.apply_new_to_old()`
5. **Deterministic** — same AST → identical circuit
6. **Involution certification** — ExpInvolution verifies π² = id at compile time

---

## Test Coverage

~620+ tests across Python (pytest) and OCaml (dune test + newtests).
