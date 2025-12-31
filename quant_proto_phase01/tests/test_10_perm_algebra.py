# tests/test_10_perm_algebra.py
import random

from core.perm import WirePerm, identity, compose, inverse, block_swap


def random_perm(n: int) -> WirePerm:
    arr = list(range(n))
    random.shuffle(arr)
    return WirePerm(n, arr)


def test_identity_laws():
    for n in range(1, 8):
        p = random_perm(n)
        e = identity(n)
        assert compose(e, p).new_to_old == p.new_to_old
        assert compose(p, e).new_to_old == p.new_to_old


def test_inverse_laws():
    for n in range(1, 8):
        p = random_perm(n)
        pinv = inverse(p)
        e = identity(n)
        assert compose(pinv, p).new_to_old == e.new_to_old
        assert compose(p, pinv).new_to_old == e.new_to_old


def test_associativity():
    for n in range(1, 8):
        p = random_perm(n)
        q = random_perm(n)
        r = random_perm(n)
        left = compose(r, compose(q, p))
        right = compose(compose(r, q), p)
        assert left.new_to_old == right.new_to_old


def test_block_swap_involutive():
    # block_swap(m, n) is self-inverse only when m == n
    m, n = 3, 3
    p = block_swap(m, n)
    pinv = inverse(p)
    assert pinv.new_to_old == p.new_to_old
