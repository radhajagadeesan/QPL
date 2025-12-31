# tests/helpers.py
"""Tiny stable helpers for tests.

These helpers intentionally centralize import shims and pytket introspection so
tests stay stable across refactors.
"""

from __future__ import annotations

import importlib
from typing import Any, Callable, Iterable, List, Optional, Tuple


def import_attr(module: str, attr: str) -> Any:
    mod = importlib.import_module(module)
    return getattr(mod, attr)


def try_import_attr(candidates: List[Tuple[str, str]]) -> Any:
    """Try (module, attr) pairs; return first that imports, else raise."""
    last_err = None
    for module, attr in candidates:
        try:
            return import_attr(module, attr)
        except Exception as e:
            last_err = e
    raise ImportError(f"Could not import any of: {candidates}. Last error: {last_err}")


def get_compile_to_pytket() -> Callable[..., Any]:
    """Return the project's compile-to-pytket entrypoint.

    Returns a function that compiles a term and returns the Circuit directly.
    """
    raw_compile = try_import_attr([
        ("compile.to_pytket", "compile_to_pytket"),
        ("compile.to_pytket", "compile"),
        ("compile.to_pytket", "to_pytket"),
        ("compile.to_pytket", "compile_term"),
    ])

    def compile_to_pytket(term, *, materialize: bool = False):
        result = raw_compile(term, materialize=materialize)
        # If result has a .circuit attribute (Compiled object), return that
        if hasattr(result, "circuit"):
            return result.circuit
        return result

    return compile_to_pytket


def get_wireperm_cls():
    return try_import_attr([
        ("core.perm", "WirePerm"),
        ("core.perm", "Perm"),
        ("core.perm", "Permutation"),
    ])


def perm_apply(p: Any, i: int) -> int:
    """Apply a WirePerm to an index i using common conventions."""
    if hasattr(p, "apply_new_to_old") and callable(getattr(p, "apply_new_to_old")):
        return int(p.apply_new_to_old(i))
    if hasattr(p, "apply") and callable(getattr(p, "apply")):
        return int(p.apply(i))
    if callable(p):
        return int(p(i))
    if hasattr(p, "__getitem__"):
        return int(p[i])
    raise AttributeError("WirePerm has no apply_new_to_old/apply/__call__/__getitem__ for index application")


def perm_to_list(p: Any) -> List[int]:
    """Stable list representation for debugging."""
    if hasattr(p, "new_to_old"):
        return list(p.new_to_old)
    if hasattr(p, "to_list") and callable(getattr(p, "to_list")):
        return list(p.to_list())
    if hasattr(p, "mapping"):
        return list(p.mapping)
    if hasattr(p, "perm"):
        return list(p.perm)
    if hasattr(p, "__iter__"):
        try:
            return list(p)
        except TypeError:
            pass
    raise AttributeError("WirePerm has no obvious list representation (new_to_old/to_list/mapping/perm/iter)")


def circuit_fingerprint(circ: Any) -> List[Tuple[str, Tuple[int, ...]]]:
    """Return a stable op list fingerprint: [(opname, (qubits...)), ...]."""
    # pytket Circuit has get_commands()
    if hasattr(circ, "get_commands") and callable(getattr(circ, "get_commands")):
        out = []
        for cmd in circ.get_commands():
            op = cmd.op.get_name()
            qs = tuple(q.index[0] for q in cmd.qubits)
            out.append((op, qs))
        return out
    # fallback: some wrappers expose commands attribute
    cmds = getattr(circ, "commands", None)
    if cmds is not None:
        out = []
        for cmd in cmds:
            op = cmd.op.get_name() if hasattr(cmd, "op") else str(cmd)
            qs = tuple(getattr(q, "index", (q,))[0] for q in getattr(cmd, "qubits", ()))
            out.append((op, qs))
        return out
    raise AttributeError("Unrecognized circuit object: cannot extract commands")


def has_swap(circ: Any) -> bool:
    for op, _ in circuit_fingerprint(circ):
        if op.upper() == "SWAP":
            return True
    return False


def non_swap_fingerprint(circ: Any) -> List[Tuple[str, Tuple[int, ...]]]:
    return [(op, qs) for (op, qs) in circuit_fingerprint(circ) if op.upper() != "SWAP"]


def assert_raises_msg(exc_type, msg_substr: str, fn, *args, **kwargs):
    try:
        fn(*args, **kwargs)
    except exc_type as e:
        s = str(e)
        assert msg_substr in s, f"Expected '{msg_substr}' in error; got: {s}"
        return
    raise AssertionError(f"Expected {exc_type.__name__} but no exception was raised")
