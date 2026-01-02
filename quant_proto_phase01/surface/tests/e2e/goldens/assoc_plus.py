# Structural example: AssocPlusL (reassociate (+) tree)
# (A + B) + C -> A + (B + C)
# Expected: compiles to WirePerm only

from lang.types import Q
from lang.terms import AssocPlusL

main = AssocPlusL(Q(), Q(), Q())
