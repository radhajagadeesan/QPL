#!/usr/bin/env python3
"""Bridge script for OCaml surface language integration.

This script provides a JSON-based interface for the OCaml surface compiler
to call the Phase 0-4C Python compiler.

Usage:
    echo '{"type": "compile", "term": {...}}' | python bridge.py
    echo '{"type": "check_involution", "term": {...}}' | python bridge.py

Input JSON format for terms:
    {"node": "TwistPlus", "a": {"node": "Q"}, "b": {"node": "Q"}}
    {"node": "Id", "ty": {"node": "Plus", "left": {"node": "Q"}, "right": {"node": "Q"}}}
"""

import json
import sys
from pathlib import Path

# Add src to path
src_path = Path(__file__).parent.parent / "python" / "src"
sys.path.insert(0, str(src_path))

from lang.types import Q, Ten, Plus, Unit, Ty, width
from lang.terms import (
    Term, Id, Seq, TenTerm,
    TwistTen, AssocTenL, AssocTenR,
    TwistPlus, AssocPlusL, AssocPlusR,
    DistL, DistR, UndistL, UndistR,
    H, S, Sdg, T, Tdg, X, Y, Z,
    Rx, Ry, Rz, Phase,
    CX, CZ, CRz, CCX,
    # Controlled single-qubit gates
    CH, CS, CSdg,
    # Higher-order constructs
    FunVar, Lam, Apply,
    # Exponentials of structural involutions
    ExpSwap, ExpInvolution,
    # Bifunctorial action on sums
    PlusMap,
    # N-ary coherent sum eliminator
    NPlusMap,
    # Phase-weighted bifunctorial action
    PhasedPlusMap,
    # Phase-weighted n-ary control
    PhasedControl,
    # Case combinator
    Case,
)
from core.perm import WirePerm, identity, compose
from compile.to_pytket import compile


def parse_type(j: dict) -> Ty:
    """Parse a JSON type representation into a Ty."""
    node = j["node"]
    if node == "Q":
        return Q()
    elif node == "Unit" or node == "I":
        return Unit()
    elif node == "Ten":
        return Ten(parse_type(j["left"]), parse_type(j["right"]))
    elif node == "Plus":
        return Plus(parse_type(j["left"]), parse_type(j["right"]))
    else:
        raise ValueError(f"Unknown type node: {node}")


def _max_wire_index(j: dict) -> int:
    """Find the maximum wire index used in a JSON term."""
    node = j.get("node", "")
    max_idx = -1

    # Check for wire indices in gates
    if "i" in j:
        max_idx = max(max_idx, j["i"])
    if "j" in j:
        max_idx = max(max_idx, j["j"])
    if "k" in j:
        max_idx = max(max_idx, j["k"])

    # Recurse into subterms
    if "f" in j:
        max_idx = max(max_idx, _max_wire_index(j["f"]))
    if "g" in j:
        max_idx = max(max_idx, _max_wire_index(j["g"]))
    if "body" in j:
        max_idx = max(max_idx, _max_wire_index(j["body"]))
    if "arg" in j:
        max_idx = max(max_idx, _max_wire_index(j["arg"]))
    if "left" in j:
        max_idx = max(max_idx, _max_wire_index(j["left"]))
    if "right" in j:
        max_idx = max(max_idx, _max_wire_index(j["right"]))

    return max_idx


