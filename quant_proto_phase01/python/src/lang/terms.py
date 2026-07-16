# src/lang/terms.py
"""AST for the prototype source language.

Design goal
-----------
Keep the AST *self-describing*: structural isomorphisms (twist/assoc/dist) carry
their intended type parameters so that typechecking is simple and errors are
readable.

Phases 0–1
----------
- Structural isos for both ⊗ and ⊕, plus distributivity maps.
- Gates are first-order and typed by a whole-program "ambient" type ty_total.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Union

from lang.types import Ty, Ten, Plus, Q, Dual, Arrow, Unit


def _contains_arrow(ty: Ty) -> bool:
    """True if ty tree contains any Arrow node."""
    if isinstance(ty, Arrow):
        return True
    if isinstance(ty, (Ten, Plus)):
        return _contains_arrow(ty.left) or _contains_arrow(ty.right)
    if isinstance(ty, Dual):
        return _contains_arrow(ty.ty)
    return False


@dataclass(frozen=True, slots=True)
class Id:
    ty: Ty


class Seq:
    """Sequential composition of terms.

    Can be constructed with 2 or more terms:
        Seq(f, g)        # two terms
        Seq(f, g, h)     # three terms -> Seq(f, Seq(g, h))
        Seq(f, g, h, i)  # four terms  -> Seq(f, Seq(g, Seq(h, i)))
    """
    __slots__ = ('f', 'g')

    def __init__(self, f: "Term", g: "Term", *rest: "Term"):
        if rest:
            # Variadic: Seq(a, b, c, ...) -> Seq(a, Seq(b, c, ...))
            g = Seq(g, *rest)
        object.__setattr__(self, 'f', f)
        object.__setattr__(self, 'g', g)

    def __setattr__(self, name, value):
        raise AttributeError("Seq is immutable")

    def __hash__(self):
        return hash((self.f, self.g))

    def __eq__(self, other):
        if not isinstance(other, Seq):
            return NotImplemented
        return self.f == other.f and self.g == other.g

    def __repr__(self):
        return f"Seq({self.f!r}, {self.g!r})"


@dataclass(frozen=True, slots=True)
class TenTerm:
    """Parallel composition of terms: f ⊗ g."""
    f: "Term"
    g: "Term"


# -- Structural isos for tensor (⊗)

@dataclass(frozen=True, slots=True)
class TwistTen:
    """twist⊗_{a,b} : a⊗b -> b⊗a"""
    a: Ty
    b: Ty


@dataclass(frozen=True, slots=True)
class AssocTenL:
    """assoc⊗_L : (a⊗b)⊗c -> a⊗(b⊗c)"""
    a: Ty
    b: Ty
    c: Ty


@dataclass(frozen=True, slots=True)
class AssocTenR:
    """assoc⊗_R : a⊗(b⊗c) -> (a⊗b)⊗c"""
    a: Ty
    b: Ty
    c: Ty


# -- Structural isos for sum (⊕) (structural only in Phases 0–1)

@dataclass(frozen=True, slots=True)
class TwistPlus:
    """twist⊕_{a,b} : a⊕b -> b⊕a"""
    a: Ty
    b: Ty


@dataclass(frozen=True, slots=True)
class AssocPlusL:
    """assoc⊕_L : (a⊕b)⊕c -> a⊕(b⊕c)"""
    a: Ty
    b: Ty
    c: Ty


@dataclass(frozen=True, slots=True)
class AssocPlusR:
    """assoc⊕_R : a⊕(b⊕c) -> (a⊕b)⊕c"""
    a: Ty
    b: Ty
    c: Ty


# -- Distributivity (structural only in Phases 0–1)

@dataclass(frozen=True, slots=True)
class DistL:
    """dist_L : (a⊕b)⊗c -> (a⊗c) ⊕ (b⊗c)"""
    a: Ty
    b: Ty
    c: Ty


@dataclass(frozen=True, slots=True)
class DistR:
    """dist_R : a⊗(b⊕c) -> (a⊗b) ⊕ (a⊗c)"""
    a: Ty
    b: Ty
    c: Ty


# -- Inverse distributivity (structural only in Phases 0–1)

@dataclass(frozen=True, slots=True)
class UndistL:
    """undist_L : (a⊗c) ⊕ (b⊗c) -> (a⊕b)⊗c (inverse of DistL)"""
    a: Ty
    b: Ty
    c: Ty


@dataclass(frozen=True, slots=True)
class UndistR:
    """undist_R : (a⊗b) ⊕ (a⊗c) -> a⊗(b⊕c) (inverse of DistR)"""
    a: Ty
    b: Ty
    c: Ty


# -- Feedback (Phase 3 GOI)

@dataclass(frozen=True, slots=True)
class WireIdentity:
    """Wire-level identity between two types of equal width.

    Used for type coercions where the wire encoding is identical but the
    Granthi type-level interpretation differs — specifically, the n-ary
    distributivity primitives [n_dist] and [n_factor] which convert between
        Z_n ⊗ A  and  ⊕^n (b ⊗ A)
    at the type level. Both forms have the same flat n-ary wire encoding
    (log_n tag bits + width(A) payload), so the morphism is identity at the
    wire level. Compiles to zero gates.
    """
    dom: Ty
    cod: Ty


@dataclass(frozen=True, slots=True)
class TagPerm:
    """Wire-level basis-state permutation on a fixed-width type.

    Maps basis state |i⟩ to |perm[i]⟩ for i < n, identity on unused states.
    Used as a general primitive for permutation morphisms on tagged sum
    types (e.g., group operations like Z_n's neg/shift). Compiles via
    pytket's ToffoliBox.

    The width of [ty] determines the number of qubits (k = width(ty)),
    and perm must be a length-n tuple where n ≤ 2^k.
    """
    perm: tuple
    ty: Ty


@dataclass(frozen=True, slots=True)
class Feedback:
    """Feedback_k(body) : explicit GOI feedback operator.

    If body : (A ⊗ X) → (B ⊗ X) with width(X) = k,
    then Feedback_k(body) : A → B.

    This is the ONLY construct that may introduce cycles.
    Feedback is explicit and fenced—no implicit GOI elsewhere.
    """
    k: int           # number of loop wires
    body: "Term"     # the body term


# -- Gate terms (Phase 0 minimal + Phase 4C extensions)

@dataclass(frozen=True, slots=True)
class H:
    """Hadamard gate on wire i.

    Defaults: i=0, ty_total=Ten(Q(), Q()) for 2-qubit context.
    """
    i: int = 0
    ty_total: Ty = None  # type: ignore

    def __post_init__(self):
        if self.ty_total is None:
            object.__setattr__(self, 'ty_total', Ten(Q(), Q()))


@dataclass(frozen=True, slots=True)
class S:
    """S (phase) gate on wire i.

    Defaults: i=0, ty_total=Ten(Q(), Q()) for 2-qubit context.
    """
    i: int = 0
    ty_total: Ty = None  # type: ignore

    def __post_init__(self):
        if self.ty_total is None:
            object.__setattr__(self, 'ty_total', Ten(Q(), Q()))


@dataclass(frozen=True, slots=True)
class CX:
    """Controlled-X gate with control i and target j.

    Defaults: i=0, j=1, ty_total=Ten(Q(), Q()) for standard 2-qubit context.
    """
    i: int = 0
    j: int = 1
    ty_total: Ty = None  # type: ignore

    def __post_init__(self):
        if self.ty_total is None:
            object.__setattr__(self, 'ty_total', Ten(Q(), Q()))


# -- Phase 4C: Additional fixed gates

@dataclass(frozen=True, slots=True)
class X:
    """Pauli-X gate on wire i."""
    i: int = 0
    ty_total: Ty = None  # type: ignore

    def __post_init__(self):
        if self.ty_total is None:
            object.__setattr__(self, 'ty_total', Ten(Q(), Q()))


@dataclass(frozen=True, slots=True)
class Y:
    """Pauli-Y gate on wire i."""
    i: int = 0
    ty_total: Ty = None  # type: ignore

    def __post_init__(self):
        if self.ty_total is None:
            object.__setattr__(self, 'ty_total', Ten(Q(), Q()))


@dataclass(frozen=True, slots=True)
class Z:
    """Pauli-Z gate on wire i."""
    i: int = 0
    ty_total: Ty = None  # type: ignore

    def __post_init__(self):
        if self.ty_total is None:
            object.__setattr__(self, 'ty_total', Ten(Q(), Q()))


@dataclass(frozen=True, slots=True)
class T:
    """T gate (π/4 phase) on wire i."""
    i: int = 0
    ty_total: Ty = None  # type: ignore

    def __post_init__(self):
        if self.ty_total is None:
            object.__setattr__(self, 'ty_total', Ten(Q(), Q()))


@dataclass(frozen=True, slots=True)
class Tdg:
    """T-dagger gate (inverse of T) on wire i."""
    i: int = 0
    ty_total: Ty = None  # type: ignore

    def __post_init__(self):
        if self.ty_total is None:
            object.__setattr__(self, 'ty_total', Ten(Q(), Q()))


@dataclass(frozen=True, slots=True)
class Sdg:
    """S-dagger gate (inverse of S) on wire i."""
    i: int = 0
    ty_total: Ty = None  # type: ignore

    def __post_init__(self):
        if self.ty_total is None:
            object.__setattr__(self, 'ty_total', Ten(Q(), Q()))


@dataclass(frozen=True, slots=True)
class CZ:
    """Controlled-Z gate with control i and target j."""
    i: int = 0
    j: int = 1
    ty_total: Ty = None  # type: ignore

    def __post_init__(self):
        if self.ty_total is None:
            object.__setattr__(self, 'ty_total', Ten(Q(), Q()))


@dataclass(frozen=True, slots=True)
class CH:
    """Controlled-Hadamard gate with control i and target j.

    Used for quantum control in case expressions on sum types.
    """
    i: int = 0
    j: int = 1
    ty_total: Ty = None  # type: ignore

    def __post_init__(self):
        if self.ty_total is None:
            object.__setattr__(self, 'ty_total', Ten(Q(), Q()))


@dataclass(frozen=True, slots=True)
class CS:
    """Controlled-S gate with control i and target j.

    Used for quantum control in case expressions on sum types.
    """
    i: int = 0
    j: int = 1
    ty_total: Ty = None  # type: ignore

    def __post_init__(self):
        if self.ty_total is None:
            object.__setattr__(self, 'ty_total', Ten(Q(), Q()))


@dataclass(frozen=True, slots=True)
class CSdg:
    """Controlled-S-dagger gate with control i and target j."""
    i: int = 0
    j: int = 1
    ty_total: Ty = None  # type: ignore

    def __post_init__(self):
        if self.ty_total is None:
            object.__setattr__(self, 'ty_total', Ten(Q(), Q()))


@dataclass(frozen=True, slots=True)
class CCX:
    """Toffoli (CCX) gate with controls i, j and target k."""
    i: int = 0
    j: int = 1
    k: int = 2
    ty_total: Ty = None  # type: ignore

    def __post_init__(self):
        if self.ty_total is None:
            object.__setattr__(self, 'ty_total', Ten(Ten(Q(), Q()), Q()))


@dataclass(frozen=True, slots=True)
class CSWAP:
    """Fredkin (CSWAP) gate with control c and targets i, j.

    Swaps qubits i and j when control c is |1⟩.
    This is Ctrl(SWAP) - the controlled version of SWAP.
    """
    c: int = 0
    i: int = 1
    j: int = 2
    ty_total: Ty = None  # type: ignore

    def __post_init__(self):
        if self.ty_total is None:
            object.__setattr__(self, 'ty_total', Ten(Ten(Q(), Q()), Q()))


# -- Phase 4C: Parameterized gates

@dataclass(frozen=True, slots=True)
class Rz:
    """Rz(θ) rotation around Z-axis on wire i.

    θ is in radians.
    """
    theta: float
    i: int = 0
    ty_total: Ty = None  # type: ignore

    def __post_init__(self):
        if self.ty_total is None:
            object.__setattr__(self, 'ty_total', Ten(Q(), Q()))


@dataclass(frozen=True, slots=True)
class Rx:
    """Rx(θ) rotation around X-axis on wire i.

    θ is in radians.
    """
    theta: float
    i: int = 0
    ty_total: Ty = None  # type: ignore

    def __post_init__(self):
        if self.ty_total is None:
            object.__setattr__(self, 'ty_total', Ten(Q(), Q()))


@dataclass(frozen=True, slots=True)
class Ry:
    """Ry(θ) rotation around Y-axis on wire i.

    θ is in radians.
    """
    theta: float
    i: int = 0
    ty_total: Ty = None  # type: ignore

    def __post_init__(self):
        if self.ty_total is None:
            object.__setattr__(self, 'ty_total', Ten(Q(), Q()))


@dataclass(frozen=True, slots=True)
class Phase:
    """Global phase gate e^{iφ} on wire i.

    φ is in radians. This applies a phase rotation.
    """
    phi: float
    i: int = 0
    ty_total: Ty = None  # type: ignore

    def __post_init__(self):
        if self.ty_total is None:
            object.__setattr__(self, 'ty_total', Ten(Q(), Q()))


@dataclass(frozen=True, slots=True)
class CRz:
    """Controlled-Rz(θ) with control i and target j.

    θ is in radians.
    """
    theta: float
    i: int = 0
    j: int = 1
    ty_total: Ty = None  # type: ignore

    def __post_init__(self):
        if self.ty_total is None:
            object.__setattr__(self, 'ty_total', Ten(Q(), Q()))


# -- Compact-closed structure (cups and caps)

@dataclass(frozen=True, slots=True)
class Cup:
    """Cup (unit introduction): η_A : I → A ⊗ A*.

    Creates a pair of wires: one for A, one for its dual A*.
    Pure wiring — emits zero gates.

    Since all our types are self-dual (A* = A physically),
    this allocates 2·width(A) wires.
    """
    ty: Ty  # A


@dataclass(frozen=True, slots=True)
class Cap:
    """Cap (counit / evaluation): ε_A : A* ⊗ A → I.

    Connects dual wires to their matching wires (wire identification).
    Pure wiring — emits zero gates.

    Since all our types are self-dual (A* = A physically),
    this consumes 2·width(A) wires.
    """
    ty: Ty  # A


# -- Higher-order constructs (compiled via cup/cap wiring)

@dataclass(frozen=True, slots=True)
class FunVar:
    """Function variable: x : A → B.

    Represents a wire bundle of width(A) + width(B).
    A function A → B is physically A* ⊗ B ≡ A ⊗ B wires.
    """
    name: str
    dom: Ty  # A
    cod: Ty  # B


@dataclass(frozen=True, slots=True)
class Lam:
    """Lambda abstraction: λx:A→B. body.

    Compiled via cup: creates A⊗B wires for the function variable x,
    then compiles body which uses those wires.
    """
    name: str
    dom: Ty  # A (domain of x)
    cod: Ty  # B (codomain of x)
    body: "Term"


@dataclass(frozen=True, slots=True)
class Apply:
    """Function application: f arg.

    Compiled via cap: connects function's domain wires to argument wires.
    Pure wiring — the cap identifies dual wires.
    """
    f: "Term"
    arg: "Term"


# -- Exponentials of structural involutions

@dataclass(frozen=True, slots=True)
class ExpSwap:
    """Exponential of SWAP on wires i and j: exp(iθ · SWAP).

    This is the atomic building block for exponentials of structural involutions.
    Any involutive permutation π decomposes into disjoint transpositions,
    and exp(iθ · π) = ∏ₖ exp(iθ · SWAP(aₖ,bₖ)) for each transposition (aₖ,bₖ).

    The unitary is: exp(iθ · SWAP) = cos(θ)·I + i·sin(θ)·SWAP
    """
    theta: float
    i: int = 0
    j: int = 1
    ty_total: Ty = None  # type: ignore

    def __post_init__(self):
        if self.ty_total is None:
            object.__setattr__(self, 'ty_total', Ten(Q(), Q()))


@dataclass(frozen=True, slots=True)
class ExpInvolution:
    """Exponential of a structural involution: exp(iθP).

    The body P can be any term that compiles to an involutive unitary (U² ≈ I).
    At compile time:
    1. Compile P to a unitary matrix U
    2. Verify U² ≈ I (involutive check)
    3. Compute cos(θ)·I + i·sin(θ)·U via direct unitary synthesis
    4. Emit as Unitary1qBox/Unitary2qBox/Unitary3qBox (up to 3 qubits)

    This gives: exp(iθ · P) = cos(θ)·I + i·sin(θ)·P
    """
    theta: float
    body: "Term"  # The involution P
    ty_total: Ty = None  # type: ignore

    def __post_init__(self):
        if self.ty_total is None:
            object.__setattr__(self, 'ty_total', Ten(Q(), Q()))
        if _contains_arrow(self.ty_total):
            raise ValueError(
                f"ExpInvolution body type must be first-order (no Arrow "
                f"constructors); got ty_total={self.ty_total!r}"
            )


# -- Tensor introduction and elimination (for full source language)

@dataclass(frozen=True, slots=True)
class Pair:
    """Tensor introduction (pairing): t ⊗ u.

    Given t : A and u : B (with disjoint contexts), produces (t, u) : A ⊗ B.

    This is the term-level pairing operator, distinct from TenTerm which is
    parallel composition of morphisms. Pair is for building values, while
    TenTerm is for combining circuits.
    """
    fst: "Term"  # t : A
    snd: "Term"  # u : B


@dataclass(frozen=True, slots=True)
class LetPair:
    """Tensor elimination (destructuring): let (x, y) = t in u.

    Given t : A ⊗ B with x : A and y : B bound in u : C,
    produces a term of type C.

    This binds x to the first width(A) wires and y to the next width(B) wires
    of t's output. The body u can then refer to x and y as contiguous wire
    bundles in the environment.

    Compilation:
    1. Compile t to get circuit Ct : ⟦Γ1⟧ → ⟦A⟧||⟦B⟧
    2. Extend environment: x ↦ prefix of t's output, y ↦ suffix
    3. Compile u with extended environment
    4. Wire: connect Ct's outputs to corresponding x,y input wires of Cu
    """
    x: str       # first variable name
    y: str       # second variable name
    ty_x: Ty     # type of x (A)
    ty_y: Ty     # type of y (B)
    pair: "Term" # the pair term t : A ⊗ B
    body: "Term" # the body u : C (with x, y in scope)


@dataclass(frozen=True, slots=True)
class Var:
    """Variable reference: x.

    Represents a reference to a bound variable. During compilation, this
    becomes identity wiring on the variable's wire range (from the environment).
    """
    name: str
    ty: Ty  # The type of the variable


# -- Case/Copairing (branching on sum types)

@dataclass(frozen=True, slots=True)
class Case:
    """Case combinator (bifunctorial): [f, g] : (A + B) → (C + D).

    Given:
        left  : A → C
        right : B → D

    Produces a combinator of type (A + B) → (C + D) that:
    - Applies `left` when the input is in the left summand
    - Applies `right` when the input is in the right summand
    - Preserves the tag (left stays left, right stays right)

    When the input is in superposition, this compiles to controlled gates:
    - Anti-controlled (on tag=0): apply gates from `left` branch
    - Controlled (on tag=1): apply gates from `right` branch

    Type parameters:
        ty_left:  A (left summand)
        ty_right: B (right summand)

    Note: This is semantically a bifunctor on sums (same as PlusMap).
    For true copairing with same codomain, use branches that produce the same type.
    """
    ty_left: Ty   # A
    ty_right: Ty  # B
    left: "Term"  # f : A → C
    right: "Term" # g : B → D


@dataclass(frozen=True, slots=True)
class CaseExpr:
    """Pattern-matching case expression on sum types.

    case scrut of
    | inl x => left_body
    | inr y => right_body

    Given:
        scrut : A + B (the scrutinee)
        x     : variable name bound to A in left branch
        y     : variable name bound to B in right branch

    The scrutinee is evaluated, then based on the tag:
    - If left (tag=0): bind x to payload A, evaluate left_body
    - If right (tag=1): bind y to payload B, evaluate right_body

    When the scrutinee is in superposition, both branches execute coherently
    via controlled gates (anti-control for left, control for right).

    Type parameters:
        ty_x: A (left payload type, bound to x)
        ty_y: B (right payload type, bound to y)

    The result type C is inferred from the bodies (they must match for true copairing).
    """
    scrut: "Term"  # scrutinee : A + B
    x: str         # variable name for left payload
    y: str         # variable name for right payload
    ty_x: Ty       # type A (left payload)
    ty_y: Ty       # type B (right payload)
    left: "Term"   # left_body : C (with x : A in scope)
    right: "Term"  # right_body : C (with y : B in scope)


@dataclass(frozen=True, slots=True)
class PlusMap:
    """Bifunctorial action on sums (⊕-Map): f ⊕ g : (A + B) → (C + D).

    Given:
        left  : A → C
        right : B → D

    Produces a term of type (A + B) → (C + D) that:
    - Applies `left` when the input is in the left summand
    - Applies `right` when the input is in the right summand
    - Preserves the tag (left stays left, right stays right)

    When the input is in superposition, this compiles to controlled gates:
    - Anti-controlled (on tag=0): apply gates from `left` branch
    - Controlled (on tag=1): apply gates from `right` branch

    This differs from Case which has both branches produce the same type:
    - Case:    [f, g] : (A + B) → C           (f: A→C, g: B→C)
    - PlusMap: f ⊕ g  : (A + B) → (C + D)     (f: A→C, g: B→D)

    Type parameters:
        ty_left:  A (left summand input type)
        ty_right: B (right summand input type)

    The output types C and D are inferred from the branches.
    """
    ty_left: Ty    # A (left input)
    ty_right: Ty   # B (right input)
    left: "Term"   # f : A → C
    right: "Term"  # g : B → D


@dataclass(frozen=True, slots=True)
class NPlusMap:
    """N-ary coherent sum eliminator.

    NPlusMap(summand_types=(A₁,...,Aₙ), branches=(f₁,...,fₙ))
    where fᵢ : Aᵢ → Bᵢ

    Domain:  A₁ + ... + Aₙ   (flat Plus tree)
    Codomain: B₁ + ... + Bₙ  (flat Plus tree)

    Compiles directly against the flat tag encoding using
    per-branch X-flip + multi-controlled gates + X-unflip.
    """
    summand_types: tuple  # (Ty, ...) — input summand types
    branches: tuple       # (Term, ...) — one morphism per summand


@dataclass(frozen=True, slots=True)
class PhasedPlusMap:
    """Phase-weighted bifunctorial action on sums.

    Like PlusMap, but applies a phase factor z = e^{iθ} to the left branch.
    This is the phase-weighted bifunctor omap_z(f, g) from the spec.

    Given:
        theta : float (phase angle, z = e^{iθ})
        left  : A → C
        right : B → D

    Produces a term of type (A + B) → (C + D) that:
    - Applies `left` when in left summand, THEN multiplies by phase z
    - Applies `right` when in right summand (no phase)
    - Preserves the tag

    Implementation:
    For A ⊕ B with tag qubit(s), the phase on the left branch becomes a
    controlled-phase gate on the tag qubit(s). For a binary sum (1 tag qubit):
        X; P(θ); X  applies phase e^{iθ} when tag=0 (left branch)

    For larger sums with multi-qubit tags, uses multi-controlled phase
    targeting the left branch's tag encoding.

    Type parameters:
        theta:    Phase angle (z = e^{iθ}, validated |z| = 1 in OCaml)
        ty_left:  A (left summand input type)
        ty_right: B (right summand input type)
    """
    theta: float   # Phase angle (z = e^{iθ})
    ty_left: Ty    # A (left input)
    ty_right: Ty   # B (right input)
    left: "Term"   # f : A → C
    right: "Term"  # g : B → D


@dataclass(frozen=True, slots=True)
class PhasedControl:
    """Phase-weighted n-ary coherent control.

    Given an n-ary datatype D with arity k and phases [θ₀, ..., θ_{k-1}],
    applies phase e^{iθᵢ} when control is in branch i.

    Type: D ⊗ A → D ⊗ A

    Uses efficient log₂(k) tag encoding. For each tag value i with binary
    pattern b₀b₁...b_{n-1}:
    - Apply X to bits that are 0 in the pattern
    - Apply multi-controlled U1(θᵢ/π)
    - Apply X to restore

    Parameters:
        name:     Datatype name (for debugging)
        arity:    Number of branches k
        phases:   List of phase angles [θ₀, ..., θ_{k-1}]
        dt_rep:   Datatype representation (I^{⊕k})
        a_ty:     Target type A
    """
    name: str
    arity: int
    phases: list  # List of floats (angles in radians)
    dt_rep: Ty    # Datatype representation
    a_ty: Ty      # Target type


# -- Controlled combinator (inductive construction)

@dataclass(frozen=True, slots=True)
class Ctrl:
    """Controlled combinator: Ctrl(f) : Bool ⊗ A → Bool ⊗ A.

    Given f : A → A, produces a controlled version that:
    - Applies f when control qubit is |1⟩
    - Applies identity when control qubit is |0⟩
    - Preserves the control qubit (passes it through)

    Type: Ctrl : (A ⊸ A) → (Bool ⊗ A ⊸ Bool ⊗ A)

    Compiled inductively:
    - Base case: primitive gates use built-in controlled versions (CH, CS, etc.)
    - Inductive cases:
        Ctrl(f ; g) = Ctrl(f) ; Ctrl(g)     -- distributes over composition
        Ctrl(f ⊗ g) = Ctrl(f) ⊗ Ctrl(g)    -- shared control over tensor
        Ctrl(Id)    = Id                    -- identity
        Ctrl(Twist) = CSWAP                 -- controlled swap

    This enables multi-level control: Ctrl(Ctrl(f)) gives doubly-controlled gates.
    """
    body: "Term"  # f : A → A


# -- Qubit encoding isomorphism (Q ↔ I + I with ancilla)

@dataclass(frozen=True, slots=True)
class EncodeQubit:
    """Encode a primitive qubit into one-hot sum type: Q → I + I.

    Allocates an ancilla |0⟩ internally. Circuit: CX[0,1]; X[0]

    Maps:
        |0⟩ → |10⟩  (logical |0⟩_L)
        |1⟩ → |01⟩  (logical |1⟩_L)

    Preserves superposition: α|0⟩ + β|1⟩ → α|10⟩ + β|01⟩
    """
    pass


@dataclass(frozen=True, slots=True)
class DecodeQubit:
    """Decode one-hot sum type back to primitive qubit: I + I → Q.

    Deallocates ancilla (returns to |0⟩). Circuit: X[0]; CX[0,1]

    Maps:
        |10⟩ → |0⟩  (logical |0⟩_L → |0⟩)
        |01⟩ → |1⟩  (logical |1⟩_L → |1⟩)

    Partial function: undefined on invalid states |00⟩, |11⟩.
    Preserves superposition: α|10⟩ + β|01⟩ → α|0⟩ + β|1⟩
    """
    pass


Term = Union[
    Id, Seq, TenTerm,
    TwistTen, AssocTenL, AssocTenR,
    TwistPlus, AssocPlusL, AssocPlusR,
    DistL, DistR, UndistL, UndistR,
    Feedback,
    # Phase 0 gates
    H, S, CX,
    # Phase 4C fixed gates
    X, Y, Z, T, Tdg, Sdg, CZ, CCX, CSWAP,
    # Phase 4C parameterized gates
    Rz, Rx, Ry, Phase, CRz,
    # Controlled single-qubit gates (for quantum case expressions)
    CH, CS, CSdg,
    # Compact-closed structure (cups and caps)
    Cup, Cap,
    # Higher-order constructs (compiled via cup/cap wiring)
    FunVar, Lam, Apply,
    # Tensor intro/elim and variables (full source language)
    Pair, LetPair, Var,
    # Case/copairing (branching on sum types)
    Case,
    # Pattern-matching case expression
    CaseExpr,
    # Bifunctorial action on sums (⊕-Map)
    PlusMap,
    # N-ary coherent sum eliminator
    NPlusMap,
    # Phase-weighted bifunctorial action
    PhasedPlusMap,
    # Phase-weighted n-ary control
    PhasedControl,
    # Exponentials of structural involutions
    ExpSwap, ExpInvolution,
    # Controlled combinator (inductive)
    Ctrl,
    # Qubit encoding isomorphism
    EncodeQubit, DecodeQubit,
]


def q() -> Ty:
    """Atomic Q wire."""
    return Q()


def ten(a: Ty, b: Ty) -> Ty:
    return Ten(a, b)


def plus(a: Ty, b: Ty) -> Ty:
    return Plus(a, b)


# Aliases for alternative naming conventions used in tests
TensorTwist = TwistTen
TensorAssocL = AssocTenL
TensorAssocR = AssocTenR
SumTwist = TwistPlus
SumAssocL = AssocPlusL
SumAssocR = AssocPlusR
