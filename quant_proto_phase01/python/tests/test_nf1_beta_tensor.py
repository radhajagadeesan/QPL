"""NF-1: bounded beta/tensor normalization experiment.

TEST-ONLY. Nothing here modifies the compiler, and the normalizer below is
NOT the paper's canonical-derivation interface. It implements exactly one
bounded form, called NF_beta_tensor:

    reducible:  Apply(Lam(..), arg)                     -- beta
                a Lam-headed nested application spine    -- iterated beta
                LetPair(x, y, Pair(a, b), body)          -- tensor elimination
    transparent relays recognised by the emitter:
                Seq(Lam(..), Id)   and   Seq(Id, Lam(..))
    normal:     neutral Var-headed spines, e.g. Apply(Var f, arg)

Anything else -- case/sum reductions, eta, structural laws -- is OUTSIDE
NF_beta_tensor and is deliberately NOT contracted here, because no calculus
rule has been cited for them in this experiment.

A positive result is evidence for the larger canonical-normal-derivation
hypothesis, not completion of it.
"""

import json
import os
import sys

import numpy as np
import pytest

import lang.terms as T
from lang.terms import (Id, Seq, Apply, Lam, Var, Pair, LetPair, TenTerm,
                        PlusMap, NPlusMap, PhasedPlusMap, Case, CaseExpr,
                        Ctrl, Feedback, ExpInvolution, Sum, DatatypeControl,
                        H as Hg)
from lang.types import Unit, Q, Ten, Plus, Arrow
from typing_.check import type_of

I, q = Unit(), Q()
qq = Arrow(q, q)
FIX = os.path.join(os.path.dirname(__file__), "fixtures")

# --- the complete Term union, pinned -----------------------------------------
COMPOSITES = ("Apply", "Case", "CaseExpr", "Ctrl", "DatatypeControl",
              "ExpInvolution", "Feedback", "Lam", "LetPair", "NPlusMap",
              "Pair", "PhasedPlusMap", "PlusMap", "Sum", "TenTerm", "Seq")

LEAVES = (
    'AssocPlusL', 'AssocPlusR', 'AssocTenL', 'AssocTenR', 'CCX', 'CH', 'CRz',
    'CS', 'CSWAP', 'CSdg', 'CX', 'CZ', 'Cap', 'Cup', 'DecodeQubit', 'DistL',
    'DistR', 'EncodeQubit', 'ExpSwap', 'FunVar', 'GlobalPhase', 'H', 'Id',
    'Phase', 'PhasedControl', 'Rx', 'Ry', 'Rz', 'S', 'Sdg', 'SumAssocL',
    'SumAssocR', 'SumTwist', 'T', 'TagPerm', 'Tdg', 'TensorAssocL',
    'TensorAssocR', 'TensorTwist', 'TwistPlus', 'TwistTen', 'UndistL',
    'UndistR', 'Var', 'WireIdentity', 'X', 'Y', 'Z')


class UnknownConstructor(Exception):
    """An exhaustive visitor met a constructor it does not know."""


import lang.terms as T


def _kind(t):
    n = type(t).__name__
    if n in COMPOSITES or n in LEAVES:
        return n
    raise UnknownConstructor(
        f"{n} is in neither COMPOSITES nor LEAVES -- the Term union has "
        f"changed and this experiment must be re-audited. It must NEVER be "
        f"treated as normal by falling through.")


def children(t):
    """Sub-TERMS of a node. Exhaustive or fail; non-term metadata excluded."""
    k = _kind(t)
    if k in LEAVES:
        return []
    if k == "Apply":            return [t.f, t.arg]
    if k == "Seq":              return [t.f, t.g]
    if k == "TenTerm":          return [t.f, t.g]
    if k == "Pair":             return [t.fst, t.snd]
    if k == "Lam":              return [t.body]
    if k == "LetPair":          return [t.pair, t.body]
    if k == "Case":             return [t.left, t.right]
    if k == "CaseExpr":         return [t.scrut, t.left, t.right]
    if k == "PlusMap":          return [t.left, t.right]
    if k == "PhasedPlusMap":    return [t.left, t.right]
    if k == "Sum":              return [t.left, t.right]
    if k == "NPlusMap":         return list(t.branches)
    if k == "DatatypeControl":  return list(t.branches)
    if k == "Ctrl":             return [t.body]
    if k == "Feedback":         return [t.body]
    if k == "ExpInvolution":    return [t.body]
    raise UnknownConstructor(f"no child rule for composite {k}")


def rebuild(t, kids):
    """Rebuild a node from new children, preserving all non-term metadata."""
    k = _kind(t)
    if k in LEAVES:
        return t
    if k == "Apply":            return Apply(kids[0], kids[1])
    if k == "Seq":              return Seq(kids[0], kids[1])
    if k == "TenTerm":          return TenTerm(kids[0], kids[1])
    if k == "Pair":             return Pair(kids[0], kids[1])
    if k == "Lam":              return Lam(t.name, t.dom, t.cod, kids[0])
    if k == "LetPair":          return LetPair(t.x, t.y, t.ty_x, t.ty_y,
                                               kids[0], kids[1])
    if k == "Case":             return Case(t.ty_left, t.ty_right,
                                            kids[0], kids[1])
    if k == "CaseExpr":         return CaseExpr(kids[0], t.x, t.y, t.ty_x,
                                                t.ty_y, kids[1], kids[2])
    if k == "PlusMap":          return PlusMap(t.ty_left, t.ty_right,
                                               kids[0], kids[1])
    if k == "PhasedPlusMap":    return PhasedPlusMap(t.theta, t.ty_left,
                                                     t.ty_right, kids[0],
                                                     kids[1])
    if k == "Sum":              return Sum(t.alpha_theta, t.beta_theta,
                                           kids[0], kids[1])
    if k == "NPlusMap":         return NPlusMap(t.summand_types, tuple(kids))
    if k == "DatatypeControl":  return DatatypeControl(t.name, t.arity,
                                                       t.dt_rep, t.a_ty,
                                                       tuple(kids))
    if k == "Ctrl":             return Ctrl(kids[0])
    if k == "Feedback":         return Feedback(t.k, kids[0])
    if k == "ExpInvolution":    return ExpInvolution(t.theta, kids[0],
                                                     t.ty_total)
    raise UnknownConstructor(f"no rebuild rule for composite {k}")


