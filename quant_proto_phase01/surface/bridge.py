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
src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))

from lang.types import Q, Ten, Plus, Unit, Ty, width
from lang.terms import (
    Term, Id, Seq, TenTerm,
    TwistTen, AssocTenL, AssocTenR,
    TwistPlus, AssocPlusL, AssocPlusR,
    DistL, DistR,
    H, S, Sdg, T, Tdg, X, Y, Z,
    Rx, Ry, Rz, Phase,
    CX, CZ, CRz, CCX,
    # Controlled single-qubit gates
    CH, CS, CSdg,
    # Higher-order constructs (GOI apply)
    FunVar, Lam, Apply,
    # Exponentials of structural involutions
    ExpSwap, ExpInvolution,
    # Bifunctorial action on sums
    PlusMap,
    # Case combinator
    Case,
)
from core.perm import WirePerm, identity, compose
from compile.to_pytket import compile
from compile.goi import (
    GOIArtifact, GateAtom, LoopSpec,
    apply_perm, goi_seq, make_unitary_value, conjugate_unitary,
)


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
        else:
            raise ValueError(f"No single-controlled version of gate: {name}")

    # Multiple controls: decompose using the first control + recursion
    # C^n[G] = C[C^{n-1}[G]] implemented as nested controlled gates
    else:
        # For multi-controlled gates, we decompose:
        # CC...C[G] with controls [c0, c1, ..., cn] on target t
        # becomes a sequence that uses ancilla or direct decomposition
        #
        # For now, use the simple (but gate-expensive) decomposition:
        # Apply controlled version with first control, where the "base gate"
        # is itself controlled by the remaining controls
        #
        # This is handled by the to_pytket compiler which supports multi-controlled ops
        raise ValueError(
            f"Multi-controlled gate ({len(controls)} controls) not yet supported in bridge. "
            f"Gate: {name}, controls: {controls}, target: {target}"
        )


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


def parse_term(j: dict, ty_total: Ty = None) -> Term:
    """Parse a JSON term representation into a Term.

    ty_total: The total type context for gates. If None, inferred from max wire index.
    """
    # Infer ty_total from max wire index if not provided
    if ty_total is None:
        max_idx = _max_wire_index(j)
        n_qubits = max(2, max_idx + 1)  # At least 2 qubits
        ty_total = _build_ty_total(n_qubits)

    node = j["node"]

    # Structural combinators
    if node == "Id":
        return Id(parse_type(j["ty"]))

    elif node == "Seq":
        return Seq(parse_term(j["f"], ty_total), parse_term(j["g"], ty_total))

    elif node == "TenTerm":
        return TenTerm(parse_term(j["f"], ty_total), parse_term(j["g"], ty_total))

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

    # Higher-order constructs (GOI apply)
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
    else:
        response = {"success": False, "error": f"Unknown request type: {req_type}"}

    print(json.dumps(response))


if __name__ == "__main__":
    main()
