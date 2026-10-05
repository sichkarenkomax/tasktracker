from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture
def client() -> TestClient:
    """Test client with the real lifespan, so module bootstrap is exercised."""
    with TestClient(create_app()) as test_client:
        yield test_client
