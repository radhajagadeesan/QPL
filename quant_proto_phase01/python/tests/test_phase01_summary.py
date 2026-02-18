"""Phase 0+1 summary tests (executable documentation).

These tests are intentionally *narrative* and *end-to-end*:
run them to understand what Phase 0+1 guarantee.

They assert the Phase-1-frozen invariants:
  - Structure compiles to WirePerm metadata only (no gates, no SWAPs).
  - Computation compiles to a flat, first-order unitary circuit.
  - No SWAPs by default.
  - SWAPs appear only via explicit materialization and do not change non-SWAP gate order.
  - Determinism: same AST -> identical circuit.

They are written to be resilient to small API renamings by using reflection.
If an API cannot be found, the error message tells you what symbol to expose.

Expected project layout (Phase 1):
  src/lang/types.py
  src/lang/terms.py
  src/core/perm.py
  src/compile/to_pytket.py
  src/backends/materialize.py

Run:
  pytest -q
"""

from __future__ import annotations

import importlib
import inspect
from dataclasses import is_dataclass
from typing import Any, Callable, Optional, Sequence, Tuple

import pytest


# ---------------------------------------------------------------------------
# Reflection helpers (keep these tests top-level and repo-stable)
# ---------------------------------------------------------------------------

def _import(mod: str):
    try:
        return importlib.import_module(mod)
    except Exception as e:
        raise AssertionError(
            f"Could not import {mod!r}. Ensure your repo uses the Phase 1 layout under src/ and is on PYTHONPATH.\n"
            f"Original error: {type(e).__name__}: {e}"
        )


def _pick_attr(obj: Any, *names: str) -> Any:
    for n in names:
        if hasattr(obj, n):
            return getattr(obj, n)
    raise AssertionError(
        f"None of {names} found on {obj}. Please export one of these names, or update this test file."
    )


def _pick_callable(mod: Any, preferred: Sequence[str], *, predicate: Optional[Callable[[Any], bool]] = None) -> Callable:
    """Pick a function from a module by name (preferred order) or by predicate."""
    for n in preferred:
        if hasattr(mod, n) and callable(getattr(mod, n)):
            return getattr(mod, n)
    if predicate is not None:
        for n, v in vars(mod).items():
            if callable(v) and predicate(v):
                return v
    raise AssertionError(
        f"Could not find a callable in {mod.__name__}. Expected one of: {list(preferred)}"
    )


def _term_ctor(terms_mod: Any, *names: str) -> Any:
    """Return a term class or constructor by trying several names."""
    return _pick_attr(terms_mod, *names)


def _shape_ctor(types_mod: Any, *names: str) -> Any:
    return _pick_attr(types_mod, *names)


def _call_ctor(ctor: Any, *args: Any, **kwargs: Any) -> Any:
    """Call a class/constructor, tolerating dataclasses with positional fields."""
    try:
        return ctor(*args, **kwargs)
    except TypeError:
        # Try keyword by field names for dataclasses
        if inspect.isclass(ctor) and is_dataclass(ctor):
            fields = [f.name for f in ctor.__dataclass_fields__.values()]  # type: ignore
            if len(args) == len(fields) and not kwargs:
                return ctor(**dict(zip(fields, args)))
        raise


def _pytket_available() -> bool:
    try:
        import pytket  # noqa: F401

        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Project-level helpers
# ---------------------------------------------------------------------------


def _load_project():
    """Import project modules."""
    types_mod = _import("lang.types")
    terms_mod = _import("lang.terms")
    perm_mod = _import("core.perm")
    to_pytket_mod = _import("compile.to_pytket")
    materialize_mod = _import("backends.materialize")
    return types_mod, terms_mod, perm_mod, to_pytket_mod, materialize_mod


def _compile_to_circuit(to_pytket_mod: Any, term: Any, ty: Any):
    """Compile term to a pytket Circuit.

    We accept any of these signatures (common in Phase 1 variants):
      - compile(term, ty)
      - to_pytket(term, ty)
      - compile_term(term, ty)
      - compile_program(term, ty)

    If your compiler needs a different entrypoint, expose one of these.
    """

    compiler = _pick_callable(
        to_pytket_mod,
        preferred=["compile", "to_pytket", "compile_term", "compile_program"],
    )

    try:
        return compiler(term, ty)
    except TypeError:
        # Some implementations accept only term and infer type.
        try:
            return compiler(term)
        except Exception as e:
            raise AssertionError(
                f"Compiler entrypoint {compiler.__name__} exists but could not be called as compile(term, ty) or compile(term). "
                f"Adjust test helper _compile_to_circuit accordingly. Original: {type(e).__name__}: {e}"
            )


