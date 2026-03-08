#!/usr/bin/env python3
"""Shared utilities for QPL demos.

This module provides common functionality for demo scripts:
- Live compilation with confirmation
- ASCII circuit diagram rendering
- Argument parsing for --circuits flag

Usage:
    from demo_utils import DemoRunner

    runner = DemoRunner("My Demo Name")
    result = runner.compile(term, "term_name")
    runner.show_circuit(result, "term_name")
"""

import argparse
import sys
from pathlib import Path

# Add src to path
src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))

from compile.to_pytket import compile as qpl_compile


class DemoRunner:
    """Manages demo execution with live compilation and circuit display."""

    def __init__(self, demo_name: str, description: str = None):
        """Initialize demo runner.

        Args:
            demo_name: Name of the demo for display
            description: Optional description for help text
        """
        self.demo_name = demo_name
        self.show_circuits = False
        self._parse_args(description)

    def _parse_args(self, description: str):
        """Parse command line arguments."""
        parser = argparse.ArgumentParser(
            description=description or f"{self.demo_name} - QPL Demo"
        )
        parser.add_argument(
            "--circuits", action="store_true",
            help="Show ASCII circuit diagrams"
        )
        args = parser.parse_args()
        self.show_circuits = args.circuits

    def print_header(self):
        """Print demo header with live execution notice."""
        print("=" * 60)
        print(f"  LIVE EXECUTION: {self.demo_name}")
        print("  All compilations are real - no fabricated output")
        print("=" * 60)
        if self.show_circuits:
            print("\n[--circuits flag set: will show circuit diagrams]")

    def print_footer(self):
        """Print demo footer with tip about --circuits."""
        if not self.show_circuits:
            print("\nTip: Run with --circuits to see ASCII circuit diagrams")

    def compile(self, term, name: str, materialize: bool = True):
        """Compile a term with live confirmation.

        Args:
            term: The QPL term to compile
            name: Name for display
            materialize: Whether to materialize SWAPs

        Returns:
            Compiled result
        """
        print(f"  [COMPILING {name}...]", end=" ", flush=True)
        result = qpl_compile(term, materialize=materialize)
        print(f"OK - {result.circuit.n_gates} gates on {result.circuit.n_qubits} qubits")
        return result

    def show_circuit(self, result, name: str):
        """Show ASCII circuit diagram if --circuits flag is set.

        Args:
            result: Compiled result with circuit
            name: Name for display
        """
        if not self.show_circuits:
            return

        print(f"\n{'─' * 60}")
        print(f"Circuit Diagram: {name}")
        print(f"{'─' * 60}")

        cmds = list(result.circuit.get_commands())
        n_qubits = result.circuit.n_qubits

        # Build simple ASCII diagram
        lines = [f"q[{i}]: ───" for i in range(n_qubits)]

        for cmd in cmds:
            gate_name = cmd.op.type.name
            qubits = [q.index[0] for q in cmd.qubits]

            # Pad all lines to same length
            max_len = max(len(line) for line in lines)
            lines = [line.ljust(max_len, '─') for line in lines]

            if len(qubits) == 1:
                # Single qubit gate
                q = qubits[0]
                lines[q] += f"[{gate_name}]───"
            elif len(qubits) == 2:
                # Two qubit gate (control-target)
                ctrl, tgt = qubits[0], qubits[1]
                min_q, max_q = min(ctrl, tgt), max(ctrl, tgt)
                # Determine gate label for target
                tgt_label = gate_name[1:] if gate_name.startswith('C') else gate_name
                if tgt_label == "X":
                    tgt_label = "X"  # Keep X for CNOT
                for q in range(n_qubits):
                    if q == ctrl:
                        lines[q] += "──●──"
                    elif q == tgt:
                        lines[q] += f"[{tgt_label}]"
                    elif min_q < q < max_q:
                        lines[q] += "──│──"
                    else:
                        lines[q] += "─────"
            elif len(qubits) == 3:
                # Three qubit gate (CCX etc)
                ctrl1, ctrl2, tgt = qubits[0], qubits[1], qubits[2]
                min_q, max_q = min(qubits), max(qubits)
                for q in range(n_qubits):
                    if q in [ctrl1, ctrl2]:
                        lines[q] += "──●──"
                    elif q == tgt:
                        lines[q] += "──X──"
                    elif min_q < q < max_q:
                        lines[q] += "──│──"
                    else:
                        lines[q] += "─────"
            else:
                # Multi-qubit or box-type gate
                min_q, max_q = min(qubits), max(qubits)
                label = f"[{gate_name}]"
                for q in range(n_qubits):
                    if q == min_q:
                        lines[q] += label
                    elif q in qubits:
                        lines[q] += "──■──"
                    elif min_q < q < max_q:
                        lines[q] += "──│──"
                    else:
                        lines[q] += "─" * len(label)

        # Pad to equal length and print
        max_len = max(len(line) for line in lines)
        for line in lines:
            print(line.ljust(max_len, '─'))
        print()

    def print_circuit_details(self, result, title: str):
        """Print circuit details (gates, permutation).

        Args:
            result: Compiled result
            title: Section title
        """
        print(f"\n{title}")
        print("=" * len(title))
        print(f"Circuit: {result.circuit.n_gates} gates on {result.circuit.n_qubits} qubits")
        print(f"Permutation: {result.perm.new_to_old}")
        print("Gates:")
        for cmd in result.circuit.get_commands():
            qubits = [q.index[0] for q in cmd.qubits]
            try:
                params = list(cmd.op.params) if cmd.op.params else []
            except RuntimeError:
                params = []
            if params:
                print(f"  {cmd.op.type.name}({[round(p, 4) for p in params]}) on {qubits}")
            else:
                print(f"  {cmd.op.type.name} on {qubits}")
