"""
Shared fixtures and mock setup for all tests.
Patches external dependencies (DB, Redis, Telegram, Messenger) so tests
run entirely in-memory without any network calls.
"""
import os
import sys
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

# Ensure project root is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Set required env vars BEFORE importing any project modules
os.environ.setdefault("API_ID", "12345")
os.environ.setdefault("API_HASH", "abc123")
os.environ.setdefault("BOT_TOKEN", "123:ABC")
os.environ.setdefault("ADMIN_ID", "999")
os.environ.setdefault("PAGE_ACCESS_TOKEN", "test_token")
os.environ.setdefault("VERIFY_TOKEN", "test_verify")
os.environ.setdefault("DATABASE_URL", "postgresql://fake:fake@localhost/fake")


@pytest.fixture(autouse=True)
def global_mocks():
    """Globally mock the database to prevent connectivity errors during unit tests."""
    with patch("database.connection.Database.fetchone", new_callable=AsyncMock) as mock_fetchone, \
         patch("database.connection.Database.fetchall", new_callable=AsyncMock) as mock_fetchall, \
         patch("database.connection.Database.fetchval", new_callable=AsyncMock) as mock_fetchval, \
         patch("database.connection.Database.execute", new_callable=AsyncMock) as mock_execute:
        
        # Default returns to avoid further errors
        mock_fetchone.return_value = None
        mock_fetchall.return_value = []
        mock_fetchval.return_value = None
        mock_execute.return_value = MagicMock(rowcount=0)
        
        yield (mock_fetchone, mock_fetchall, mock_execute)

@pytest.fixture(autouse=True)
def reset_singletons():
    """Resets all singleton states before each test by clearing existing instances in-place."""
    from services.distributed_state import distributed_state
    from state.match_state import match_state
    from utils.rate_limiter import rate_limiter
    
    # 1. Clear DistributedState (In-place)
    distributed_state._fallback_store.clear()
    distributed_state.redis = None
    distributed_state._instance = distributed_state # Ensure singleton property remains
    
    # 2. Clear MatchState (In-place)
    match_state.rematch_requests.clear()
    match_state.user_ui_messages.clear() # Fix for UI tests
    if hasattr(match_state, "ui_history"):
        match_state.ui_history.clear()
    match_state.last_button_time.clear()
    match_state.last_message_time.clear()
    match_state.spam_count.clear()
    match_state.mute_until.clear()
    
    # 3. Clear RateLimiter (In-place)
    rate_limiter._last_message.clear()
    rate_limiter._last_matchmaking.clear()
    rate_limiter._last_report.clear()
    
    # 4. Clear BehaviorEngine (In-place)
    from core.behavior_engine import behavior_engine
    behavior_engine.reset()
    
    yield

@pytest.fixture
def event_loop():
    """Create a fresh event loop for each test."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()

def _run_async_mock(coro):
    """Mock for _run_async that runs the coroutine in the current loop for testing."""
    return asyncio.run(coro)