def _materialize(materialize_mod: Any, circ: Any, perm: Any):
    """Materialize SWAPs for a circuit/permutation (debug only).

    The materialize module may have:
      - swaps_for_perm(perm) -> list of (a, b) tuples
      - apply_swaps(circ, swaps) -> applies swaps to circuit

    Or a combined:
      - materialize(circ, perm)
      - materialize_swaps(circ, perm)

    If your API differs, export one of these.
    """

    # Try combined functions first
    for fn_name in ["materialize", "materialize_swaps"]:
        if hasattr(materialize_mod, fn_name) and callable(getattr(materialize_mod, fn_name)):
            fn = getattr(materialize_mod, fn_name)
            try:
                return fn(circ, perm)
            except TypeError:
                pass

    # Use swaps_for_perm + apply_swaps
    if hasattr(materialize_mod, "swaps_for_perm") and hasattr(materialize_mod, "apply_swaps"):
        swaps = materialize_mod.swaps_for_perm(perm)
        materialize_mod.apply_swaps(circ, swaps)
        return circ

    raise AssertionError(
        f"Could not find materialize functions in {materialize_mod.__name__}. "
        "Expected materialize(circ, perm) or swaps_for_perm + apply_swaps."
    )


def _extract_perm_from_compile_result(res: Any):
    """Compiler outputs either:
      - a Circuit
      - (Circuit, WirePerm)
      - {"circuit":..., "perm":...} (dict)
      - Compiled object with .circuit and .perm attributes

    Return (circuit, perm_or_None).
    """

    # Object with .circuit attribute (e.g., Compiled dataclass)
    if hasattr(res, "circuit"):
        return res.circuit, getattr(res, "perm", None)

    # dict-like
    if isinstance(res, dict) and "circuit" in res:
        return res["circuit"], res.get("perm")

    # tuple-like
    if isinstance(res, tuple) and len(res) == 2:
        return res[0], res[1]

    # circuit only
    return res, None


def _count_swaps(circ: Any) -> int:
    """Count SWAP ops in a pytket circuit."""
    # pytket Circuit has get_commands()
    cmds = circ.get_commands()
    return sum(1 for c in cmds if c.op.type.name.upper() == "SWAP")


def _non_swap_signature(circ: Any) -> Tuple[Tuple[str, Tuple[int, ...]], ...]:
    """A stable signature: sequence of (op_type, qubit_indices) for non-SWAP gates."""
    sig = []
    for cmd in circ.get_commands():
        optype = cmd.op.type.name.upper()
        if optype == "SWAP":
            continue
        qs = tuple(int(q.index[0]) for q in cmd.args)  # Qubit index
        sig.append((optype, qs))
    return tuple(sig)


def _assert_no_swaps_by_default(circ: Any):
    n = _count_swaps(circ)
    assert n == 0, f"Expected no SWAPs by default, found {n}"


# ---------------------------------------------------------------------------
# Narrative test programs
# ---------------------------------------------------------------------------


def _mk_q(types_mod: Any, n: int):
    """Return an n-wire quantum shape.

    We accept either:
      - Q(n) if Q takes a size argument
      - Q() as atomic singleton, build n-qubit type via Ten(Q(), Q(), ...)
      - helper like q(n), Qn(n), qn(n)

    If your representation differs, update this helper.
    """

    Q = _shape_ctor(types_mod, "Q")

    # Try Q(n) first
    try:
        return _call_ctor(Q, n)
    except TypeError:
        pass

    # Try helper functions q(n), Qn(n), qn(n)
    for fn_name in ["q", "Qn", "qn"]:
        if hasattr(types_mod, fn_name) and callable(getattr(types_mod, fn_name)):
            return getattr(types_mod, fn_name)(n)

    # Q is atomic - build n-qubit type using Ten
    if n == 1:
        return _call_ctor(Q)

    Ten = _shape_ctor(types_mod, "Ten")
    # Build left-associative tensor: Ten(Ten(Q, Q), Q) for n=3
    result = _call_ctor(Q)
    for _ in range(n - 1):
        result = _call_ctor(Ten, result, _call_ctor(Q))
    return result


def _mk_seq(terms_mod: Any, *terms: Any):
    Seq = _term_ctor(terms_mod, "Seq")
    t = terms[0]
    for u in terms[1:]:
        t = _call_ctor(Seq, t, u)
    return t


def _mk_id(terms_mod: Any):
    Id = _term_ctor(terms_mod, "Id")
    try:
        return _call_ctor(Id)
    except TypeError:
        # sometimes Id(ty)
        return Id


