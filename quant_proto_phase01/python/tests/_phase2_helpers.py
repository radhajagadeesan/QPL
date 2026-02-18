"""
Helpers for Phase 2 TenTerm tests, aligned to the Phase 0–1 API reference.

Imports:
  - lang.types: Q, Ten, width
  - lang.terms: Id, Seq, TenTerm, H, S, CX, TwistTen, ...
  - compile.to_pytket: compile(term, materialize=False, explain=False) -> Compiled(circuit, perm, log?)
  - backends.materialize: swaps_for_perm, apply_swaps

We use pytket's standard introspection:
  circ.get_commands()
  cmd.op.type.name
  [q.index[0] for q in cmd.qubits]
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, List, Tuple

from lang.types import Q, Ten, width
from lang.terms import Id, Seq, TenTerm, H, S, CX, TwistTen, TwistPlus, AssocTenL, AssocTenR
from compile.to_pytket import compile as tk_compile
from backends.materialize import swaps_for_perm, apply_swaps

@dataclass(frozen=True)
class CmdSig:
    op: str
    qubits: Tuple[int, ...]

def qpow(n: int):
    """Nested tensor type Q ⊗ ... ⊗ Q with n factors (right-associated)."""
    assert n >= 1
    ty = Q()
    cur = ty
    for _ in range(n - 1):
        cur = Ten(cur, Q())
    return cur

def cmds(circ) -> list:
    return list(circ.get_commands())

def op_name(cmd) -> str:
    return cmd.op.type.name

def qubit_idxs(cmd) -> List[int]:
    return [int(q.index[0]) for q in cmd.qubits]

def assert_no_swaps(circ):
    bad = [c for c in cmds(circ) if op_name(c).upper() == "SWAP"]
    assert not bad, f"Found SWAPs in circuit when materialize=False: {[ (op_name(c), qubit_idxs(c)) for c in bad ]}"

def non_swap_signature(circ) -> List[CmdSig]:
    out: List[CmdSig] = []
    for c in cmds(circ):
        n = op_name(c)
        if n.upper() == "SWAP":
            continue
        out.append(CmdSig(op=n, qubits=tuple(qubit_idxs(c))))
    return out

def full_signature(circ) -> List[CmdSig]:
    return [CmdSig(op=op_name(c), qubits=tuple(qubit_idxs(c))) for c in cmds(circ)]

def compile_term(term, *, materialize: bool = False, explain: bool = False):
    """Compile and return Compiled."""
    return tk_compile(term, materialize=materialize, explain=explain)

def materialize_manual(compiled):
    """Return a new circuit with SWAPs applied for compiled.perm."""
    circ2 = compiled.circuit.copy()
    swaps = swaps_for_perm(compiled.perm)
    apply_swaps(circ2, swaps)
    return circ2
