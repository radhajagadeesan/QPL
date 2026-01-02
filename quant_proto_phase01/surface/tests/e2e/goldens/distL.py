# Structural example: DistL (left distributivity)
# A ⊗ (B + C) -> (A ⊗ B) + (A ⊗ C)
# Expected: compiles to WirePerm only

from lang.types import Q
from lang.terms import DistL

main = DistL(Q(), Q(), Q())