def _mk_gate_H(terms_mod: Any, i: int, ty: Any = None):
    H = _term_ctor(terms_mod, "H")
    try:
        if ty is not None:
            return _call_ctor(H, i, ty)
        return _call_ctor(H, i)
    except TypeError:
        # Maybe H() with defaults works
        return _call_ctor(H)


def _mk_gate_S(terms_mod: Any, i: int, ty: Any = None):
    S = _term_ctor(terms_mod, "S")
    try:
        if ty is not None:
            return _call_ctor(S, i, ty)
        return _call_ctor(S, i)
    except TypeError:
        return _call_ctor(S)


def _mk_gate_CX(terms_mod: Any, c: int, t: int, ty: Any = None):
    CX = _term_ctor(terms_mod, "CX", "CNOT")
    try:
        if ty is not None:
            return _call_ctor(CX, c, t, ty)
        return _call_ctor(CX, c, t)
    except TypeError:
        return _call_ctor(CX)


def _mk_twist(terms_mod: Any, kind: str = "ten", types_mod: Any = None, ty: Any = None):
    """Return a structural twist term.

    We try common names: TenTwist/TensorTwist and PlusTwist/SumTwist.
    If the constructor requires type arguments (a, b), we use:
      - If ty is provided and is Ten(a, b), use TwistTen(a, b)
      - Otherwise default to Q(), Q() (2-qubit twist)
    """

    # Get Q type for default arguments
    if types_mod is None:
        types_mod = _import("lang.types")
    Q = _shape_ctor(types_mod, "Q")
    q = _call_ctor(Q)

    # Determine a, b for twist
    a, b = q, q
    if ty is not None:
        Ten = _shape_ctor(types_mod, "Ten")
        if isinstance(ty, type(Ten(q, q))) or (hasattr(ty, "left") and hasattr(ty, "right")):
            a, b = ty.left, ty.right

    if kind == "ten":
        ctor = _term_ctor(terms_mod, "TenTwist", "TensorTwist", "TwistTen", "TwistTensor")
        try:
            return _call_ctor(ctor)
        except TypeError:
            # Constructor requires type arguments
            return _call_ctor(ctor, a, b)
    if kind == "plus":
        ctor = _term_ctor(terms_mod, "PlusTwist", "SumTwist", "TwistPlus", "TwistSum")
        try:
            return _call_ctor(ctor)
        except TypeError:
            return _call_ctor(ctor, a, b)
    raise ValueError(kind)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not _pytket_available(), reason="pytket not installed in this environment")
def test_summary_01_flat_unitary_circuit_no_swaps():
    """A small program compiles to a flat unitary circuit with *no SWAPs by default*.

    This is the baseline Phase 1 claim: compilation produces first-order pytket gates only.
    """

    types_mod, terms_mod, perm_mod, to_pytket_mod, _ = _load_project()

    ty = _mk_q(types_mod, 2)
    prog = _mk_seq(
        terms_mod,
        _mk_gate_H(terms_mod, 0),
        _mk_gate_CX(terms_mod, 0, 1),
        _mk_gate_S(terms_mod, 1),
    )

    res = _compile_to_circuit(to_pytket_mod, prog, ty)
    circ, _perm = _extract_perm_from_compile_result(res)

    _assert_no_swaps_by_default(circ)
    # Sanity: has commands
    assert len(circ.get_commands()) >= 3


@pytest.mark.skipif(not _pytket_available(), reason="pytket not installed in this environment")
def test_summary_02_structure_only_rewiring_changes_gate_indices_not_gate_sequence():
    """Structural rewiring changes *where* gates land, but does not add gates.

    We compare:
      (A) gates-only program
      (B) same gates, but wrapped by a structural twist that permutes wires

    Expect:
      - same number of non-SWAP gates
      - same gate *types* in the same order
      - (likely) different qubit indices
      - no SWAPs in either
    """

    types_mod, terms_mod, perm_mod, to_pytket_mod, _ = _load_project()

    ty = _mk_q(types_mod, 2)

    gates = _mk_seq(
        terms_mod,
        _mk_gate_H(terms_mod, 0),
        _mk_gate_CX(terms_mod, 0, 1),
        _mk_gate_S(terms_mod, 0),
    )

    twist = _mk_twist(terms_mod, "ten")
    # common pattern: Seq(Twist, gates) or Seq(gates, Twist); we pick Twist;gates
    prog_rewired = _mk_seq(terms_mod, twist, gates)

    cA, _ = _extract_perm_from_compile_result(_compile_to_circuit(to_pytket_mod, gates, ty))
    cB, _ = _extract_perm_from_compile_result(_compile_to_circuit(to_pytket_mod, prog_rewired, ty))

    _assert_no_swaps_by_default(cA)
    _assert_no_swaps_by_default(cB)

    sigA = _non_swap_signature(cA)
    sigB = _non_swap_signature(cB)

    assert len(sigA) == len(sigB)
    assert tuple(t for (t, _qs) in sigA) == tuple(t for (t, _qs) in sigB)

    # In most conventions, twist will change indices for at least one gate.
    assert sigA != sigB, "Expected rewiring to change at least one gate's wire indices"


