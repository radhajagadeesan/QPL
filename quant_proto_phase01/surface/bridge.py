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

from lang.types import Q, Ten, Plus, Ty
from lang.terms import (
    Term, Id, Seq, TenTerm,
    TwistTen, AssocTenL, AssocTenR,
    TwistPlus, AssocPlusL, AssocPlusR,
    DistL, DistR,
    H, S, Sdg, T, Tdg, X, Y, Z,
    Rx, Ry, Rz, Phase,
    CX, CZ, CRz, CCX,
)
from core.perm import WirePerm, identity, compose
from compile.to_pytket import compile


def parse_type(j: dict) -> Ty:
    """Parse a JSON type representation into a Ty."""
    node = j["node"]
    if node == "Q":
        return Q()
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

    return max_idx


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