def binders(t):
    """(name, type) pairs a node binds over which of its children."""
    k = _kind(t)
    if k == "Lam":      return {0: [(t.name, t.dom)]}
    if k == "LetPair":  return {1: [(t.x, t.ty_x), (t.y, t.ty_y)]}
    if k == "CaseExpr": return {1: [(t.x, t.ty_x)], 2: [(t.y, t.ty_y)]}
    return {}


# ---------------------------------------------------------------------------
# The NF_beta_tensor predicate
# ---------------------------------------------------------------------------

def _spine_head(t):
    while True:
        if _kind(t) == "Apply":
            t = t.f
        elif _kind(t) == "Seq" and _kind(t.g) == "Id":
            t = t.f                       # transparent relay Seq(_, Id)
        elif _kind(t) == "Seq" and _kind(t.f) == "Id":
            t = t.g                       # transparent relay Seq(Id, _)
        else:
            return t


def first_redex(t, path="root"):
    k = _kind(t)
    if k == "Apply" and _kind(_spine_head(t)) == "Lam":
        return path
    if k == "LetPair" and _kind(t.pair) == "Pair":
        return path
    for i, c in enumerate(children(t)):
        r = first_redex(c, f"{path}.{_child_name(t, i)}")
        if r:
            return r
    return None


def _child_name(t, i):
    k = _kind(t)
    names = {"Apply": ["f", "arg"], "Seq": ["f", "g"], "TenTerm": ["f", "g"],
             "Pair": ["fst", "snd"], "Lam": ["body"],
             "LetPair": ["pair", "body"], "Case": ["left", "right"],
             "CaseExpr": ["scrut", "left", "right"],
             "PlusMap": ["left", "right"], "PhasedPlusMap": ["left", "right"],
             "Sum": ["left", "right"], "Ctrl": ["body"],
             "Feedback": ["body"], "ExpInvolution": ["body"]}
    if k in names:
        return names[k][i]
    return f"branch[{i}]"


def is_nf_beta_tensor(t):
    return first_redex(t) is None




# ===========================================================================
# PART 3 -- the test-only normalizer
# ===========================================================================
#
# Does NOT call the compiler's _normalize or _substitute. Alpha-uniquifies
# binders first, so substitution afterwards is capture-avoiding by
# construction; then contracts beta/LetPair redexes to a fixed point with a
# fuel guard.

def all_names(t, acc=None):
    """Every name occurring in `t`, bound OR free, including FunVar."""
    acc = set() if acc is None else acc
    k = _kind(t)
    if k in ("Var", "FunVar"):
        acc.add(t.name)
        return acc
    for nm, _ in sum(binders(t).values(), []):
        acc.add(nm)
    for c in children(t):
        all_names(c, acc)
    return acc


def fresh_avoiding(base, avoid):
    """A name outside `avoid`, chosen deterministically.

    Must be outside ALL free and bound names of the term and of the
    substitution range -- a counter alone is not enough: a term may already
    contain `x#1`, and reusing it would capture.
    """
    root = base.split("#")[0]
    i = 0
    while True:
        cand = f"{root}#{i}"
        if cand not in avoid:
            return cand
        i += 1


def free_names(t):
    return {n for (n, _ty) in _fv(t)}


def canonicalize(t, ren=None, counter=None, avoid=None):
    """Rename binders to canonical names in traversal order.

    Canonical names are drawn from v0, v1, ... but SKIP the term's global
    free-name set. Without that, canonicalizing

        Lam x. (x, v0)          -- v0 free

    renames the binder to v0 and captures the free occurrence.

    Deterministic and STABLE on a second pass: `nf` preserves free variables,
    so the same avoid-set is computed again and the same names are chosen,
    which is what keeps `nf` exactly syntactically idempotent.
    """
    if avoid is None:
        avoid = free_names(t)
    ren = {} if ren is None else ren
    counter = [0] if counter is None else counter

    def _next():
        while True:
            nm = f"v{counter[0]}"
            counter[0] += 1
            if nm not in avoid:
                return nm
    k = _kind(t)
    if k in ("Var", "FunVar"):
        nm = ren.get(t.name, t.name)
        return Var(nm, t.ty) if k == "Var" else T.FunVar(nm, t.dom, t.cod)
    if k in LEAVES:
        return t
    bs = binders(t)
    if not bs:
        return rebuild(t, [canonicalize(c, ren, counter, avoid)
                           for c in children(t)])
    if k == "Lam":
        nn = _next()
        return Lam(nn, t.dom, t.cod,
                   canonicalize(t.body, {**ren, t.name: nn}, counter, avoid))
    if k == "LetPair":
        pair = canonicalize(t.pair, ren, counter, avoid)
        nx, ny = _next(), _next()
        return LetPair(nx, ny, t.ty_x, t.ty_y, pair,
                       canonicalize(t.body, {**ren, t.x: nx, t.y: ny},
                                    counter, avoid))
    if k == "CaseExpr":
        scrut = canonicalize(t.scrut, ren, counter, avoid)
        nx, ny = _next(), _next()
        return CaseExpr(scrut, nx, ny, t.ty_x, t.ty_y,
                        canonicalize(t.left, {**ren, t.x: nx}, counter, avoid),
                        canonicalize(t.right, {**ren, t.y: ny}, counter,
                                     avoid))
    raise UnknownConstructor(f"no canonical rule for binder node {k}")


