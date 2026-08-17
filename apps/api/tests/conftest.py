import os

os.environ.setdefault("ENVIRONMENT", "test")

# Force-cleared, not setdefault -- config.py's Settings reads apps/api/.env
# directly (env_file=".env"), which happens regardless of ENVIRONMENT, so a
# developer's own real OPENAI_API_KEY/ANTHROPIC_API_KEY (needed for real
# local exploration of chat/voice) would otherwise leak into the test
# suite too. Found live: test_a_real_synthesis_failure_is_reported_as_an_
# error started making a genuine, unmocked call to api.openai.com and
# passing for the wrong reason the moment a real key existed in .env --
# the test suite must never depend on what a developer happens to have
# configured locally, and must never spend a real developer's real API
# budget just by running `pytest`.
os.environ["OPENAI_API_KEY"] = ""
os.environ["ANTHROPIC_API_KEY"] = ""

import pytest  # noqa: E402


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"
