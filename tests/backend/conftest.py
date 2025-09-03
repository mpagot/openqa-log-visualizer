import pytest
from unittest.mock import MagicMock


@pytest.fixture
def app_logger():
    """Fixture for a mock logger."""
    return MagicMock()
