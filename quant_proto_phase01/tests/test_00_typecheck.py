# tests/test_00_typecheck.py
import pytest

from lang.types import Q, Ten, Plus
from lang.terms import (
    Id, Seq, TenTerm,
    TwistTen, AssocTenL, AssocTenR,
    TwistPlus, AssocPlusL, AssocPlusR,
    DistL, DistR,
    H, S, CX,
)
from typing_.check import type_of, assert_well_typed, TypeCheckError


def test_id_is_well_typed():
    ty = Ten(Q(), Q())
    assert_well_typed(Id(ty))
    dom, cod = type_of(Id(ty))
    assert dom == ty
    assert cod == ty


def test_seq_requires_matching_types():
    ty3 = Ten(Q(), Ten(Q(), Q()))
    ty2 = Ten(Q(), Q())
    with pytest.raises(TypeCheckError):
        assert_well_typed(Seq(Id(ty3), Id(ty2)))


def test_gate_index_checks():
    ty = Ten(Q(), Q())
    assert_well_typed(H(0, ty))
    assert_well_typed(S(1, ty))
    assert_well_typed(CX(0, 1, ty))
    with pytest.raises(TypeCheckError):
        assert_well_typed(H(2, ty))
    with pytest.raises(TypeCheckError):
        assert_well_typed(CX(0, 0, ty))