@pytest.mark.skipif(not _pytket_available(), reason="pytket not installed in this environment")
def test_summary_03_global_no_swap_regression_guard():
    """Regression guard: structural compilation must not sneak SWAPs into the output.

    This test is intentionally blunt: if any SWAP appears, Phase 1 is broken.
    """

    types_mod, terms_mod, perm_mod, to_pytket_mod, _ = _load_project()

    ty = _mk_q(types_mod, 3)

    twist = _mk_twist(terms_mod, "ten", types_mod, ty)
    prog = _mk_seq(
        terms_mod,
        twist,
        _mk_gate_H(terms_mod, 0, ty),
        _mk_gate_CX(terms_mod, 0, 1, ty),
        _mk_gate_CX(terms_mod, 1, 2, ty),
        _mk_gate_S(terms_mod, 2, ty),
    )

    circ, _ = _extract_perm_from_compile_result(_compile_to_circuit(to_pytket_mod, prog, ty))
    _assert_no_swaps_by_default(circ)


@pytest.mark.skipif(not _pytket_available(), reason="pytket not installed in this environment")
def test_summary_04_materialization_adds_only_swaps_preserves_non_swap_order():
    """Materialization is debug-only: it may insert SWAPs but must preserve non-SWAP order.

    We compile a program that accumulates a nontrivial WirePerm.
    Then we explicitly materialize that perm into SWAPs.

    Expect:
      - pre-materialization: no SWAPs
      - post-materialization: may have SWAPs
      - non-SWAP gate *sequence* unchanged
    """

    types_mod, terms_mod, perm_mod, to_pytket_mod, materialize_mod = _load_project()

    ty = _mk_q(types_mod, 2)

    twist = _mk_twist(terms_mod, "ten")
    prog = _mk_seq(
        terms_mod,
        twist,
        _mk_gate_H(terms_mod, 0),
        _mk_gate_CX(terms_mod, 0, 1),
        _mk_gate_S(terms_mod, 1),
    )

    res = _compile_to_circuit(to_pytket_mod, prog, ty)
    circ, perm = _extract_perm_from_compile_result(res)

    _assert_no_swaps_by_default(circ)
    assert perm is not None, (
        "This summary test expects the compiler to return the final WirePerm along with the circuit "
        "(e.g., (circ, perm) or {circuit:..., perm:...}). "
        "If your compiler currently returns only the circuit, expose the perm for debugging/materialization."
    )

    sig_before = _non_swap_signature(circ)

    circ_mat = _materialize(materialize_mod, circ.copy(), perm)

    # Materialized circuit may (or may not) include swaps depending on perm.
    assert len(circ_mat.get_commands()) >= len(circ.get_commands())
    sig_after = _non_swap_signature(circ_mat)

    assert sig_before == sig_after, "Materialization must preserve non-SWAP gate sequence"


@pytest.mark.skipif(not _pytket_available(), reason="pytket not installed in this environment")
def test_summary_05_compiler_determinism_same_ast_identical_circuit():
    """Determinism: same AST compiles to byte-for-byte identical (command-identical) circuit."""

    types_mod, terms_mod, perm_mod, to_pytket_mod, _ = _load_project()

    ty = _mk_q(types_mod, 2)
    prog = _mk_seq(
        terms_mod,
        _mk_gate_H(terms_mod, 0),
        _mk_gate_CX(terms_mod, 0, 1),
        _mk_gate_S(terms_mod, 0),
    )

    c1, p1 = _extract_perm_from_compile_result(_compile_to_circuit(to_pytket_mod, prog, ty))
    c2, p2 = _extract_perm_from_compile_result(_compile_to_circuit(to_pytket_mod, prog, ty))

    assert _non_swap_signature(c1) == _non_swap_signature(c2)
    assert _count_swaps(c1) == _count_swaps(c2) == 0

    # If you return perms, they should also be equal under repr/eq.
    if p1 is not None and p2 is not None:
        assert repr(p1) == repr(p2)
