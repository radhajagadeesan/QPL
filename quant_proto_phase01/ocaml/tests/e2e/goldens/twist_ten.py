# Structural example: TwistTen (swap tensor factors)
# A ⊗ B -> B ⊗ A
# Expected: compiles to WirePerm only, perm = [1, 0]

from lang.types import Q
from lang.terms import TwistTen

main = TwistTen(Q(), Q())
