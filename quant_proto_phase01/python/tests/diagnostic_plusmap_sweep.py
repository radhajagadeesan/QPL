"""Diagnostic sweep over binary PlusMaps. NOT A TEST -- pytest does not
collect this file, and it must never become an acceptance gate.

Its acceptance value is ZERO. A leakage census over a machine-generated type
pool cannot say whether the compiler is right; it can only say which way a
change moved the population. Its one job is to separate, for any candidate
change:

    FIXED       leaking before -> clean after
    REGRESSED   clean before   -> leaking after     <-- the number that matters

A change that fixes thousands and regresses hundreds is not a net win; the
regressions are circuits that were correct and no longer are. The abandoned
whole-boundary transport scored 3736 fixed / 248 regressed, and those 248 are
what sent it to wip/plusmap-global-transport instead of into the tree.

Usage
-----
    PYTHONPATH=python/src python3 python/tests/diagnostic_plusmap_sweep.py > after.json
    PYTHONPATH=<baseline-src> python3 python/tests/diagnostic_plusmap_sweep.py > before.json
    python3 python/tests/diagnostic_plusmap_sweep.py --compare before.json after.json

The baseline tree is produced with, e.g.
    git show <ref>:quant_proto_phase01/python/src/compile/to_pytket.py
copied over a scratch copy of python/src.
"""

import json
import sys


def build_terms():
    from lang.types import Unit, Q, Ten, Plus
    from lang.terms import (Id, PlusMap, DistL, DistR, UndistL, UndistR,
                            TwistPlus, H as Hg, S as Sg)
    from compile.to_pytket import type_of
    I, q = Unit(), Q()
    mors = [Id(A) for A in (I, q, Plus(I, I), Ten(I, q))]
    mors += [Hg(0, q), Sg(0, q), TwistPlus(I, I)]
    for A in (I, q):
        for B in (I, q):
            for C in (I, q, Plus(I, I)):
                for K in (DistL, DistR, UndistL, UndistR):
                    try:
                        mors.append(K(A, B, C))
                    except Exception:
                        pass
    terms = []
    for l in mors:
        for r in mors:
            try:
                dl, _ = type_of(l)
                dr, _ = type_of(r)
                terms.append(PlusMap(dl, dr, l, r))
            except Exception:
                pass
    return terms


def sweep():
    """One entry per (term, mode).

    The key carries a stable case INDEX and the structural term repr, not just
    the type signature. Distinct programs routinely share a domain/codomain
    pair -- PlusMap(Q,Q,H,S) and PlusMap(Q,Q,S,H) both read `Q(+)Q => Q(+)Q`
    -- so a type-only key silently overwrote siblings and undercounted both
    fixes and regressions.
    """
    from compile.to_pytket import compile as tp_compile, type_of
    from compile.frames import leakage, pretty
    terms = build_terms()
    out = {}
    for i, t in enumerate(terms):
        try:
            sig = f"{pretty(type_of(t)[0])} => {pretty(type_of(t)[1])}"
        except Exception:
            sig = "<untypable>"
        key = f"{i:05d} | {sig} | {t!r}"
        for m in (False, True):
            try:
                c = tp_compile(t, materialize=m)
                U = c.circuit.get_unitary()
                out[f"{key} | m={m}"] = round(
                    float(leakage(c.input_frame, U, c.output_frame)), 9)
            except Exception as e:
                out[f"{key} | m={m}"] = "RAISE:" + type(e).__name__
    expected = 2 * len(terms)
    assert len(out) == expected, (
        f"key collision: {len(out)} entries for {len(terms)} terms "
        f"(expected {expected}). The key is not distinguishing programs.")
    return out


def compare(before_path, after_path):
    b = json.load(open(before_path))
    a = json.load(open(after_path))
    keys = set(b) | set(a)

    def clean(v):
        return isinstance(v, float) and v < 1e-9

    fixed, regressed, now_raises, other = [], [], [], 0
    for k in sorted(keys):
        x, y = b.get(k, "MISSING"), a.get(k, "MISSING")
        if x == y:
            continue
        if clean(y) and not clean(x):
            fixed.append((k, x, y))
        elif clean(x) and not clean(y):
            regressed.append((k, x, y))
        elif isinstance(y, str) and y.startswith("RAISE"):
            now_raises.append((k, x, y))
        else:
            other += 1
    print(f"cases: {len(keys)}")
    print(f"  FIXED      (leaking -> clean): {len(fixed)}")
    print(f"  REGRESSED  (clean -> leaking): {len(regressed)}   <-- the gate")
    print(f"  now raises                   : {len(now_raises)}")
    print(f"  other changes                : {other}")
    print("\n--- REGRESSED, in full ---")
    for k, x, y in regressed:
        print(f"  {k}\n      {x} -> {y}")
    return len(regressed)


if __name__ == "__main__":
    if len(sys.argv) == 4 and sys.argv[1] == "--compare":
        sys.exit(1 if compare(sys.argv[2], sys.argv[3]) else 0)
    print(json.dumps(sweep()))
