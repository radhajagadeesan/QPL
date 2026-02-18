# src/backends/materialize.py
"""Permutation materialization: convert a WirePerm into an explicit SWAP network."""

from __future__ import annotations

from typing import List, Tuple

from core.perm import WirePerm


def swaps_for_perm(p: WirePerm) -> List[Tuple[int, int]]:
    n = p.n
    old_to_new = [0] * n
    for new, old in enumerate(p.new_to_old):
        old_to_new[old] = new

    swaps: List[Tuple[int, int]] = []
    pos = list(range(n))
    invpos = list(range(n))

    for wire in range(n):
        target_pos = old_to_new[wire]
        while invpos[wire] != target_pos:
            cur_pos = invpos[wire]
            other_wire = pos[target_pos]
            swaps.append((cur_pos, target_pos))
            pos[cur_pos], pos[target_pos] = pos[target_pos], pos[cur_pos]
            invpos[wire] = target_pos
            invpos[other_wire] = cur_pos
    return swaps


def apply_swaps(circ, swaps: List[Tuple[int, int]]) -> None:
    for a, b in swaps:
        if a != b:
            circ.SWAP(a, b)
