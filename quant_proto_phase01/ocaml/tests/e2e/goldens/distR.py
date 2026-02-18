# Structural example: DistR (right distributivity)
# (A + B) ⊗ C -> (A ⊗ C) + (B ⊗ C)
# Expected: compiles to WirePerm only

from lang.types import Q
from lang.terms import DistR

main = DistR(Q(), Q(), Q())
