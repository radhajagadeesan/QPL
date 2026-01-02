"""Test helpers for surface language end-to-end testing.

Provides utilities for:
- Compiling surface programs through the Phase 0-4C pipeline
- Golden file comparison
- Permutation serialization
- Circuit canonicalization
"""

import sys
import os
import json
import subprocess
import tempfile
from pathlib import Path
from typing import Optional, Tuple, Any, Dict

# Add parent paths for imports
SURFACE_DIR = Path(__file__).parent.parent
PROJECT_DIR = SURFACE_DIR.parent
SRC_DIR = PROJECT_DIR / 'src'
sys.path.insert(0, str(SRC_DIR))
sys.path.insert(0, str(PROJECT_DIR))

from lang.types import Q, Ten, Plus
from lang.terms import (
    Id, Seq, TenTerm, TwistTen, TwistPlus,
    AssocTenL, AssocTenR, AssocPlusL, AssocPlusR,
    DistL, DistR, H, S, CX, X, Y, Z, T, Rz
)
from compile.to_pytket import compile as phase0_compile

# Aliases for compatibility
TwistTensor = TwistTen
AssocTensorL = AssocTenL
AssocTensorR = AssocTenR
GateH = H
GateS = S
GateCX = CX
GateX = X
GateY = Y
GateZ = Z
GateT = T
GateRz = Rz


def compile_term(term, materialize: bool = False) -> Tuple[Any, Any]:
    """Compile a core IR term through Phase 0.

    Returns:
        (circuit, perm) tuple
    """
    result = phase0_compile(term, materialize=materialize)
    return result.circuit, result.perm


def compile_surface_text(src: str, certified: bool = True, materialize: bool = False) -> Tuple[Any, Any]:
    """Compile surface language text through the full pipeline.

    This is a placeholder that will be connected to the OCaml parser.
    For now, it expects Python term definitions.

    Returns:
        (circuit, perm) tuple
    """
    # Execute the source as Python and extract 'main'
    local_ns: Dict[str, Any] = {
        'Q': Q, 'Ten': Ten, 'Plus': Plus,
        'Id': Id, 'Seq': Seq, 'TenTerm': TenTerm,
        'TwistTensor': TwistTensor, 'TwistPlus': TwistPlus,
        'AssocTensorL': AssocTensorL, 'AssocTensorR': AssocTensorR,
        'AssocPlusL': AssocPlusL, 'AssocPlusR': AssocPlusR,
        'DistL': DistL, 'DistR': DistR,
        'GateH': GateH, 'GateS': GateS, 'GateCX': GateCX,
        'GateX': GateX, 'GateY': GateY, 'GateZ': GateZ,
        'GateT': GateT, 'GateRz': GateRz,
    }
    exec(src, local_ns)
    term = local_ns.get('main')
    if term is None:
        raise ValueError("Source must define 'main' term")

    return compile_term(term, materialize=materialize)


def compile_surface_file(path: str, **kwargs) -> Tuple[Any, Any]:
    """Compile a surface language file."""
    with open(path, 'r') as f:
        src = f.read()
    return compile_surface_text(src, **kwargs)


def perm_serialize(perm) -> str:
    """Serialize a WirePerm to stable JSON string."""
    return json.dumps({
        'n': perm.n,
        'new_to_old': perm.new_to_old,
    }, sort_keys=True)


def circuit_to_commands(circuit) -> str:
    """Convert circuit to canonical command stream text."""
    if circuit is None:
        return ""

    # pytket Circuit
    if hasattr(circuit, 'get_commands'):
        cmds = circuit.get_commands()
        if not cmds:
            return ""
        return '\n'.join(str(cmd) for cmd in cmds)

    # List-like
    if hasattr(circuit, '__iter__'):
        lines = []
        for cmd in circuit:
            if hasattr(cmd, 'to_string'):
                lines.append(cmd.to_string())
            else:
                lines.append(str(cmd))
        return '\n'.join(lines)

    return str(circuit)


def is_empty_circuit(circuit) -> bool:
    """Check if circuit contains no gates."""
    if circuit is None:
        return True
    # pytket Circuit: check n_gates
    if hasattr(circuit, 'n_gates'):
        return circuit.n_gates == 0
    # List-like
    if hasattr(circuit, '__len__'):
        return len(circuit) == 0
    return False


def is_involutive(perm) -> bool:
    """Check if permutation is involutive (p o p = id)."""
    n = perm.n
    new_to_old = perm.new_to_old
    # For involutive: perm(perm(i)) = i for all i
    # With new_to_old representation: new_to_old[new_to_old[i]] == i
    for i in range(n):
        if new_to_old[new_to_old[i]] != i:
            return False
    return True


def load_golden(path: str) -> str:
    """Load golden file content."""
    with open(path, 'r') as f:
        return f.read()


def save_golden(path: str, content: str):
    """Save golden file content."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w') as f:
        f.write(content)


def compare_golden(actual: str, golden_path: str, update: bool = False) -> bool:
    """Compare actual output against golden file.

    Args:
        actual: The actual output string
        golden_path: Path to golden file
        update: If True, update golden file on mismatch

    Returns:
        True if match (or updated), False otherwise
    """
    if not os.path.exists(golden_path):
        if update:
            save_golden(golden_path, actual)
            return True
        return False

    expected = load_golden(golden_path)
    if actual == expected:
        return True

    if update:
        save_golden(golden_path, actual)
        return True

    return False


# OCaml integration helpers

def ocaml_to_python(ml_source: str) -> str:
    """Run OCaml surface compiler to generate Python code.

    This calls the OCaml bridge to elaborate and emit Python.
    """
    # Use the bridge.py interface
    bridge_path = SURFACE_DIR / 'bridge.py'

    with tempfile.NamedTemporaryFile(mode='w', suffix='.ml', delete=False) as f:
        f.write(ml_source)
        ml_path = f.name

    try:
        result = subprocess.run(
            [sys.executable, str(bridge_path), 'elaborate', ml_path],
            capture_output=True,
            text=True,
            timeout=30
        )
        if result.returncode != 0:
            raise RuntimeError(f"OCaml elaboration failed: {result.stderr}")
        return result.stdout
    finally:
        os.unlink(ml_path)


def run_generated_python(py_source: str) -> Tuple[Any, Any, str]:
    """Execute generated Python and return (circuit, perm, logs)."""
    local_ns: Dict[str, Any] = {
        'Q': Q, 'Ten': Ten, 'Plus': Plus,
        'Id': Id, 'Seq': Seq, 'TenTerm': TenTerm,
        'TwistTensor': TwistTensor, 'TwistPlus': TwistPlus,
        'AssocTensorL': AssocTensorL, 'AssocTensorR': AssocTensorR,
        'AssocPlusL': AssocPlusL, 'AssocPlusR': AssocPlusR,
        'DistL': DistL, 'DistR': DistR,
        'GateH': GateH, 'GateS': GateS, 'GateCX': GateCX,
        'GateX': GateX, 'GateY': GateY, 'GateZ': GateZ,
        'GateT': GateT, 'GateRz': GateRz,
        'phase0_compile': phase0_compile,
    }

    import io
    from contextlib import redirect_stdout

    log_buffer = io.StringIO()
    with redirect_stdout(log_buffer):
        exec(py_source, local_ns)

    circuit = local_ns.get('circuit')
    perm = local_ns.get('perm')
    logs = log_buffer.getvalue()

    return circuit, perm, logs
