# Structural example: TwistPlus (swap (+) summands)
# Expected: compiles to WirePerm only, perm = [1, 0]

from lang.types import Q, Plus
from lang.terms import TwistPlus

main = TwistPlus(Q(), Q())
