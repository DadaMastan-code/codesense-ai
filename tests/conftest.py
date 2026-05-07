"""Shared pytest configuration and fixtures."""
from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def clear_rate_store():
    """Reset the in-memory rate limit store between tests."""
    import backend.main as main_module
    main_module._rate_store.clear()
    yield
    main_module._rate_store.clear()
