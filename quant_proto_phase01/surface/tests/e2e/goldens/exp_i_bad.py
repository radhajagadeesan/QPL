# Certification example: exp_i with NON-involutive permutation (should FAIL)
# Uses a 3-cycle permutation which is NOT involutive (order 3, not 2)
# Expected: exp_i certification fails, error message identifies involution failure
#
# GOI Note: Involution certification checks p o p = id on the GOI boundary.
# A 3-cycle [2, 0, 1] has order 3: p o p = [1, 2, 0], p o p o p = [0, 1, 2].
# Since p o p != id, this is NOT involutive and must be rejected.

from lang.types import Q, Plus
from lang.terms import TwistPlus

# TwistPlus on (A+B)+C creates a 3-cycle permutation [2, 0, 1]
# This is NOT involutive!
a, b, c = Q(), Q(), Q()
non_involutive = TwistPlus(Plus(a, b), c)

main = non_involutive

# Certification check: J o J should equal Id
# [2, 0, 1] o [2, 0, 1] = [1, 2, 0] != [0, 1, 2]
# Therefore this is NOT involutive and exp_i(theta, J) must be REJECTED