def subst(t, name, rep):
    """Capture-avoiding substitution.

    Binders that would capture a free variable of `rep` are renamed. Never
    reuses the compiler's `_substitute`, which only skips shadowed bodies and
    can therefore capture.
    """
    k = _kind(t)
    if k == "Var":
        return rep if t.name == name else t
    if k == "FunVar":
        return rep if t.name == name else t
    if k in LEAVES:
        return t
    rep_fv = {n for (n, _ty) in _fv(rep)}
    bs = binders(t)
    if not bs:
        return rebuild(t, [subst(c, name, rep) for c in children(t)])

    avoid = all_names(t) | all_names(rep) | {name}

    def rebind(node_names, tys):
        """Rename any binder that shadows `name` or would capture rep's fv.

        The replacement name avoids EVERY name in the term and in the
        substitution range, so a term already containing `x#1` cannot be
        collided with.
        """
        out, ren = [], {}
        for nm in node_names:
            if nm == name or nm in rep_fv:
                nn = fresh_avoiding(nm, avoid)
                avoid.add(nn)
                ren[nm] = nn
                out.append(nn)
            else:
                out.append(nm)
        return out, ren

    if k == "Lam":
        (nn,), ren = rebind([t.name], [t.dom])
        body = alpha_rename(t.body, ren)
        if nn == name:                       # still shadowed: stop here
            return Lam(nn, t.dom, t.cod, body)
        return Lam(nn, t.dom, t.cod, subst(body, name, rep))
    if k == "LetPair":
        pair = subst(t.pair, name, rep)
        (nx, ny), ren = rebind([t.x, t.y], [t.ty_x, t.ty_y])
        body = alpha_rename(t.body, ren)
        if name in (nx, ny):
            return LetPair(nx, ny, t.ty_x, t.ty_y, pair, body)
        return LetPair(nx, ny, t.ty_x, t.ty_y, pair, subst(body, name, rep))
    if k == "CaseExpr":
        scrut = subst(t.scrut, name, rep)
        (nx, ny), ren = rebind([t.x, t.y], [t.ty_x, t.ty_y])
        left = alpha_rename(t.left, {t.x: nx} if t.x in ren else {})
        right = alpha_rename(t.right, {t.y: ny} if t.y in ren else {})
        left = left if nx == name else subst(left, name, rep)
        right = right if ny == name else subst(right, name, rep)
        return CaseExpr(scrut, nx, ny, t.ty_x, t.ty_y, left, right)
    raise UnknownConstructor(f"no subst rule for binder node {k}")


def alpha_rename(t, ren):
    """Apply a renaming map to free occurrences."""
    if not ren:
        return t
    k = _kind(t)
    if k == "Var":
        return Var(ren.get(t.name, t.name), t.ty)
    if k == "FunVar":
        return T.FunVar(ren.get(t.name, t.name), t.dom, t.cod)
    if k in LEAVES:
        return t
    bs = binders(t)
    kids = []
    for i, c in enumerate(children(t)):
        shadowed = {n for n, _ in bs.get(i, [])}
        sub = {a: b for a, b in ren.items() if a not in shadowed}
        kids.append(alpha_rename(c, sub))
    return rebuild(t, kids)


class NormalizationFuelExceeded(Exception):
    pass


def nf(t, fuel=10000):
    """NF_beta_tensor: contract to a fixed point, then CANONICALIZE.

    Canonicalizing last (rather than uniquifying first) is what makes `nf`
    exactly syntactically idempotent: nf(nf(t)) reproduces the same binder
    names and every constructor field, with no metadata erased.
    """
    cur = canonicalize(t)
    for _ in range(fuel):
        nxt = _step(cur)
        if nxt is None:
            return canonicalize(cur)
        cur = nxt
    raise NormalizationFuelExceeded(
        f"exceeded {fuel} steps; first remaining redex at {first_redex(cur)}")


def _step(t):
    """One outermost-first contraction, or None if already normal."""
    k = _kind(t)
    if k == "Apply":
        head = _spine_head(t)
        if _kind(head) == "Lam":
            red = _contract_spine(t)
            if red is not None:
                return red
    if k == "LetPair" and _kind(t.pair) == "Pair":
        b = subst(t.body, t.x, t.pair.fst)
        return subst(b, t.y, t.pair.snd)
    kids = children(t)
    for i, c in enumerate(kids):
        s = _step(c)
        if s is not None:
            new = list(kids)
            new[i] = s
            return rebuild(t, new)
    return None


def _contract_spine(t):
    """Contract the outermost beta of a Lam-headed application spine."""
    args = []
    cur = t
    while _kind(cur) == "Apply":
        args.append(cur.arg)
        cur = cur.f
        while _kind(cur) == "Seq" and _kind(cur.g) == "Id":
            cur = cur.f
        while _kind(cur) == "Seq" and _kind(cur.f) == "Id":
            cur = cur.g
    if _kind(cur) != "Lam":
        return None
    args.reverse()                      # outermost Apply supplies innermost arg
    body = subst(cur.body, cur.name, args[0])
    for a in args[1:]:
        body = Apply(body, a)
    return body


