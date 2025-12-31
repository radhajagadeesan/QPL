# tests/utils_integration.py
from __future__ import annotations
from typing import List
from pytket import Circuit

def extract_cmd_stream(circ: Circuit) -> List[str]:
    result: List[str] = []
    for cmd in circ.get_commands():
        name = cmd.op.type.name
        wires = [q.index[0] for q in cmd.qubits]
        result.append(f"{name}({','.join(map(str, wires))})")
    return result

def has_swaps(circ: Circuit) -> bool:
    return any(cmd.op.type.name.upper() == "SWAP" for cmd in circ.get_commands())

def perm_to_list(perm) -> list[int]:
    return list(perm.new_to_old)

def load_json(path):
    import json
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def save_json(path, obj):
    import json
    from pathlib import Path
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, sort_keys=True)
        f.write("\n")
