"""
Helpers for Phase 3 GOI tests.

Provides:
- Type and term builders
- GOI artifact introspection
- Assertion utilities
"""
from __future__ import annotations
from typing import List, Set, Tuple

from lang.types import Q, Ten, width
from lang.terms import (
    Id, Seq, TenTerm, Feedback,
    TwistTen, AssocTenL, AssocTenR,
    TwistPlus, AssocPlusL, AssocPlusR,
    H, S, CX,
)
from compile.to_pytket import compile, compile_goi, Compiled, CompiledGOI
from compile.goi import (
    GateAtom, LoopSpec, GOIArtifact, Extracted,
    normalize_goi, is_yankable, collapse_feedback, try_extract,
)
from core.perm import WirePerm, identity


def qpow(n: int):
    """Build Q^n type (right-associated tensor of n qubits)."""
    assert n >= 1
    ty = Q()
    for _ in range(n - 1):
        ty = Ten(ty, Q())
    return ty


def cmds(circ) -> list:
    """Get commands from a circuit."""
    return list(circ.get_commands())


def op_name(cmd) -> str:
    """Get operation name from a command."""
    return cmd.op.type.name


def qubit_idxs(cmd) -> List[int]:
    """Get qubit indices from a command."""
    return [int(q.index[0]) for q in cmd.qubits]


def assert_no_swaps(circ):
    """Assert that a circuit contains no SWAP gates."""
    bad = [c for c in cmds(circ) if op_name(c).upper() == "SWAP"]
    assert not bad, f"Found SWAPs: {[(op_name(c), qubit_idxs(c)) for c in bad]}"


def assert_perm_eq(p: WirePerm, q: WirePerm):
    """Assert two permutations are equal."""
    assert p.n == q.n, f"Perm size mismatch: {p.n} != {q.n}"
    assert p.new_to_old == q.new_to_old, f"Perm mismatch: {p.new_to_old} != {q.new_to_old}"


def assert_atoms_equal(a1: GateAtom, a2: GateAtom, *, check_wires: bool = True):
    """Assert two gate atoms are equal.

    If check_wires=False, only compares gate_name.
    """
    assert a1.gate_name == a2.gate_name, f"Gate mismatch: {a1.gate_name} != {a2.gate_name}"
    if check_wires:
        assert a1.wires == a2.wires, f"Wire mismatch: {a1.wires} != {a2.wires}"


def gate_support(atom: GateAtom) -> Set[int]:
    """Get the set of wires this gate touches."""
    return atom.support()


def extract_cmd_stream(circ) -> List[str]:
    """Extract deterministic command stream representation."""
    result = []
    for cmd in cmds(circ):
        name = op_name(cmd)
        wires = qubit_idxs(cmd)
        result.append(f"{name}({','.join(map(str, wires))})")
    return result


def is_extracted(result) -> bool:
    """Check if result is Extracted or CompiledGOI (success)."""
    return isinstance(result, (Extracted, CompiledGOI))


def is_residual(result) -> bool:
    """Check if result is GOIArtifact (residual/failure)."""
    return isinstance(result, GOIArtifact)


def make_goi_artifact(
    n: int,
    atoms: List[Tuple[str, Tuple[int, ...]]],
    loops: List[int] = None,
    perm: List[int] = None
) -> GOIArtifact:
    """Build a GOIArtifact for testing.

    Args:
        n: number of wires
        atoms: list of (gate_name, wire_tuple)
        loops: list of loop sizes k
        perm: permutation new_to_old (default: identity)
    """
    gate_atoms = tuple(GateAtom(name, wires) for name, wires in atoms)
    loop_specs = tuple(LoopSpec(k) for k in (loops or []))
    p = WirePerm(n, perm) if perm else identity(n)
    return GOIArtifact(n_in=n, n_out=n, perm=p, atoms=gate_atoms, loops=loop_specs)