# ===========================================================================
# PART 2 -- capture avoidance
# ===========================================================================
#
# to_pytket._substitute is deliberately NOT reused: it is capture-unsafe
# (it never renames a binder) and structurally incomplete.

def _fv(t, bound=frozenset()):
    """Typed free-variable multiset, exhaustive over the union."""
    k = _kind(t)
    if k == "Var":
        return {} if t.name in bound else {(t.name, str(t.ty)): 1}
    if k == "FunVar":
        # FunVar IS a lexically bound occurrence -- "Function variable:
        # x : A -> B" -- so it must appear in free-variable analysis,
        # renaming and substitution, not be treated as an opaque leaf.
        key = (t.name, str(Arrow(t.dom, t.cod)))
        return {} if t.name in bound else {key: 1}
    out = {}
    bs = binders(t)
    for i, c in enumerate(children(t)):
        inner = bound | {n for n, _ in bs.get(i, [])}
        for key, n in _fv(c, inner).items():
            out[key] = out.get(key, 0) + n
    return out


@pytest.mark.parametrize("case", ["lam", "letpair_x", "letpair_y",
                                  "caseexpr_x", "caseexpr_y", "nested"])
def test_substitution_is_capture_avoiding(case):
    """Substituting a replacement whose free `y` would be captured by an
    inner binder must rename that binder, never capture."""
    rep = Var("y", q)
    if case == "lam":
        term = Lam("y", q, q, Var("x", q))
    elif case == "letpair_x":
        term = LetPair("y", "b", q, q, Id(Ten(q, q)), Var("x", q))
    elif case == "letpair_y":
        term = LetPair("a", "y", q, q, Id(Ten(q, q)), Var("x", q))
    elif case == "caseexpr_x":
        term = CaseExpr(Id(Plus(q, q)), "y", "b", q, q, Var("x", q), Id(q))
    elif case == "caseexpr_y":
        term = CaseExpr(Id(Plus(q, q)), "a", "y", q, q, Id(q), Var("x", q))
    else:
        term = Lam("y", q, q, Lam("y", q, q, Var("x", q)))

    got = subst(term, "x", rep)
    # the free y of the replacement must still be FREE in the result
    assert ("y", str(q)) in _fv(got), (
        f"{case}: the replacement's free y was CAPTURED -> {got}")


def test_substitution_leaves_neutral_term_exactly_unchanged():
    """Exactly unchanged -- not merely 'same free variables'."""
    t = Apply(Var("f", qq), Id(q))
    assert structurally_equal(subst(t, "absent", Var("w", q)), t)


def test_fresh_names_are_deterministic():
    term = Lam("y", q, q, Var("x", q))
    assert repr(subst(term, "x", Var("y", q))) == \
           repr(subst(term, "x", Var("y", q)))
    outer = Apply(Lam("x", q, q, Lam("y", q, q, Var("x", q))), Id(q))
    assert repr(nf(outer)) == repr(nf(outer)), "nf is not deterministic"


def test_canonicalization_does_not_capture_a_free_canonical_name():
    """`Lam x. (x, v0)` with v0 FREE.

    Naive canonicalization renames the binder to v0 and captures. Canonical
    names must be drawn outside the term's global free-name set.
    """
    t = Lam("x", q, Ten(q, q), Pair(Var("x", q), Var("v0", q)))
    assert ("v0", str(q)) in _fv(t)
    assert _fv(nf(t)) == _fv(t), "canonicalization captured the free v0"


def test_substitution_avoids_a_preexisting_suffixed_collision():
    """`Lam x. (x, (z, x#1))`, substituting z := x.

    The replacement really is inserted (z occurs), so the binder x MUST be
    renamed -- and to neither `x` (would capture the inserted x) nor `x#1`
    (would capture the pre-existing free name). Every resource occurs once.
    """
    term = Lam("x", q, Ten(q, Ten(q, q)),
               Pair(Var("x", q), Pair(Var("z", q), Var("x#1", q))))
    before = _fv(term)
    assert ("z", str(q)) in before and ("x#1", str(q)) in before

    got = subst(term, "z", Var("x", q))
    assert _kind(got) == "Lam"
    assert got.name not in ("x", "x#1"), (
        f"binder renamed to a colliding name: {got.name}")
    after = _fv(got)
    assert ("x", str(q)) in after, "the inserted x was captured by the binder"
    assert ("x#1", str(q)) in after, "the pre-existing free x#1 was captured"
    assert all(v == 1 for v in after.values()), f"non-linear result: {after}"


def structurally_equal(a, b):
    """Exact structural equality INCLUDING binder names and every field.

    Seq has __slots__ rather than dataclass __eq__, so equality is recursive
    and explicit; nothing is erased to make a comparison succeed.
    """
    ka, kb = _kind(a), _kind(b)
    if ka != kb:
        return False
    if ka in LEAVES:
        return repr(a) == repr(b)
    meta_a = [getattr(a, f, None) for f in
              ("name", "x", "y", "dom", "cod", "ty_x", "ty_y", "ty_left",
               "ty_right", "theta", "alpha_theta", "beta_theta", "arity",
               "dt_rep", "a_ty", "k", "ty_total", "summand_types")]
    meta_b = [getattr(b, f, None) for f in
              ("name", "x", "y", "dom", "cod", "ty_x", "ty_y", "ty_left",
               "ty_right", "theta", "alpha_theta", "beta_theta", "arity",
               "dt_rep", "a_ty", "k", "ty_total", "summand_types")]
    if meta_a != meta_b:
        return False
    ca, cb = children(a), children(b)
    return len(ca) == len(cb) and all(
        structurally_equal(x, y) for x, y in zip(ca, cb))


