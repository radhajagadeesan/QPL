# Structural example: Combined structural operations
# Mixture of assoc/twist/dist across ⊗ and (+)
# Expected: compiles to WirePerm only

from lang.types import Q, Ten, Plus
from lang.terms import Seq, TenTerm, TwistPlus, TwistTensor, AssocPlusL, Id

a, b, c = Q(), Q(), Q()

# Compose: AssocPlusL ; (TwistPlus ⊗ Id) ; AssocPlusR-like
main = Seq(
    AssocPlusL(a, b, c),
    TenTerm(TwistPlus(a, b), Id(c))
)
