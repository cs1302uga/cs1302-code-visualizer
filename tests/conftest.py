"""Pytest configuration and shared test fixtures."""

import os
import pytest


@pytest.fixture(autouse=True, scope="session")
def ensure_headless_testing():
    """Ensure headless Chrome mode is active during all test execution."""
    os.environ["CS1302_HEADLESS"] = "true"
    os.environ.pop("CS1302_DISABLE_HEADLESS", None)