def parse_general_gate(j: dict, ty_total: Ty) -> Term:
    """Parse a general gate with arbitrary controls.

    JSON format: {"node": "Gate", "name": "H", "targets": [1], "controls": [0, 2]}

    For nested quantum case expressions, gates can have multiple controls
    (one for each nesting level).
    """
    from lang.terms import (
        Id, Seq,
        H, S, Sdg, T, Tdg, X, Y, Z,
        CH, CS, CSdg,
    )

    name = j["name"]
    targets = j["targets"]
    controls = j.get("controls", [])

    if len(targets) != 1:
        raise ValueError(f"General gate currently only supports single-target gates, got {targets}")

    target = targets[0]

    # No controls: just the basic gate
    if len(controls) == 0:
        if name == "H":
            return H(target, ty_total)
        elif name == "S":
            return S(target, ty_total)
        elif name == "Sdg":
            return Sdg(target, ty_total)
        elif name == "T":
            return T(target, ty_total)
        elif name == "Tdg":
            return Tdg(target, ty_total)
        elif name == "X":
            return X(target, ty_total)
        elif name == "Y":
            return Y(target, ty_total)
        elif name == "Z":
            return Z(target, ty_total)
        else:
            raise ValueError(f"Unknown gate name: {name}")

    # Single control: use existing controlled gates
    elif len(controls) == 1:
        ctrl = controls[0]
        if name == "H":
            return CH(ctrl, target, ty_total)
        elif name == "S":
            return CS(ctrl, target, ty_total)
        elif name == "Sdg":
            return CSdg(ctrl, target, ty_total)
        elif name == "X":
            return CX(ctrl, target, ty_total)
        elif name == "Z":
            return CZ(ctrl, target, ty_total)
        elif name == "T":
            # Controlled-T = CRz(π/4)
            import math
            return CRz(math.pi / 4, ctrl, target, ty_total)
        else:
            raise ValueError(f"No single-controlled version of gate: {name}")

    # Multiple controls: construct nested Ctrl terms
    # Gate(name, [target], [c0, c1, ...]) → Ctrl(Ctrl(...Ctrl(base_gate)...))
    # The Ctrl layout places controls as the first N wires, payload after.
    # This matches the lift_to_controlled pattern from OCaml elaboration.
    else:
        from lang.terms import Ctrl, Rz as RzTerm, Rx as RxTerm, Ry as RyTerm, CX as CXTerm
        import re

        n_ctrls = len(controls)
        inner_target = target - n_ctrls

        # Build base gate with adjusted wire index
        if name == "H":
            base = H(inner_target, ty_total)
        elif name == "S":
            base = S(inner_target, ty_total)
        elif name == "Sdg":
            base = Sdg(inner_target, ty_total)
        elif name == "T":
            base = T(inner_target, ty_total)
        elif name == "Tdg":
            base = Tdg(inner_target, ty_total)
        elif name == "X":
            base = X(inner_target, ty_total)
        elif name == "Y":
            base = Y(inner_target, ty_total)
        elif name == "Z":
            base = Z(inner_target, ty_total)
        elif name.startswith("Rz("):
            theta = float(re.search(r'Rz\(([^)]+)\)', name).group(1))
            base = RzTerm(theta, inner_target, ty_total)
        elif name.startswith("Rx("):
            theta = float(re.search(r'Rx\(([^)]+)\)', name).group(1))
            base = RxTerm(theta, inner_target, ty_total)
        elif name.startswith("Ry("):
            theta = float(re.search(r'Ry\(([^)]+)\)', name).group(1))
            base = RyTerm(theta, inner_target, ty_total)
        else:
            raise ValueError(
                f"Multi-controlled gate not supported for: {name}. "
                f"Controls: {controls}, target: {target}"
            )

        # Wrap in n_ctrls levels of Ctrl
        result = base
        for _ in range(n_ctrls):
            result = Ctrl(result)
        return result


def _build_ty_total(n_qubits: int) -> Ty:
    """Build a tensor type with n_qubits qubits: Q ⊗ Q ⊗ ... ⊗ Q."""
    if n_qubits <= 0:
        return Q()
    if n_qubits == 1:
        return Q()

    # Build right-associated: Q ⊗ (Q ⊗ (Q ⊗ ...))
    result = Q()
    for _ in range(n_qubits - 1):
        result = Ten(Q(), result)
    return result


def _min_width_from_types(j: dict) -> int:
    """Find the minimum width implied by explicit type annotations in a term tree."""
    node = j.get("node", "")
    w = 0

    # Id nodes have an explicit type
    if node == "Id" and "ty" in j:
        w = max(w, width(parse_type(j["ty"])))

    # Recurse into subterms
    for key in ("f", "g", "body", "arg", "left", "right", "scrut"):
        if key in j and isinstance(j[key], dict):
            w = max(w, _min_width_from_types(j[key]))

    return w


