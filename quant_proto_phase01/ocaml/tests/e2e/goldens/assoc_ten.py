# Structural example: AssocTenL (reassociate tensor tree)
# (A ⊗ B) ⊗ C -> A ⊗ (B ⊗ C)
# Expected: compiles to WirePerm only

from lang.types import Q
from lang.terms import AssocTenL

main = AssocTenL(Q(), Q(), Q())
