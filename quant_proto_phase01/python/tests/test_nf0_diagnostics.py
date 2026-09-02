"""NF-0: canonical normal-form feasibility diagnostics.

TEST-ONLY. Nothing here modifies the compiler. It measures whether the
existing pipeline can produce the canonical normal derivations the reference
emitter is defined on.

The reference rule under test:

    the reference emitter is defined on canonical normal derivations; every
    syntactic premise reached by structural recursion is consequently normal,
    and a clause that CONSTRUCTS an auxiliary term first normalizes and
    canonically retypes it before recursive emission.
"""

import json
import os
import sys

import pytest

from lang.types import Unit, Q, Ten, Plus, Arrow
from lang.terms import (Id, Seq, Apply, Lam, Var, Pair, LetPair, TenTerm,
                        PlusMap, NPlusMap, Case, CaseExpr, H as Hg)
from compile.to_pytket import _normalize, _substitute
from typing_.check import type_of

I, q = Unit(), Q()
qq = Arrow(q, q)
FIX = os.path.join(os.path.dirname(__file__), "fixtures")


def _fixture(name):
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..",
                                    "ocaml"))
    from bridge import parse_term
    with open(os.path.join(FIX, name + ".json")) as f:
        return parse_term(json.load(f))


# ---------------------------------------------------------------------------
# D. The full-NF predicate
# ---------------------------------------------------------------------------

# The NF-0 predicate was incomplete: it fell through on unknown constructors
# (silently classifying them as normal) and its "idempotence" test compared
# only types. Both are superseded by the exhaustive, fail-loud predicate in
# test_nf1_beta_tensor.py, which is imported here so a single definition is
# audited rather than two divergent ones.

sys.path.insert(0, os.path.dirname(__file__))
from test_nf1_beta_tensor import (            # noqa: E402
    first_redex, is_nf_beta_tensor, _kind, UnknownConstructor, nf,
    structurally_equal, binder_census,
)

is_full_nf = is_nf_beta_tensor      # NF_beta_tensor only -- NOT canonical NF


# ---------------------------------------------------------------------------
# C. The normalizer audit, as executable assertions
# ---------------------------------------------------------------------------

def test_python_normalizer_does_not_beta_reduce():
    """`_normalize` eliminates LetPair(Pair(..)) only. Its Apply clause is
    `Apply(_normalize(f), _normalize(arg))` -- it recurses, never reduces."""
    red = Apply(Lam("p", q, q, Var("p", q)), Id(q))
    assert isinstance(_normalize(red), Apply), (
        "_normalize now beta-reduces; the NF-0 audit must be redone")
    assert first_redex(red) == "root"


def test_python_substitution_is_not_capture_avoiding():
    """Counterexample: substituting a replacement with a free `y` into a term
    that BINDS `y` captures it. `_substitute` respects shadowing (it skips a
    body that rebinds the name) but never renames, so capture is possible."""
    got = _substitute(Lam("y", q, q, Var("x", q)), "x", Var("y", q))
    assert isinstance(got, Lam) and got.name == "y"
    assert isinstance(got.body, Var) and got.body.name == "y", (
        "capture no longer occurs; the NF-0 audit must be redone")


def test_compiler_normalize_is_idempotent_structurally():
    """Structural idempotence of the COMPILER's _normalize.

    The earlier version compared only `type_of`, which cannot detect a
    changed term at a fixed interface. This compares structure.
    """
    for name in ("curried_select_3_applied_hst", "qswitch_eta_endoQ",
                 "ctrl_ho_closed_plus_map"):
        t = _fixture(name)
        once = _normalize(t)
        twice = _normalize(once)
        assert structurally_equal(twice, once), f"{name}: not idempotent"


def test_normalize_preserves_exact_source_type():
    """Structural source-type equality, not merely equal wire width."""
    for name in ("curried_select_3_applied_hst", "qswitch_eta_endoQ",
                 "ctrl_ho_closed_plus_map"):
        t = _fixture(name)
        assert type_of(_normalize(t)) == type_of(t), f"{name}: type changed"
