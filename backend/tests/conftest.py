import os
import tempfile
from pathlib import Path
from typing import Iterator

import pytest

# The environment must be fixed BEFORE any `app` module is imported, because the settings singletons are
# created at import time. Forcing masked keys guarantees a developer's real .env can never reach a live API.
_TEST_DIR = Path(tempfile.mkdtemp(prefix="ticket-engine-tests-"))

os.environ.update(
    {
        "ENVIRONMENT": "test",
        "DEBUG": "false",
        "OPENROUTER_API_KEY": "sk-or-v1-MASKED_KEY_HERE",
        "GEMINI_API_KEY": "AIzaSy_MASKED_KEY_HERE",
        "DATABASE_URL": f"sqlite:///{(_TEST_DIR / 'tickets.db').as_posix()}",
        "CHROMA_PERSIST_DIR": str(_TEST_DIR / "chroma"),
        "CHROMA_COLLECTION": "past_tickets_kb_test",
        "ENFORCE_RBAC_ON_PROCESS_TICKET": "false",
        "JEV_LATENCY_THRESHOLD_MS": "500",
        "CORS_ORIGINS": '["http://localhost:5173","http://127.0.0.1:5173"]',
    }
)


@pytest.fixture(scope="session", autouse=True)
def fast_gemini_simulator() -> Iterator[None]:
    """Removes the simulator's 1000-2000 ms wait so the suite stays fast; timing contracts are still asserted."""
    from app.services import gemini_service

    patcher = pytest.MonkeyPatch()
    patcher.setattr(gemini_service, "_simulated_target_ms", lambda raw_text, team: 1)
    yield
    patcher.undo()


@pytest.fixture(scope="session")
def client() -> Iterator["TestClient"]:  # noqa: F821
    """Application client used as a context manager so the lifespan creates the schema and seeds the data."""
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as test_client:
        yield test_client