def binder_census(t):
    """Every binder occurrence, as an ordered multiset of (kind, name, type).

    An independent linearity/preservation check: type_of plus free-variable
    equality does not prove a binder was neither duplicated nor dropped.
    """
    out = []
    k = _kind(t)
    if k not in LEAVES:
        for nm, ty in sum(binders(t).values(), []):
            out.append((k, nm, str(ty)))
        for c in children(t):
            out.extend(binder_census(c))
    return out


class LinearityReport:
    def __init__(self):
        self.uses = {}          # binder identity (path) -> occurrence count
        self.free = {}          # (name, type) -> count
        self.binders = {}       # binder identity -> (name, type)

    def __repr__(self):
        return f"LinearityReport(uses={self.uses}, free={self.free})"


def lexical_scan(t, path="root", env=None, rep=None):
    """Scope-aware resolution of every Var/FunVar to its NEAREST binder.

    Counting textual names cannot distinguish two shadowed binders that share
    a name, and cannot tell a bound occurrence from a free one. Each binder
    gets a lexical IDENTITY (its path), each occurrence resolves to the
    innermost enclosing binder of that name, and anything unresolved is free.
    """
    env = {} if env is None else env
    rep = LinearityReport() if rep is None else rep
    k = _kind(t)
    if k in ("Var", "FunVar"):
        ty = t.ty if k == "Var" else Arrow(t.dom, t.cod)
        ident = env.get(t.name)
        if ident is None:
            key = (t.name, str(ty))
            rep.free[key] = rep.free.get(key, 0) + 1
        else:
            rep.uses[ident] = rep.uses.get(ident, 0) + 1
        return rep
    if k in LEAVES:
        return rep
    bs = binders(t)
    for i, c in enumerate(children(t)):
        sub = dict(env)
        for j, (nm, ty) in enumerate(bs.get(i, [])):
            ident = f"{path}#{i}.{j}:{nm}"
            rep.binders[ident] = (nm, str(ty))
            rep.uses.setdefault(ident, 0)
            sub[nm] = ident            # innermost wins: shadows any outer
        lexical_scan(c, f"{path}.{_child_name(t, i)}", sub, rep)
    return rep


def assert_linear(t, where=""):
    """Every surviving binder is used EXACTLY once. Not <= : deletion fails."""
    rep = lexical_scan(t)
    bad = [(i, n) for i, n in rep.uses.items() if n != 1]
    assert not bad, (
        f"{where}: binders not used exactly once: "
        f"{[(rep.binders[i][0], i, n) for i, n in bad]}")
    return rep


def _count_var(t, name):
    k = _kind(t)
    if k in ("Var", "FunVar"):
        return 1 if t.name == name else 0
    if k in LEAVES:
        return 0
    return sum(_count_var(c, name) for c in children(t))


def test_substitution_reaches_every_composite():
    """A variable beneath every composite constructor must be substituted."""
    v = Var("x", q)
    r = Var("r", q)
    nodes = {
        "Seq": Seq(v, Id(q)), "TenTerm": TenTerm(v, Id(q)),
        "Pair": Pair(v, Id(q)), "Apply": Apply(Var("f", qq), v),
        "Lam": Lam("z", q, q, v), "LetPair": LetPair("a", "b", q, q, Id(Ten(q,q)), v),
        "Case": Case(q, q, v, Id(q)), "PlusMap": PlusMap(q, q, v, Id(q)),
        "PhasedPlusMap": PhasedPlusMap(0.0, q, q, v, Id(q)),
        "Sum": Sum(0.0, 0.0, v, Id(q)),
        "NPlusMap": NPlusMap((q, q), (v, Id(q))),
        "Ctrl": Ctrl(v), "Feedback": Feedback(1, v),
        "ExpInvolution": ExpInvolution(0.0, v, q),
        "CaseExpr": CaseExpr(Id(Plus(q, q)), "a", "b", q, q, v, Id(q)),
        "DatatypeControl": DatatypeControl("D2", 2, Plus(I, I), q, (v, Id(q))),
        "TenTerm2": TenTerm(Id(q), v),
        "Apply.f": Apply(v, Id(q)),
    }
    bad = []
    for name, node in nodes.items():
        out = subst(node, "x", r)
        if _count_var(out, "x") != 0:
            bad.append(f"{name}: target x survived")
        if _count_var(out, "r") != 1:
            bad.append(f"{name}: marker r appears {_count_var(out,'r')}x, "
                       f"expected exactly 1")
    assert not bad, "; ".join(bad)


# --- FunVar -------------------------------------------------------------
#
# SOURCE RULE. FunVar is produced by OCaml Core elaboration, and that is
# where its binding status is fixed -- not in the Python backend.
#
#   ocaml/lib/elaborate.ml:528
#       | Some (Ast.TyArrow (a, b)) -> Core.FunVar (x, a, b)
#   ocaml/lib/elaborate.ml:545
#       Core.Lam (x, a, b, body')
#
# An arrow-typed `Ast.Var x` elaborates to `Core.FunVar (x, a, b)`; the
# arrow-typed `Ast.Lam (x, ty, body)` is KEPT as `Core.Lam (x, a, b, body')`
# with the same binder name x. So the FunVar occurrences of x sit BENEATH the
# Core.Lam that binds x: a FunVar is a lexically bound occurrence exactly when
# an enclosing Lam introduces its name, and must therefore participate in
# free-variable analysis, alpha-renaming and capture-avoiding substitution.
#
# NOTE: this is NOT a claim about the Python backend. `_find_lam` /
# `_resolve_term` look up `Var`, not `FunVar`; the binding discipline asserted
# here comes from the elaborator above.

