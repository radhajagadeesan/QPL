# tests/test_encode_decode.py
"""Tests for Q ↔ I+I encoding isomorphism."""

import numpy as np
import pytest

from lang.terms import EncodeQubit, DecodeQubit, Seq
from lang.types import Q, Plus, Unit, width
from typing_.check import type_of
from compile.to_pytket import compile


class TestTypeRules:
    """Test type rules for encode/decode."""

    def test_encode_type(self):
        """encode : Q → I + I"""
        enc = EncodeQubit()
        dom, cod = type_of(enc)
        assert dom == Q()
        assert cod == Plus(Unit(), Unit())
        assert width(dom) == 1
        assert width(cod) == 1

    def test_decode_type(self):
        """decode : I + I → Q"""
        dec = DecodeQubit()
        dom, cod = type_of(dec)
        assert dom == Plus(Unit(), Unit())
        assert cod == Q()
        assert width(dom) == 1
        assert width(cod) == 1

    def test_roundtrip_encode_decode_type(self):
        """encode ; decode : Q → Q"""
        roundtrip = Seq(EncodeQubit(), DecodeQubit())
        dom, cod = type_of(roundtrip)
        assert dom == Q()
        assert cod == Q()

    def test_roundtrip_decode_encode_type(self):
        """decode ; encode : I+I → I+I"""
        roundtrip = Seq(DecodeQubit(), EncodeQubit())
        dom, cod = type_of(roundtrip)
        assert dom == Plus(Unit(), Unit())
        assert cod == Plus(Unit(), Unit())


class TestCompilation:
    """Test compilation of encode/decode."""

    def test_encode_circuit(self):
        """Encode compiles to CX[0,1]; X[0]"""
        enc = EncodeQubit()
        result = compile(enc)
        commands = [str(cmd) for cmd in result.circuit.get_commands()]
        assert commands == ['CX q[0], q[1];', 'X q[0];']

    def test_decode_circuit(self):
        """Decode compiles to X[0]; CX[0,1]"""
        dec = DecodeQubit()
        result = compile(dec)
        commands = [str(cmd) for cmd in result.circuit.get_commands()]
        assert commands == ['X q[0];', 'CX q[0], q[1];']

    def test_roundtrip_is_identity(self):
        """encode ; decode = identity on Q ⊗ |0⟩ subspace"""
        roundtrip = Seq(EncodeQubit(), DecodeQubit())
        result = compile(roundtrip)
        U = result.circuit.get_unitary()
        # Should be 4x4 identity
        assert np.allclose(U, np.eye(4))


class TestEncodeBehavior:
    """Test encode maps Q states to one-hot I+I states."""

    def test_encode_zero(self):
        """|0⟩ ⊗ |0⟩ → |10⟩ (logical |0⟩_L)"""
        enc = EncodeQubit()
        U = compile(enc).circuit.get_unitary()
        v_in = np.array([1, 0, 0, 0])  # |00⟩
        v_out = U @ v_in
        expected = np.array([0, 0, 1, 0])  # |10⟩
        assert np.allclose(v_out, expected)

    def test_encode_one(self):
        """|1⟩ ⊗ |0⟩ → |01⟩ (logical |1⟩_L)"""
        enc = EncodeQubit()
        U = compile(enc).circuit.get_unitary()
        v_in = np.array([0, 0, 1, 0])  # |10⟩
        v_out = U @ v_in
        expected = np.array([0, 1, 0, 0])  # |01⟩
        assert np.allclose(v_out, expected)

    def test_encode_superposition(self):
        """(α|0⟩ + β|1⟩) ⊗ |0⟩ → α|10⟩ + β|01⟩"""
        enc = EncodeQubit()
        U = compile(enc).circuit.get_unitary()
        # Input: (|0⟩ + |1⟩)/√2 ⊗ |0⟩ = (|00⟩ + |10⟩)/√2
        v_in = np.array([1, 0, 1, 0]) / np.sqrt(2)
        v_out = U @ v_in
        # Expected: (|10⟩ + |01⟩)/√2
        expected = np.array([0, 1, 1, 0]) / np.sqrt(2)
        assert np.allclose(v_out, expected)


class TestDecodeBehavior:
    """Test decode maps one-hot I+I states back to Q."""

    def test_decode_logical_zero(self):
        """|10⟩ (logical |0⟩_L) → |0⟩ ⊗ |0⟩"""
        dec = DecodeQubit()
        U = compile(dec).circuit.get_unitary()
        v_in = np.array([0, 0, 1, 0])  # |10⟩
        v_out = U @ v_in
        expected = np.array([1, 0, 0, 0])  # |00⟩
        assert np.allclose(v_out, expected)

    def test_decode_logical_one(self):
        """|01⟩ (logical |1⟩_L) → |1⟩ ⊗ |0⟩"""
        dec = DecodeQubit()
        U = compile(dec).circuit.get_unitary()
        v_in = np.array([0, 1, 0, 0])  # |01⟩
        v_out = U @ v_in
        expected = np.array([0, 0, 1, 0])  # |10⟩
        assert np.allclose(v_out, expected)

    def test_decode_superposition(self):
        """α|10⟩ + β|01⟩ → (α|0⟩ + β|1⟩) ⊗ |0⟩"""
        dec = DecodeQubit()
        U = compile(dec).circuit.get_unitary()
        # Input: (|10⟩ + |01⟩)/√2
        v_in = np.array([0, 1, 1, 0]) / np.sqrt(2)
        v_out = U @ v_in
        # Expected: (|00⟩ + |10⟩)/√2
        expected = np.array([1, 0, 1, 0]) / np.sqrt(2)
        assert np.allclose(v_out, expected)


class TestRoundtrips:
    """Test roundtrip properties."""

    def test_encode_decode_roundtrip(self):
        """encode ; decode is identity on Q ⊗ |0⟩"""
        roundtrip = Seq(EncodeQubit(), DecodeQubit())
        U = compile(roundtrip).circuit.get_unitary()
        assert np.allclose(U, np.eye(4))

    def test_decode_encode_roundtrip_on_valid_states(self):
        """decode ; encode is identity on valid I+I states"""
        roundtrip = Seq(DecodeQubit(), EncodeQubit())
        U = compile(roundtrip).circuit.get_unitary()
        # Check |10⟩ → |10⟩
        v10 = np.array([0, 0, 1, 0])
        assert np.allclose(U @ v10, v10)
        # Check |01⟩ → |01⟩
        v01 = np.array([0, 1, 0, 0])
        assert np.allclose(U @ v01, v01)

    def test_superposition_preserved_through_roundtrip(self):
        """Superposition preserved: encode ; decode on superposed input"""
        roundtrip = Seq(EncodeQubit(), DecodeQubit())
        U = compile(roundtrip).circuit.get_unitary()
        # Input: (|00⟩ + |10⟩)/√2
        v_in = np.array([1, 0, 1, 0]) / np.sqrt(2)
        v_out = U @ v_in
        assert np.allclose(v_out, v_in)
