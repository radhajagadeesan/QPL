# Typing Rules Reference (from paper)

## Part A: Pure Linear Core

Typing judgment: `Γ ⊢ t : A`

Linearity enforced by context splitting (`Γ = Γ₁ ⊎ Γ₂`) in multiplicative rules.

### Rules

**Var**
```
────────────────
x:A ⊢ x : A
```

**⊸-I (Lam)**
```
Γ, x:A ⊢ t : B
────────────────────────
Γ ⊢ λx.t : A ⊸ B
```

**⊗-I (Tensor intro / Pair)**
```
Γ₁ ⊢ t : A    Γ₂ ⊢ u : B    Γ = Γ₁ ⊎ Γ₂
─────────────────────────────────────────────
Γ ⊢ t ⊗ u : A ⊗ B
```

**⊗-E (Tensor elim / LetPair)**
```
Γ₁ ⊢ t : A ⊗ B    Γ₂, x:A, y:B ⊢ u : C    Γ = Γ₁ ⊎ Γ₂
──────────────────────────────────────────────────────────────
Γ ⊢ let (x,y) = t in u : C
```

**⊸-E (App)**
```
Γ₁ ⊢ f : A ⊸ B    Γ₂ ⊢ u : A    Γ = Γ₁ ⊎ Γ₂
─────────────────────────────────────────────────
Γ ⊢ f u : B
```

**⊕-Map**
```
Γ₁ ⊢ f : A ⊸ C    Γ₂ ⊢ g : B ⊸ D    Γ = Γ₁ ⊎ Γ₂
──────────────────────────────────────────────────────
Γ ⊢ f ⊕ g : A ⊕ B ⊸ C ⊕ D
```

### Key observations for implementation

1. **Var** uses exactly a singleton context — no extra variables
2. **Lam** removes x from the context (x is bound, not free)
3. **Multiplicative rules** (Pair, LetPair, App, PlusMap) all split the context
4. **Branch contexts.** Two disciplines coexist:
   - The Raw open ⊕-map (`oplusmap`) uses SPLIT contexts: each branch
     owns its own disjoint slice of the conclusion context, proven by a
     partition witness.
   - The sealed Source `case`/`cases` (and the `let%source` surface) use
     COMPLETE branch-context transport: every branch consumes the
     identical complete nominal linear context, and the compiler
     transports the whole context into each branch (see
     `BRANCH_CONTEXT_LINEARITY.md`).  The earlier "disjoint union of
     branch contexts" phrasing described only the Raw ⊕-map.

## Part B: Generating Unitaries

### Part B(i): Exponentials of Involutions

Separate judgment `Γ ⊢_I J : A ⊸ A` for Hermitian involutions (P² = I, P = P†).

**Exp**
```
Γ ⊢_I J : A ⊸ A    θ ∈ ℝ_static
──────────────────────────────────
Γ ⊢_S exp(iθJ) : A ⊸ A
```

Note: The involution J can have context Γ (free variables).
This means exp(iθJ) inherits J's context.

### Part B(ii): Generalized ⊕-Map with phases + Unitary via Normal Form

**⊕-Map (generalized, with phases)**
```
Γ₁ ⊢_S f : A ⊸ C    Γ₂ ⊢_S g : B ⊸ D
Γ = Γ₁ ⊎ Γ₂    α, β ∈ ℂ, |α| = |β| = 1
────────────────────────────────────────────
Γ ⊢_S ⊕map(α,f,β,g) : A ⊕ B ⊸ C ⊕ D
```

**S-UnitViaNF(Δ)** — Apply raw unitary via structural normal form
```
⊢_U U : Qⁿ ⊸ Qⁿ    ⊢_NF η_T : T ⊸ Qⁿ
──────────────────────────────────────────
⊢_S (U, η_T) : T ⊸ T
```

Note: U is in the unitary judgment (no context Γ).
η_T is the structural normal form witness built from structural isos.

### Structural Normalization

Judgment: `⊢_NF ι_T : T ⊸ Q^|T|`

**NF-Q (base)**
```
──────────────────────
⊢_NF id_Q : Q ⊸ Q¹
```

**NF-* (dual)**
```
⊢_NF ι_A : A ⊸ Qᵐ
─────────────────────
⊢_NF ι_{A*} : A* ⊸ Qᵐ
```

**NF-⊗ (tensor)**
```
⊢_NF ι_A : A ⊸ Qᵐ    ⊢_NF ι_B : B ⊸ Qˡ
────────────────────────────────────────────
⊢_NF ι_{A⊗B} : A⊗B ⊸ Q^{m·ℓ}
```

**NF-⊕ (plus)**
```
⊢_NF ι_A : A ⊸ Qᵐ    ⊢_NF ι_B : B ⊸ Qˡ
────────────────────────────────────────────
⊢_NF ι_{A⊕B} : A⊕B ⊸ Q^{m+ℓ}
```

Structural normalization builds a witness from structural/distributivity
isomorphisms mapping any type T to Q^|T| (its Hilbert space dimension).

**Important conventions:**
- `b` (base) = 1-dimensional type (single basis vector), NOT a qubit
- Qubit = b + b (2-dimensional, by NF-⊕: 1+1 = 2)
- Q^n = n-dimensional Hilbert space (NOT n qubits)
- n qubits = Q^{2^n} (2^n dimensional)
- Tensor multiplies dimensions: dim(A⊗B) = dim(A) · dim(B)
- Plus adds dimensions: dim(A⊕B) = dim(A) + dim(B)

**Relation to qubit encoding (our compiler):**
- Since we only build types from qubits, we count qubits in practice
- Key difference is in sums:
  - Dimension: dim(A⊕B) = dim(A) + dim(B) (exact, direct sum)
  - Qubits: width(A⊕B) = ceil(log₂(leaves)) + max(width(leaf_i)) (tag+payload encoding)

## Source (LaTeX)

```latex
% (original LaTeX preserved for reference)
\textsc{Var}       x:A ⊢ x : A
\textsc{⊸-I}      Γ, x:A ⊢ t : B  ⟹  Γ ⊢ λx.t : A ⊸ B
\textsc{⊗-I}      Γ₁ ⊢ t : A, Γ₂ ⊢ u : B, Γ = Γ₁ ⊎ Γ₂  ⟹  Γ ⊢ t⊗u : A⊗B
\textsc{⊗-E}      Γ₁ ⊢ t : A⊗B, Γ₂,x:A,y:B ⊢ u : C, Γ = Γ₁ ⊎ Γ₂  ⟹  Γ ⊢ let(x,y)=t in u : C
\textsc{⊸-E}      Γ₁ ⊢ f : A⊸B, Γ₂ ⊢ u : A, Γ = Γ₁ ⊎ Γ₂  ⟹  Γ ⊢ fu : B
\textsc{⊕-Map}    Γ₁ ⊢ f : A⊸C, Γ₂ ⊢ g : B⊸D, Γ = Γ₁ ⊎ Γ₂  ⟹  Γ ⊢ f⊕g : A⊕B ⊸ C⊕D
```
