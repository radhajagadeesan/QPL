# Structural example: Identity
# Expected: compiles to WirePerm only, routing perm = [0, 1] (identity routing)
#
# GOI Note: In the GOI theoretical model, id_A compiles to the through-wire
# involution J_A on the doubled boundary. In our routing-based implementation,
# Id produces identity routing [0, 1, ...]. The key GOI property is that
# id is always involutive: perm o perm = id.

from lang.types import Q, Ten
from lang.terms import Id

main = Id(Ten(Q(), Q()))

# GOI Invariant: Id is trivially involutive
# Routing perm [0, 1] satisfies: [0, 1] o [0, 1] = [0, 1] (involutive)