def test_funvar_is_free_when_unbound():
    fv = T.FunVar("f", q, q)
    assert ("f", str(Arrow(q, q))) in _fv(fv)


def test_funvar_is_bound_by_an_enclosing_lam():
    term = Lam("f", qq, qq, T.FunVar("f", q, q))
    assert _fv(term) == {}, f"FunVar not bound by the enclosing Lam: {_fv(term)}"
    rep = lexical_scan(term)
    assert list(rep.uses.values()) == [1], (
        f"FunVar occurrence not resolved to the binder: {rep}")


def test_funvar_is_alpha_renamed():
    got = alpha_rename(T.FunVar("f", q, q), {"f": "g"})
    assert _kind(got) == "FunVar" and got.name == "g"
    assert (got.dom, got.cod) == (q, q), "FunVar metadata changed"


def test_funvar_is_substituted():
    got = subst(T.FunVar("f", q, q), "f", Var("w", qq))
    assert _kind(got) == "Var" and got.name == "w"


def test_funvar_binder_is_renamed_to_avoid_capture():
    """`z` occurs UNDER the binder `f`; substituting z := f must not capture.

    The previous version substituted for a variable the term did not contain,
    so nothing was ever inserted and the test could not fail.
    """
    term = Lam("f", qq, Ten(qq, qq),
               Pair(T.FunVar("f", q, q), Var("z", qq)))
    assert _count_var(term, "z") == 1, "the test term must contain z"

    got = subst(term, "z", T.FunVar("f", q, q))   # inserting a FREE f
    assert _kind(got) == "Lam"
    assert got.name != "f", (
        "binder not renamed: the inserted free f is captured")

    rep = lexical_scan(got)
    assert rep.free.get(("f", str(qq))) == 1, (
        f"the inserted f is no longer free exactly once: {rep.free}")
    assert list(rep.uses.values()) == [1], (
        f"the original bound FunVar does not resolve exactly once: {rep}")
    ident, = rep.uses
    assert rep.binders[ident][0] == got.name, (
        f"the bound FunVar resolves to {rep.binders[ident][0]!r}, "
        f"not to the renamed binder {got.name!r}")


def test_unknown_constructor_fails_loudly():
    class Bogus:
        pass
    with pytest.raises(UnknownConstructor):
        _kind(Bogus())


# ===========================================================================
# PART 4 -- the hypothesis run
# ===========================================================================

def _fixture(name):
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..",
                                    "ocaml"))
    from bridge import parse_term
    with open(os.path.join(FIX, name + ".json")) as f:
        return parse_term(json.load(f))


class BetaShortcutObserver:
    """Observe _peel_apply_chain / _find_lam WITHOUT changing them.

    A normalized witness must not let the compiler secretly finish the
    normalization: calls may be observed, but neither may PRODUCE a reduct
    or SELECT a beta path.
    """
    def __init__(self, monkeypatch):
        import compile.to_pytket as tp
        self.peel_calls = self.peel_reducts = 0
        self.find_calls = self.find_selected = 0
        real_peel, real_find = tp._peel_apply_chain, tp._find_lam

        def peel(t, env):
            self.peel_calls += 1
            r = real_peel(t, env)
            if r is not None:
                self.peel_reducts += 1
            return r

        def find(f, env):
            self.find_calls += 1
            r = real_find(f, env)
            if r is not None:
                self.find_selected += 1
            return r

        monkeypatch.setattr(tp, "_peel_apply_chain", peel)
        monkeypatch.setattr(tp, "_find_lam", find)

    def assert_no_beta(self, where):
        assert self.peel_reducts == 0, (
            f"{where}: _peel_apply_chain produced {self.peel_reducts} reduct(s) "
            f"on a NORMALIZED witness -- the compiler finished the "
            f"normalization itself")
        assert self.find_selected == 0, (
            f"{where}: _find_lam selected a beta path {self.find_selected} "
            f"time(s) on a NORMALIZED witness")


H_M = np.array([[1, 1], [1, -1]], complex) / np.sqrt(2)
S_M = np.array([[1, 0], [0, 1j]], complex)
T_M = np.array([[1, 0], [0, np.exp(1j * np.pi / 4)]], complex)
Z3 = Plus(I, Plus(I, I))
Z3A = Ten(Z3, q)
MODES = [False, True]
ATOL = 1e-10


def _hst():
    M = np.zeros((6, 6), complex)
    for k, blk in enumerate((H_M, S_M, T_M)):
        M[2 * k:2 * k + 2, 2 * k:2 * k + 2] = blk
    return M


def _witness(letter):
    sys.path.insert(0, os.path.dirname(__file__))
    import test_release_safety as RS
    if letter == "C":
        return RS._noncontiguous_witness()
    if letter == "D":
        return Apply(_fixture("curried_select_3_applied_hst"), Id(Z3A))
    if letter == "G":
        return RS._captured_witness()
    if letter == "E":
        return _fixture("qswitch_eta_endoQ")
    if letter == "F":
        return _fixture("ctrl_ho_closed_plus_map")
    raise KeyError(letter)


