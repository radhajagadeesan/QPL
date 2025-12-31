# tests/utils_integration.py
from __future__ import annotations
from typing import List
from pytket import Circuit

def extract_cmd_stream(circ: Circuit) -> List[str]:
    """Canonical command stream for determinism/equality checks."""
    result: List[str] = []
    for cmd in circ.get_commands():
        name = cmd.op.type.name
        wires = [q.index[0] for q in cmd.qubits]
        result.append(f"{name}({','.join(map(str, wires))})")
    return result

def has_swaps(circ: Circuit) -> bool:
    return any(cmd.op.type.name.upper() == "SWAP" for cmd in circ.get_commands())

def perm_equal(p, q) -> bool:
    return (p.n == q.n) and (list(p.new_to_old) == list(q.new_to_old))
