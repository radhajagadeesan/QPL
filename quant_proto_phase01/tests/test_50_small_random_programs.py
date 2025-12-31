# tests/test_50_small_random_programs.py
"""Small randomized smoke tests."""

import random

from lang.types import Q, Ten
from lang.terms import Id, Seq, TwistTen, AssocTenL, AssocTenR, H, S, CX
from compile.to_pytket import compile


def rand_ty3():
    return Ten(Ten(Q(), Q()), Q())


def rand_term(depth: int = 6):
    ty_total = rand_ty3()
    a = Ten(Q(), Q())
    b = Q()
    t = Id(ty_total)
    for _ in range(depth):
        choice = random.choice(["twist", "assocL", "assocR", "H", "S", "CX"])
        if choice == "twist":
            step = TwistTen(a, b)
        elif choice == "assocL":
            step = AssocTenL(Q(), Q(), Q())
        elif choice == "assocR":
            step = AssocTenR(Q(), Q(), Q())
        elif choice == "H":
            step = H(random.randrange(3), ty_total)
        elif choice == "S":
            step = S(random.randrange(3), ty_total)
        else:
            i, j = random.sample(range(3), 2)
            step = CX(i, j, ty_total)
        t = Seq(t, step)
    return t


def test_random_terms_compile():
    random.seed(0)
    for _ in range(50):
        out = compile(rand_term())
        assert out.circuit.n_qubits == 3
