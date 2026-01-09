import os
import tempfile

import pytest

# Set test environment before any imports
_test_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
os.environ["DB_PATH"] = _test_db.name
os.environ["HOST_CODE"] = "testcode"
os.environ["SECRET_KEY"] = "test-secret"
_test_db.close()


@pytest.fixture(autouse=True)
def reset_games():
    """Reset GAMES dict before each test."""
    from app import GAMES
    GAMES.clear()
    yield
    GAMES.clear()
