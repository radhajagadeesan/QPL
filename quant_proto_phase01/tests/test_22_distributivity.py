# tests/test_22_distributivity.py
"""Distributivity tests: compilation is intentionally deferred in Phase 0–1."""

import pytest

from lang.types import Q, Ten
from lang.terms import DistL, DistR
from compile.to_pytket import compile


def test_distL_compilation_deferred():
    a = Q()
    b = Ten(Q(), Q())
    c = Q()
    with pytest.raises(NotImplementedError):
        compile(DistL(a, b, c))


def test_distR_compilation_deferred():
    a = Q()
    b = Q()
    c = Ten(Q(), Q())
    with pytest.raises(NotImplementedError):
        compile(DistR(a, b, c))
