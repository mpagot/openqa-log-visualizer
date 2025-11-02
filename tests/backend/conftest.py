import pytest
import logging


@pytest.fixture
def app_logger():
    """Fixture for a mock logger."""
    return logging.getLogger("test logger")
