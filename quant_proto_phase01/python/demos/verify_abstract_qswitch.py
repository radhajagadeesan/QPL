"""Verify abstract QSwitch unitary matches meta-level QSwitch[H,S].

Tests at multiple levels of abstraction:
1. Concrete QSwitch[H,S] — direct gates (reference)
2. Lambda-wrapped QSwitch — Lam/Apply wiring (should match)
3. Nested Apply: f(g(x)) with f=λ.H, g=λ.S (should give S;H)
4. LetPair + Apply: extract function from pair, apply it
5. Full abstract QSwitch via LetPair + Apply + Case
"""

import numpy as np
from pytket.circuit import Circuit as PytketCircuit
from lang.types import Q, Ten, Plus, Unit, Arrow, width
from lang.terms import (
    Id, Seq, H, S, Var, Pair, LetPair, Lam, Apply,
    Case, TenTerm, DistL,
)
from typing_.check import type_of
from compile.to_pytket import compile


# Types
I = Unit()
Bool = Plus(I, I)
BoolQ = Ten(Bool, Q())
IQ = Ten(I, Q())
FnType = Arrow(Q(), Q())


def compare_unitaries(u1, u2, label):
    """Compare two unitaries up to global phase."""
    if u1.shape != u2.shape:
        print(f"  FAIL {label}: shape mismatch {u1.shape} vs {u2.shape}")
        return False
    product = u2 @ u1.conj().T
    phases = np.diag(product)
    if np.allclose(np.abs(phases), 1.0, atol=1e-8) and np.allclose(phases, phases[0], atol=1e-8):
        print(f"  PASS {label} (global phase = {phases[0]:.4f})")
        return True
    else:
        fidelity = np.abs(np.trace(product)) / u1.shape[0]
        print(f"  FAIL {label} (fidelity = {fidelity:.6f})")
        return False


def extract_submatrix(u_big, n_qubits, data_qubits, ancilla_state=0):
    """Extract effective unitary on data_qubits, ancillas fixed at ancilla_state.

    pytket big-endian: q[0] is MSB. state_idx = sum(q[k] * 2^(n-1-k)).
    """
    n_data = len(data_qubits)
    dim = 2 ** n_data

    def state_index(data_bits):
        idx = ancilla_state
        for k, dq in enumerate(data_qubits):
            if data_bits & (1 << (n_data - 1 - k)):
                idx |= (1 << (n_qubits - 1 - dq))
        return idx

    u_eff = np.zeros((dim, dim), dtype=complex)
    for i in range(dim):
        for j in range(dim):
            u_eff[i, j] = u_big[state_index(i), state_index(j)]
    return u_eff


def section(title):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


results = []

# ============================================================
# 1. Concrete (meta-level) QSwitch[H,S]
# ============================================================
section("1. Concrete QSwitch[H,S] (reference)")

left_branch = Seq(TenTerm(Id(I), S(0, Q())), TenTerm(Id(I), H(0, Q())))   # S then H
right_branch = Seq(TenTerm(Id(I), H(0, Q())), TenTerm(Id(I), S(0, Q())))  # H then S
concrete_qs = Seq(DistL(I, I, Q()), Case(IQ, IQ, left_branch, right_branch))

r1 = compile(concrete_qs, materialize=True)
u_concrete = r1.circuit.get_unitary()
print(f"  {r1.circuit.n_qubits} qubits, {r1.circuit.n_gates} gates")
print(f"  Unitary: {u_concrete.shape}")


# ============================================================
# 2. Lambda-wrapped concrete QSwitch
# ============================================================
section("2. Lambda-wrapped QSwitch (Lam/Apply wiring)")

lam_qs = Lam("bx", BoolQ, BoolQ, concrete_qs)
wrapped_qs = Apply(lam_qs, Id(BoolQ))

r2 = compile(wrapped_qs, materialize=True)
u_wrapped = r2.circuit.get_unitary()
print(f"  {r2.circuit.n_qubits} qubits, {r2.circuit.n_gates} gates")
ok = compare_unitaries(u_concrete, u_wrapped, "lambda-wrapped vs concrete")
results.append(("Lambda-wrapped", ok))


# ============================================================
# 3. Nested Apply: f(g(x)) via closed-lambda beta-reduction
# ============================================================
section("3. Nested Apply: Apply(lam.H, Apply(lam.S, Id(Q)))")

f_lam = Lam("a", Q(), Q(), H(0, Q()))
g_lam = Lam("b", Q(), Q(), S(0, Q()))

gx = Apply(g_lam, Id(Q()))
fgx = Apply(f_lam, gx)

r3 = compile(fgx, materialize=True)
u_fgx = r3.circuit.get_unitary()
n3 = r3.circuit.n_qubits
print(f"  {n3} qubits, {r3.circuit.n_gates} gates")

# Reference: S then H on 1 qubit
ref_sh = PytketCircuit(1)
ref_sh.S(0)
ref_sh.H(0)
u_ref_sh = ref_sh.get_unitary()

if n3 > 1:
    u_eff3 = extract_submatrix(u_fgx, n3, [0])
    ok = compare_unitaries(u_ref_sh, u_eff3, "f(g(x)) effective vs S;H")