def _run_normalized(letter, materialize, monkeypatch):
    from compile.to_pytket import compile as ccompile
    from compile.frames import semantic_action, leakage
    t = nf(_witness(letter))
    assert is_nf_beta_tensor(t), (
        f"{letter}: still has a redex after nf at {first_redex(t)}")
    obs = BetaShortcutObserver(monkeypatch)
    r = ccompile(t, materialize=materialize)
    obs.assert_no_beta(letter)
    U = r.circuit.get_unitary()
    return r, U, semantic_action(r.input_frame, U, r.output_frame), \
        leakage(r.input_frame, U, r.output_frame)


@pytest.mark.parametrize("materialize", MODES)
def test_C_normalized_is_exact(materialize, monkeypatch):
    r, U, sem, lk = _run_normalized("C", materialize, monkeypatch)
    assert lk < ATOL, f"C: leakage {lk:.6e}"
    assert abs(r.global_phase) < 1e-12
    np.testing.assert_allclose(sem, np.kron(np.eye(2), H_M),
                               atol=ATOL, rtol=0.0)


@pytest.mark.parametrize("materialize", MODES)
def test_D_normalized_is_exact(materialize, monkeypatch):
    r, U, sem, lk = _run_normalized("D", materialize, monkeypatch)
    assert lk < ATOL, f"D: leakage {lk:.6e}"
    assert abs(r.global_phase) < 1e-12
    np.testing.assert_allclose(sem, _hst(), atol=ATOL, rtol=0.0)


@pytest.mark.parametrize("materialize", MODES)
def test_G_normalized_is_exact(materialize, monkeypatch):
    r, U, sem, lk = _run_normalized("G", materialize, monkeypatch)
    assert lk < ATOL, f"G: leakage {lk:.6e}"
    assert abs(r.global_phase) < 1e-12
    np.testing.assert_allclose(sem, H_M, atol=ATOL, rtol=0.0)


def test_nf_preserves_lexical_linearity_and_free_variables():
    """Linearity holds BEFORE and AFTER, and FV is preserved exactly.

    Checking only the normal form would let a non-linear source slip through
    and would not establish that normalization PRESERVES linearity: the
    property has to hold at both ends of the rewrite.
    """
    for letter in ("C", "D", "E", "F", "G"):
        t = _witness(letter)
        n = nf(t)
        assert_linear(t, f"{letter} (original)")
        assert_linear(n, f"{letter} (normalized)")
        assert lexical_scan(n).free == lexical_scan(t).free, (
            f"{letter}: free-variable multiset changed")


def test_nf_is_exactly_idempotent_on_every_witness():
    """nf(nf(t)) reproduces nf(t) exactly -- structurally AND as text.

    An executable gate, not a docstring claim. `repr` equality additionally
    catches metadata (types, widths, indices) that structural equality on
    the constructors alone might not reach.
    """
    for letter in ("C", "D", "E", "F", "G"):
        n = nf(_witness(letter))
        again = nf(n)
        assert structurally_equal(again, n), (
            f"{letter}: nf is not structurally idempotent\n"
            f"  nf(t)     {n}\n  nf(nf(t)) {again}")
        assert repr(again) == repr(n), (
            f"{letter}: nf(nf(t)) differs from nf(t) in repr (metadata)\n"
            f"  nf(t)     {repr(n)}\n  nf(nf(t)) {repr(again)}")


# --- negative controls: the checker must REJECT these -----------------------

def test_linearity_checker_rejects_an_unused_binder():
    with pytest.raises(AssertionError):
        assert_linear(Lam("x", q, q, Id(q)))          # x never used


def test_linearity_checker_rejects_a_duplicated_use():
    with pytest.raises(AssertionError):
        assert_linear(Lam("x", q, Ten(q, q),
                          Pair(Var("x", q), Var("x", q))))


def test_linearity_checker_distinguishes_shadowed_same_name_binders():
    """Two binders both named `x`; the inner is used twice, the outer never.

    A textual counter sees 'x used twice' and could call it balanced. Lexical
    identities must attribute both uses to the INNER binder and report the
    outer as unused.
    """
    term = Lam("x", q, Ten(q, q),
               Lam("x", q, Ten(q, q), Pair(Var("x", q), Var("x", q))))
    rep = lexical_scan(term)
    counts = sorted(rep.uses.values())
    assert counts == [0, 2], f"expected one unused and one doubled: {counts}"
    with pytest.raises(AssertionError):
        assert_linear(term)


def test_constructor_coverage_is_pinned_to_the_declared_union():
    """Coverage is pinned to typing.get_args(Term), with aliases explicit.

    NOTE: WireIdentity and TagPerm are USED by the compiler and by these
    witnesses but are NOT members of the declared Term union. They are
    covered here deliberately; the discrepancy is reported, not papered over.
    """
    import typing
    declared = set(typing.get_args(T.Term))          # CLASS OBJECTS
    covered = {getattr(T, n) for n in (set(COMPOSITES) | set(LEAVES))
               if hasattr(T, n)}
    missing = declared - covered
    assert not missing, (
        f"declared Term members not classified: "
        f"{sorted(c.__name__ for c in missing)}")
    # Classified-but-undeclared: WireIdentity and TagPerm are USED by the
    # compiler and by these witnesses yet are absent from the declared union.
    OUTSIDE_UNION = {getattr(T, n) for n in ("WireIdentity", "TagPerm")}
    extra = covered - declared - OUTSIDE_UNION
    assert not extra, (
        f"classified but not in the union: "
        f"{sorted(c.__name__ for c in extra)}")
    for c in OUTSIDE_UNION:
        assert c not in declared, (
            f"{c.__name__} is now IN the union; remove the exception")


