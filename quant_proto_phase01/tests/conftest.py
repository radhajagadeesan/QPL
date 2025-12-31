# tests/conftest.py
import os
import random
import pytest


def pytest_configure(config):
    config.addinivalue_line(
        "markers", "phase1: marks tests as Phase 1 contract tests"
    )


DEFAULT_SEED = int(os.environ.get("QPL_SEED", "12345"))

@pytest.fixture(scope="session")
def seed():
    return DEFAULT_SEED

@pytest.fixture()
def rng(seed):
    return random.Random(seed)
