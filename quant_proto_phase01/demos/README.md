# Granthi Demos

Demonstrations of the Granthi quantum programming language.

## Python Demos (`demos/python/`)

Python API demonstrations. See `demos/python/README.md` for details.

```bash
PYTHONPATH=src python demos/python/<demo>.py
```

## OCaml E2E Demos (`surface/demos/`)

End-to-end OCaml demos using the Linear GADT module:

```bash
cd surface && dune exec demos/<demo>.exe
```

| Demo | What it Shows |
|------|---------------|
| `algorithms_e2e` | Parameterized Deutsch-Jozsa, HSP functor, Simon functor |
| `algorithmic_snippets` | Bell, GHZ, DJ, HSP, Simon in Linear GADT |
| `abstract_qswitch_e2e` | QSwitch pattern with structural isomorphisms |
| `qswitch_instantiated_e2e` | Compositional QSwitch with multiple gate pairs |
| `zn_controlled_phase_e2e` | Z2, Z4, Z5 controlled phase with binary decomposition |
| `short_circuit_e2e` | Witness routing, phased_omap0, phased_control |
| `linear_demo` | Core Linear DSL features + E2E compilation |
| `datatype_demo` | Datatype declarations, control combinator + E2E |
