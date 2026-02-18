# Certification example: exp_i with involutive permutation (should succeed)
# Uses TwistPlus which is involutive (swap o swap = id)
# Expected: compilation succeeds, certified exp_i atom emitted

import math
from lang.types import Q
from lang.terms import TwistPlus

# The involution J = TwistPlus (swap)
J = TwistPlus(Q(), Q())

# exp_i(pi/4, J) - rotation by pi/4 around the swap axis
theta = math.pi / 4
main = J  # The term to certify as involutive

# Certification check: J o J = Id
# TwistPlus satisfies this since [1,0] composed with [1,0] = [0,1]