else:
    ok = compare_unitaries(u_ref_sh, u_fgx, "f(g(x)) vs S;H")
results.append(("Nested Apply", ok))


# ============================================================
# 4. LetPair + Apply: extract function from pair, apply
# ============================================================
section("4. LetPair + Apply: let (f, x) = (lam.H, id) in f(x)")

input_pair = Pair(f_lam, Id(Q()))
body_apply = Apply(Var("f", FnType), Var("x", Q()))
lp_term = LetPair("f", "x", FnType, Q(), input_pair, body_apply)

r4 = compile(lp_term, materialize=True, explain=True)
u_lp = r4.circuit.get_unitary()
n4 = r4.circuit.n_qubits
print(f"  {n4} qubits, {r4.circuit.n_gates} gates")

# Reference: H on 1 qubit
ref_h = PytketCircuit(1)
ref_h.H(0)
u_ref_h = ref_h.get_unitary()

if n4 > 1:
    ok = False
    for dq in range(n4):
        u_try = extract_submatrix(u_lp, n4, [dq])
        uu = u_try @ u_try.conj().T
        if np.allclose(uu, np.eye(2), atol=1e-6):
            matched = compare_unitaries(u_ref_h, u_try, f"LetPair+Apply q[{dq}] vs H")
            if matched:
                ok = True
                break
    if not ok:
        print("  FAIL: No single-qubit submatrix matches H")
else:
    ok = compare_unitaries(u_ref_h, u_lp, "LetPair+Apply vs H")
results.append(("LetPair+Apply", ok))

print("  Log:")
for line in r4.log:
    print(f"    {line}")


# ============================================================
# 5. Full abstract QSwitch applied to H, S
# ============================================================
section("5. Full abstract QSwitch: LetPair + Apply + Case")

fn_ty = FnType
rest1_ty = Ten(fn_ty, Ten(Bool, Q()))
rest2_ty = Ten(Bool, Q())
input_ty = Ten(fn_ty, rest1_ty)

print(f"  Input type width: {width(input_ty)}")
print(f"  Output type width: {width(BoolQ)}")

# Build the abstract QSwitch body using LetPair with Pair values.
# The _normalize pass in compile() will substitute these:
#   LetPair(f, rest, Pair(f_lam, ...), body) → body[f_lam/f, .../rest]
#
# After normalization, Case branches contain Apply(f_lam, ...) directly,
# which the compiler handles via closed-lambda beta-reduction.

# Case branches (operate on summand type IQ = Ten(I, Q()), width 1):
# Left (b=0): g then f on payload
abstract_left = Seq(
    TenTerm(Id(I), Apply(Var("g", fn_ty), Id(Q()))),
    TenTerm(Id(I), Apply(Var("f", fn_ty), Id(Q())))
)
# Right (b=1): f then g on payload
abstract_right = Seq(
    TenTerm(Id(I), Apply(Var("f", fn_ty), Id(Q()))),
    TenTerm(Id(I), Apply(Var("g", fn_ty), Id(Q())))
)

# Abstract QSwitch body: destructure input, case on Bool, apply functions
abstract_body = Seq(DistL(I, I, Q()), Case(IQ, IQ, abstract_left, abstract_right))

# Full applied term: wrap in LetPairs with Pair values (for substitution)
full_abstract = LetPair("f", "rest", fn_ty, rest1_ty,
    Pair(f_lam, Pair(g_lam, Id(BoolQ))),
    LetPair("g", "bx", fn_ty, rest2_ty,
        Var("rest", rest1_ty),
        abstract_body))

print(f"\n  Compiling full abstract QSwitch...")
try:
    r5 = compile(full_abstract, materialize=True, explain=True)
    u_abstract = r5.circuit.get_unitary()
    n5 = r5.circuit.n_qubits
    print(f"  {n5} qubits, {n5} gates")
    print(f"  Unitary shape: {u_abstract.shape}")

    if n5 == 2:
        # Same size as concrete — direct comparison
        ok = compare_unitaries(u_concrete, u_abstract, "abstract vs concrete QSwitch")
    else:
        # Extract effective 2-qubit unitary
        print(f"  Extracting effective 2-qubit unitary...")
        ok = False
        from itertools import combinations
        for q_out in combinations(range(n5), 2):
            u_try = extract_submatrix(u_abstract, n5, list(q_out))
            uu = u_try @ u_try.conj().T
            if np.allclose(uu, np.eye(4), atol=1e-4):
                matched = compare_unitaries(u_concrete, u_try, f"abstract q{q_out} vs concrete")
                if matched:
                    ok = True
                    break
        if not ok:
            print("  FAIL: No 2-qubit submatrix matches concrete QSwitch")

    results.append(("Full abstract QSwitch", ok))

    if r5.log:
        print("  Log:")
        for line in r5.log:
            print(f"    {line}")

except Exception as e:
    import traceback
    print(f"  Compilation failed: {e}")
    traceback.print_exc()
    results.append(("Full abstract QSwitch", False))


# ============================================================
# Summary
# ============================================================
section("Results")
for name, ok in results:
    status = "PASS" if ok else "FAIL"
    print(f"  [{status}] {name}")

n_pass = sum(1 for _, ok in results if ok)
n_total = len(results)
print(f"\n  {n_pass}/{n_total} passed")
