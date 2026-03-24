"""
Pytest configuration and shared fixtures.

conftest.py is a special pytest file — fixtures defined here are automatically
available to every test in this directory without needing to import them.

What is a fixture?
  A fixture is a function that sets up (and optionally tears down) something
  a test needs. pytest injects fixtures by matching the parameter name in a
  test function to the fixture's function name. For example, a test that
  takes `fresh_session_id` as a parameter automatically receives a new UUID.
"""
import sys
import os
import types
import uuid
import pytest
from unittest.mock import MagicMock

# Make the backend app importable from the tests/ directory
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Set required env vars before any app module is imported
os.environ.setdefault("GEMINI_API_KEY", "test-key")
os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("QDRANT_URL", "http://localhost:6333")

# Stub out the database layer — SQLModel/Pydantic v2 is fixed in 0.0.37,
# but we still stub it here so tests never need a live Postgres connection.
_fake_models = types.ModuleType("app.models.memory")
_fake_models.engine = None
_fake_models.ChatMessage = None
_fake_models.SessionHistory = None
_fake_models.init_db = lambda: None
sys.modules["app.models.memory"] = _fake_models

_fake_mem = types.ModuleType("app.services.memory")
_fake_mem.MemoryManager = MagicMock()
_fake_mem.MemoryManager.get_history = MagicMock(return_value=[])
_fake_mem.MemoryManager.add_message = MagicMock()
sys.modules["app.services.memory"] = _fake_mem


@pytest.fixture
def fresh_session_id() -> str:
    """Returns a new UUID string for each test — guarantees session isolation."""
    return str(uuid.uuid4())