def parse_term(j: dict, ty_total: Ty = None, min_qubits: int = 1) -> Term:
    """Parse a JSON term representation into a Term.

    ty_total: The total type context for gates. If None, inferred from max wire index
              and explicit type annotations in the term tree.
    min_qubits: Minimum qubit count for ty_total inference (default 1 for top-level,
                1 for TenTerm children which have their own local wire space).
    """
    # Infer ty_total from max wire index if not provided
    if ty_total is None:
        max_idx = _max_wire_index(j)
        type_width = _min_width_from_types(j)
        n_qubits = max(min_qubits, max_idx + 1, type_width)
        ty_total = _build_ty_total(n_qubits)

    node = j["node"]

    # Structural combinators
    if node == "Id":
        return Id(parse_type(j["ty"]))

    elif node == "Seq":
        return Seq(parse_term(j["f"], ty_total), parse_term(j["g"], ty_total))

    elif node == "TenTerm":
        # Each child of TenTerm uses its own local wire space,
        # so infer ty_total independently for each child with min_qubits=1.
        return TenTerm(parse_term(j["f"], None, min_qubits=1),
                       parse_term(j["g"], None, min_qubits=1))

    elif node == "TwistTen":
        return TwistTen(parse_type(j["a"]), parse_type(j["b"]))

    elif node == "AssocTenL":
        return AssocTenL(parse_type(j["a"]), parse_type(j["b"]), parse_type(j["c"]))

    elif node == "AssocTenR":
        return AssocTenR(parse_type(j["a"]), parse_type(j["b"]), parse_type(j["c"]))

    elif node == "TwistPlus":
        return TwistPlus(parse_type(j["a"]), parse_type(j["b"]))

    elif node == "AssocPlusL":
        return AssocPlusL(parse_type(j["a"]), parse_type(j["b"]), parse_type(j["c"]))

    elif node == "AssocPlusR":
        return AssocPlusR(parse_type(j["a"]), parse_type(j["b"]), parse_type(j["c"]))

    # Distributivity
    elif node == "DistL":
        return DistL(parse_type(j["a"]), parse_type(j["b"]), parse_type(j["c"]))

    elif node == "DistR":
        return DistR(parse_type(j["a"]), parse_type(j["b"]), parse_type(j["c"]))

    # Inverse distributivity
    elif node == "UndistL":
        return UndistL(parse_type(j["a"]), parse_type(j["b"]), parse_type(j["c"]))

    elif node == "UndistR":
        return UndistR(parse_type(j["a"]), parse_type(j["b"]), parse_type(j["c"]))

    # Single-qubit gates
    elif node == "H":
        return H(j["i"], ty_total)

    elif node == "S":
        return S(j["i"], ty_total)

    elif node == "Sdg":
        return Sdg(j["i"], ty_total)

    elif node == "T":
        return T(j["i"], ty_total)

    elif node == "Tdg":
        return Tdg(j["i"], ty_total)

    elif node == "X":
        return X(j["i"], ty_total)

    elif node == "Y":
        return Y(j["i"], ty_total)

    elif node == "Z":
        return Z(j["i"], ty_total)

    elif node == "Rx":
        return Rx(j["theta"], j["i"], ty_total)

    elif node == "Ry":
        return Ry(j["theta"], j["i"], ty_total)

    elif node == "Rz":
        return Rz(j["theta"], j["i"], ty_total)

    elif node == "Phase":
        return Phase(j["theta"], j["i"], ty_total)

    # Two-qubit gates
    elif node == "CX":
        return CX(j["i"], j["j"], ty_total)

    elif node == "CZ":
        return CZ(j["i"], j["j"], ty_total)

    elif node == "CRz":
        return CRz(j["theta"], j["i"], j["j"], ty_total)

    # Three-qubit gate
    elif node == "CCX":
        return CCX(j["i"], j["j"], j["k"], ty_total)

    # Controlled single-qubit gates (for quantum case expressions)
    elif node == "CH":
        return CH(j["i"], j["j"], ty_total)

    elif node == "CS":
        return CS(j["i"], j["j"], ty_total)

    elif node == "CSdg":
        return CSdg(j["i"], j["j"], ty_total)

    # General multi-controlled gate (for nested cases)
    elif node == "Gate":
        return parse_general_gate(j, ty_total)

    # Higher-order constructs
    elif node == "FunVar":
        return FunVar(j["name"], parse_type(j["dom"]), parse_type(j["cod"]))

    elif node == "Lam":
        body = parse_term(j["body"], ty_total)
        return Lam(j["name"], parse_type(j["dom"]), parse_type(j["cod"]), body)

    elif node == "Apply":
        return Apply(parse_term(j["f"], ty_total), parse_term(j["arg"], ty_total))

    # Bifunctorial action on sums (⊕-Map)
    elif node == "PlusMap":
        ty_left = parse_type(j["ty_left"])
        ty_right = parse_type(j["ty_right"])
        # Branches operate on payload types, not full sum type
        left = parse_term(j["left"], ty_left)
        right = parse_term(j["right"], ty_right)
        return PlusMap(ty_left, ty_right, left, right)

    # N-ary coherent sum eliminator
    elif node == "NPlusMap":
        summand_types = tuple(parse_type(t) for t in j["summand_types"])
        branches = tuple(parse_term(b, st) for b, st in zip(j["branches"], summand_types))
        return NPlusMap(summand_types, branches)

    # Phase-weighted bifunctorial action
    elif node == "PhasedPlusMap":
        theta = j["theta"]
        ty_left = parse_type(j["ty_left"])
        ty_right = parse_type(j["ty_right"])
        # Branches operate on payload types, not full sum type
        left = parse_term(j["left"], ty_left)
        right = parse_term(j["right"], ty_right)
        return PhasedPlusMap(theta, ty_left, ty_right, left, right)

    # Phase-weighted n-ary control
    elif node == "PhasedControl":
        name = j["name"]
        arity = j["arity"]
        phases = j["phases"]  # List of floats (angles in radians)
        dt_rep = parse_type(j["dt_rep"])
        a_ty = parse_type(j["a_ty"])
        return PhasedControl(name, arity, phases, dt_rep, a_ty)

    # Pattern-matching case expression from OCaml Linear DSL
    # CaseExpr = Seq(scrut, Case(ty_left, ty_right, left, right))
    elif node == "CaseExpr":
        ty_left = parse_type(j["ty_left"])
        ty_right = parse_type(j["ty_right"])
        scrut = parse_term(j["scrut"], ty_total)
        # Branches operate on payload types, not full sum type
        left = parse_term(j["left"], ty_left)
        right = parse_term(j["right"], ty_right)
        # Compose: first scrutinee, then case combinator
        case_combinator = Case(ty_left, ty_right, left, right)
        return Seq(scrut, case_combinator)

    # Exponentials of structural involutions
    elif node == "ExpSwap":
        return ExpSwap(j["theta"], j["i"], j["j"], ty_total)

    elif node == "ExpInvolution":
        body = parse_term(j["body"], ty_total)
        return ExpInvolution(j["theta"], body, ty_total)

    else:
        raise ValueError(f"Unknown term node: {node}")


