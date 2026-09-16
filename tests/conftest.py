"""Pytest configuration and shared test fixtures."""

import os

import pytest


@pytest.fixture(autouse=True, scope="session")
def ensure_headless_testing():
    """Ensure headless Chrome mode is active during all test execution."""
    os.environ["CS1302_HEADLESS"] = "true"
    os.environ.pop("CS1302_DISABLE_HEADLESS", None)


@pytest.fixture(scope="session")
def rendering_session(ensure_headless_testing):
    """Opt in to browser reuse; each pytest worker owns and closes its own pool.

    Pass this session only to rendering APIs. Tests using raw WebDriver or
    changing browser configuration must continue to own a fresh browser.
    """
    from cs1302_code_visualizer import RenderingSession

    with RenderingSession(max_browsers=1) as session:
        yield session