COMPOSITE_REDEX_HOSTS = [
    ("Seq", lambda r: Seq(r, Id(q))),
    ("TenTerm", lambda r: TenTerm(r, Id(q))),
    ("Pair", lambda r: Pair(r, Id(q))),
    ("Apply", lambda r: Apply(Var("f", qq), r)),
    ("Lam", lambda r: Lam("z", q, q, r)),
    ("LetPair", lambda r: LetPair("a", "b", q, q, Id(Ten(q, q)), r)),
    ("Case", lambda r: Case(q, q, r, Id(q))),
    ("CaseExpr", lambda r: CaseExpr(Id(Plus(q, q)), "a", "b", q, q, r, Id(q))),
    ("PlusMap", lambda r: PlusMap(q, q, r, Id(q))),
    ("PhasedPlusMap", lambda r: PhasedPlusMap(0.0, q, q, r, Id(q))),
    ("Sum", lambda r: Sum(0.0, 0.0, r, Id(q))),
    ("NPlusMap", lambda r: NPlusMap((q, q), (r, Id(q)))),
    ("DatatypeControl", lambda r: DatatypeControl(
        "D2", 2, Plus(I, I), q, (r, Id(q)))),
    ("Ctrl", lambda r: Ctrl(r)),
    ("Feedback", lambda r: Feedback(1, r)),
    ("ExpInvolution", lambda r: ExpInvolution(0.0, r, q)),
]


@pytest.mark.parametrize("name,host", COMPOSITE_REDEX_HOSTS,
                         ids=[n for n, _ in COMPOSITE_REDEX_HOSTS])
@pytest.mark.parametrize("kind", ["beta", "letpair"])
def test_redex_beneath_every_composite_is_reached_and_contracted(name, host,
                                                                 kind):
    """A redex under every composite must be FOUND and CONTRACTED."""
    if kind == "beta":
        redex = Apply(Lam("p", q, q, Var("p", q)), Id(q))
    else:
        redex = LetPair("m", "n", q, q, Pair(Id(q), Id(q)), Var("m", q))
    if kind == "beta":
        contracted = Id(q)                     # (\p. p) Id  ->  Id
    else:
        contracted = Id(q)                     # let (m,n) = (Id,Id) in m -> Id
    term = host(redex)
    assert first_redex(term) is not None, f"{name}/{kind}: redex not reached"
    out = nf(term)
    assert is_nf_beta_tensor(out), f"{name}/{kind}: redex not contracted"
    # "No residual redex" alone is insufficient: DELETING the redex would
    # also pass. Compare against the host rebuilt around the contractum.
    expected = nf(host(contracted))
    assert structurally_equal(out, expected), (
        f"{name}/{kind}: contraction did not rebuild the host\n"
        f"  got      {out}\n  expected {expected}")


INITIAL_CLASSIFICATION = [
    ("C", False), ("D", False), ("G", False), ("E", True), ("F", True),
]


@pytest.mark.parametrize("letter,expected_nf", INITIAL_CLASSIFICATION,
                         ids=[c[0] for c in INITIAL_CLASSIFICATION])
def test_initial_nf_classification_is_executable(letter, expected_nf):
    """The NF-0 classification as an executable assertion, not prose.

      C, D, G: NOT NF_beta_tensor initially
      E, F:    NF_beta_tensor ONLY (not canonical full normal derivations)
    """
    t = _witness(letter)
    assert is_nf_beta_tensor(t) is expected_nf, (
        f"{letter}: expected NF_beta_tensor={expected_nf}, "
        f"first redex {first_redex(t)}")


def _strip_units(ty):
    """Tensor-unit canonicalization: I (x) A = A (x) I = A.

    The spec allows interface preservation modulo EXPLICIT tensor-unit and
    associativity canonicalization -- contracting LetPair(.., Pair(..)) can
    legitimately drop a Unit-typed component -- but nothing weaker, and never
    mere width equality.
    """
    if isinstance(ty, Ten):
        l, r = _strip_units(ty.left), _strip_units(ty.right)
        if isinstance(l, Unit):
            return r
        if isinstance(r, Unit):
            return l
        return Ten(l, r)
    if isinstance(ty, Plus):
        return Plus(_strip_units(ty.left), _strip_units(ty.right))
    if isinstance(ty, Arrow):
        return Arrow(_strip_units(ty.dom), _strip_units(ty.cod))
    return ty


def test_nf_preserves_interface_modulo_unit_and_free_variables():
    for letter in ("C", "D", "E", "F", "G"):
        t = _witness(letter)
        n = nf(t)
        bd, bc = type_of(t)
        ad, ac = type_of(n)
        assert (_strip_units(ad), _strip_units(ac)) == \
               (_strip_units(bd), _strip_units(bc)), (
            f"{letter}: interface changed beyond unit canonicalization: "
            f"{(bd, bc)} -> {(ad, ac)}")
        assert _fv(n) == _fv(t), f"{letter}: free variables changed"


def test_already_normal_first_order_control_is_byte_identical():
    """An already-normal first-order term: nf must leave both the term and
    the compiled output untouched."""
    from compile.to_pytket import compile as ccompile
    from lang.terms import DistL
    ctrl = Seq(TenTerm(Id(Plus(q, Ten(q, q))), Hg(0, q)),
               DistL(q, Ten(q, q), q))
    assert is_nf_beta_tensor(ctrl)
    n = nf(ctrl)
    a = ccompile(ctrl, materialize=True)
    b = ccompile(n, materialize=True)
    assert str(a.circuit) == str(b.circuit), "compiled output changed"
    assert a.input_frame.codes == b.input_frame.codes
    assert a.output_frame.codes == b.output_frame.codes