def perm_to_json(p: WirePerm) -> dict:
    """Convert a WirePerm to JSON."""
    return {
        "n": p.n,
        "new_to_old": p.new_to_old
    }


def is_involution(p: WirePerm) -> bool:
    """Check if p ∘ p = identity."""
    p_squared = compose(p, p)
    id_perm = identity(p.n)
    return p_squared == id_perm


def handle_compile(request: dict) -> dict:
    """Handle a compile request."""
    try:
        term = parse_term(request["term"])
        result = compile(term, materialize=False)

        return {
            "success": True,
            "perm": perm_to_json(result.perm),
            "circuit_size": result.circuit.n_gates
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


def handle_eq_circ(request: dict) -> dict:
    """Handle a circuit equality request.

    Compiles two terms with materialize=True, extracts unitary matrices,
    and compares them up to global phase: |tr(U1† U2)| / dim ≈ 1.
    """
    import numpy as np

    try:
        term1 = parse_term(request["term1"])
        term2 = parse_term(request["term2"])

        result1 = compile(term1, materialize=True)
        result2 = compile(term2, materialize=True)

        u1 = result1.circuit.get_unitary()
        u2 = result2.circuit.get_unitary()

        if u1.shape != u2.shape:
            return {
                "success": True,
                "equal": False,
                "reason": f"dimension mismatch: {u1.shape} vs {u2.shape}"
            }

        dim = u1.shape[0]
        # U1† U2 — if equal up to global phase, this is e^{iφ} I
        product = np.conj(u1.T) @ u2
        trace = np.trace(product)
        fidelity = abs(trace) / dim

        equal = bool(fidelity > 1.0 - 1e-8)

        return {
            "success": True,
            "equal": equal,
            "fidelity": float(fidelity)
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


def handle_check_involution(request: dict) -> dict:
    """Handle an involution check request.

    With tagged layout model, structural sum operations (like TwistPlus)
    emit X gates for tag flips. These are still considered structural
    because X·X = I, so the tag flips cancel when composed.

    We check:
    1. Only X gates allowed (tag flips from sum operations)
    2. Permutation is involutive (p ∘ p = identity)
    """
    try:
        term = parse_term(request["term"])
        result = compile(term, materialize=False)

        # Check that only X gates are present (tag flips are OK)
        for cmd in result.circuit.get_commands():
            if cmd.op.type.name != 'X':
                return {
                    "success": False,
                    "error": f"Term is not structural (contains {cmd.op.type.name} gate)"
                }

        # Check involution
        is_invol = is_involution(result.perm)

        return {
            "success": True,
            "is_involution": is_invol,
            "perm": perm_to_json(result.perm)
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


def main():
    """Main entry point."""
    # Read JSON from stdin
    input_data = sys.stdin.read()

    try:
        request = json.loads(input_data)
    except json.JSONDecodeError as e:
        print(json.dumps({"success": False, "error": f"Invalid JSON: {e}"}))
        sys.exit(1)

    req_type = request.get("type", "compile")

    if req_type == "compile":
        response = handle_compile(request)
    elif req_type == "check_involution":
        response = handle_check_involution(request)
    elif req_type == "eq_circ":
        response = handle_eq_circ(request)
    else:
        response = {"success": False, "error": f"Unknown request type: {req_type}"}

    print(json.dumps(response))


if __name__ == "__main__":
    main()
