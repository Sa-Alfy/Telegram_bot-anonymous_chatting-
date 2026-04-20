"""
Tests for Telegram-specific entry points and callback logic.
Verifies button lockout and platform-specific routing.
"""
import pytest
import time
from unittest.mock import AsyncMock, patch, MagicMock
from state.match_state import match_state
import app_state

@pytest.mark.asyncio
async def test_callback_lockout_enforcement():
    """Verify that Telegram button lockout (1.5s) is correctly enforced."""
    from handlers.callbacks import on_callback
    
    # Mock app_state to allow legacy routing
    app_state.tg_adapter = MagicMock()
    app_state.tg_adapter.translate_event = AsyncMock(return_value=None)
    user_id = 999
    query = AsyncMock()
    query.from_user.id = user_id
    query.data = "search"
    query.answer = AsyncMock()

    # 1. First click succeeds (records time)
    with patch("handlers.callbacks.MatchingHandler.handle_search", new_callable=AsyncMock) as mock_handle:
        await on_callback(None, query)
        assert mock_handle.called
        assert user_id in match_state.last_button_time

    # 2. Second rapid click (0.1s later) fails with "Please wait"
    with patch("handlers.callbacks.MatchingHandler.handle_search", new_callable=AsyncMock) as mock_handle:
        match_state.last_button_time[user_id] = time.time()
        await on_callback(None, query)
        assert not mock_handle.called
        query.answer.assert_called_with("Please wait...", show_alert=False)

    # 3. Click after cooldown succeeds
    with patch("handlers.callbacks.MatchingHandler.handle_search", new_callable=AsyncMock) as mock_handle:
        match_state.last_button_time[user_id] = time.time() - 2.0
        await on_callback(None, query)
        assert mock_handle.called
