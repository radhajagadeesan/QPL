# Unitary example: CNOT (CX) gate on 2 qubits
# Expected: compiles to circuit with CX gate

from lang.types import Q, Ten
from lang.terms import CX

main = CX()
