# tests/conftest.py
import os
import random
import pytest


def pytest_configure(config):
    config.addinivalue_line(
        "markers", "phase1: marks tests as Phase 1 contract tests"
    )
    config.addinivalue_line(
        "markers", "phase2: marks tests as Phase 2 TenTerm tests"
    )
    config.addinivalue_line(
        "markers", "phase3: marks tests as Phase 3 GOI feedback tests"
    )
    config.addinivalue_line(
        "markers", "integration: marks tests as integration tests"
    )
    config.addinivalue_line(
        "markers", "phase4a: marks tests as Phase 4A Extraction++ tests"
    )
    config.addinivalue_line(
        "markers", "regression: marks tests as regression tests for Phase 0-3 lockdown"
    )
    config.addinivalue_line(
        "markers", "phase4b: marks tests as Phase 4B ZX-based extraction tests"
    )


DEFAULT_SEED = int(os.environ.get("QPL_SEED", "12345"))

@pytest.fixture(scope="session")
def seed():
    return DEFAULT_SEED

@pytest.fixture()
def rng(seed):
    return random.Random(seed)
