# Golden files (Phase 0–3 Integration Lockdown)

This folder holds **golden artifacts** used by the integration tests to enforce that:

- **Phases 0–2 are frozen**: same AST → identical command stream + final permutation.
- **Phase 3 is additive**: on acyclic terms, `compile_goi` matches `compile` exactly.

## Files

For each named test case `<case>`:

- `<case>.cmds.json` : canonical command stream list, e.g. `["H(0)", "CX(0,1)"]`
- `<case>.perm.json` : permutation mapping `new_to_old` list, e.g. `[1,0,2]`

Optional:
- `<case>.meta.json` : notes (width, type info), purely informational.

## How to generate / update

Run from repo root:

```bash
python scripts/generate_goldens.py
```

This will (re)generate goldens for the curated suite.

**Important:** Regenerating goldens changes the spec. Do this only when you intentionally
change frozen behavior and are ready to accept a breaking change.

