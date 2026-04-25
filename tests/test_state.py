"""
Tests for state/ modules: DistributedState (fallback mode), MatchState
"""
import time
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch


# ═══════════════════════════════════════════════════════
# 1. DistributedState (Memory Fallback) Tests
# ═══════════════════════════════════════════════════════
class TestDistributedStateFallback:
    """Tests DistributedState with redis=None (in-memory fallback)."""
    # reset_singletons in conftest.py handles reset

    @pytest.mark.asyncio
    async def test_set_and_get_partner(self):
        from services.distributed_state import distributed_state
        await distributed_state.set_partner(100, 200)
        assert await distributed_state.get_partner(100) == 200
        assert await distributed_state.get_partner(200) == 100

    @pytest.mark.asyncio
    async def test_get_partner_none(self):
        from services.distributed_state import distributed_state
        assert await distributed_state.get_partner(999) is None

    @pytest.mark.asyncio
    async def test_clear_partner(self):
        from services.distributed_state import distributed_state
        await distributed_state.set_partner(100, 200)
        cleared = await distributed_state.clear_partner(100)
        assert cleared == 200
        assert await distributed_state.get_partner(100) is None
        assert await distributed_state.get_partner(200) is None

    @pytest.mark.asyncio
    async def test_clear_partner_no_existing(self):
        from services.distributed_state import distributed_state
        result = await distributed_state.clear_partner(999)
        assert result is None

    @pytest.mark.asyncio
    async def test_is_in_chat(self):
        from services.distributed_state import distributed_state
        from core.engine.state_machine import UnifiedState
        await distributed_state.set_user_state("100", UnifiedState.CHAT_ACTIVE)
        await distributed_state.set_partner(100, 200)
        assert await distributed_state.is_in_chat(100) is True
        assert await distributed_state.is_in_chat(300) is False

    @pytest.mark.asyncio
    async def test_set_and_get_user_state(self):
        from services.distributed_state import distributed_state
        await distributed_state.set_user_state(100, "awaiting_bio")
        assert await distributed_state.get_user_state(100) == "awaiting_bio"

    @pytest.mark.asyncio
    async def test_clear_user_state(self):
        from services.distributed_state import distributed_state
        await distributed_state.set_user_state(100, "idle")
        await distributed_state.set_user_state(100, None)
        assert await distributed_state.get_user_state(100) is None

    @pytest.mark.asyncio
    async def test_get_user_state_none(self):
        from services.distributed_state import distributed_state
        assert await distributed_state.get_user_state(999) is None

    @pytest.mark.asyncio
    async def test_is_duplicate_message_empty(self):
        from services.distributed_state import distributed_state
        assert await distributed_state.is_duplicate_message("") is False
        assert await distributed_state.is_duplicate_message(None) is False

    @pytest.mark.asyncio
    async def test_is_duplicate_message_first_time(self):
        from services.distributed_state import distributed_state
        assert await distributed_state.is_duplicate_message("msg_001") is False

    @pytest.mark.asyncio
    async def test_is_duplicate_message_second_time(self):
        from services.distributed_state import distributed_state
        await distributed_state.is_duplicate_message("msg_002")
        assert await distributed_state.is_duplicate_message("msg_002") is True

    @pytest.mark.asyncio
    async def test_is_duplicate_message_different_ids(self):
        from services.distributed_state import distributed_state
        await distributed_state.is_duplicate_message("msg_a")
        assert await distributed_state.is_duplicate_message("msg_b") is False

    @pytest.mark.asyncio
    async def test_is_duplicate_interaction_first_time(self):
        from services.distributed_state import distributed_state
        assert await distributed_state.is_duplicate_interaction(100, "search", ttl=1) is False

    @pytest.mark.asyncio
    async def test_is_duplicate_interaction_duplicate(self):
        from services.distributed_state import distributed_state
        await distributed_state.is_duplicate_interaction(100, "find", ttl=5)
        assert await distributed_state.is_duplicate_interaction(100, "find", ttl=5) is True

    @pytest.mark.asyncio
    async def test_is_duplicate_interaction_expires(self):
        from services.distributed_state import distributed_state
        await distributed_state.is_duplicate_interaction(100, "temp", ttl=1)
        # Wait for expiry
        await asyncio.sleep(1.1)
        assert await distributed_state.is_duplicate_interaction(100, "temp", ttl=1) is False


# ═══════════════════════════════════════════════════════
# 2. MatchState Tests
# ═══════════════════════════════════════════════════════
class TestMatchState:
    @pytest.mark.asyncio
    async def test_add_to_queue(self):
        from state.match_state import match_state
        from services.distributed_state import distributed_state
        with patch.object(distributed_state, "add_to_queue", new_callable=AsyncMock) as mock_add:
            mock_add.return_value = True
            result = await match_state.add_to_queue(100)
            assert result is True
            mock_add.assert_called_once()

    @pytest.mark.asyncio
    async def test_remove_from_queue(self):
        from state.match_state import match_state
        from services.distributed_state import distributed_state
        with patch.object(distributed_state, "remove_from_queue", new_callable=AsyncMock) as mock_rem:
            await match_state.remove_from_queue(100)
            mock_rem.assert_called_once()

    @pytest.mark.asyncio
    async def test_is_in_chat(self):
        from state.match_state import match_state
        from services.distributed_state import distributed_state
        with patch.object(distributed_state, "is_in_chat", new_callable=AsyncMock) as mock_in_chat:
            mock_in_chat.return_value = True
            result = await match_state.is_in_chat(100)
            assert result is True

    @pytest.mark.asyncio
    async def test_disconnect(self):
        from state.match_state import match_state
        from services.distributed_state import distributed_state
        with patch.object(distributed_state, "atomic_disconnect", new_callable=AsyncMock) as MockAtomic:
            MockAtomic.return_value = (True, time.time() - 60, time.time() - 60)
            result = await match_state.disconnect(100)
            assert result is not None
            MockAtomic.assert_called_once_with(100)

    @pytest.mark.asyncio
    async def test_set_user_state(self):
        from state.match_state import match_state
        from services.distributed_state import distributed_state
        with patch.object(distributed_state, "set_user_state", new_callable=AsyncMock) as mock_set:
            await match_state.set_user_state(100, "awaiting_location")
            mock_set.assert_called_once_with("100", "awaiting_location")

    @pytest.mark.asyncio
    async def test_get_user_state(self):
        from state.match_state import match_state
        from services.distributed_state import distributed_state
        with patch.object(distributed_state, "get_user_state", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = "awaiting_location"
            state = await match_state.get_user_state(100)
            assert state == "awaiting_location"
