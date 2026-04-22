"""
Tests for Phase 2 hardening:
  1. State Authority   — server state is authoritative; payload.state is hint only
  2. Concurrency Lock  — acquire_action_lock / release_action_lock
  3. Target Integrity  — validate_target returns False for banned/missing users
  4. Session State     — set/get/clear session state; validate_session
"""
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from services.distributed_state import DistributedState


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def fresh_state():
    """Return a fresh DistributedState (not the singleton) with memory fallback."""
    obj = object.__new__(DistributedState)
    obj._init_state()
    return obj


# ─────────────────────────────────────────────────────────────────────────────
# 1. Concurrency lock  —  acquire / release
# ─────────────────────────────────────────────────────────────────────────────

class TestActionLock:
    def test_first_acquire_succeeds(self):
        ds = fresh_state()
        result = asyncio.get_event_loop().run_until_complete(
            ds.acquire_action_lock(user_id=1001)
        )
        assert result is True

    def test_second_acquire_blocked(self):
        ds = fresh_state()
        loop = asyncio.get_event_loop()
        loop.run_until_complete(ds.acquire_action_lock(user_id=1002))
        second = loop.run_until_complete(ds.acquire_action_lock(user_id=1002))
        assert second is False  # locked

    def test_release_allows_reacquire(self):
        ds = fresh_state()
        loop = asyncio.get_event_loop()
        loop.run_until_complete(ds.acquire_action_lock(user_id=1003))
        loop.run_until_complete(ds.release_action_lock(user_id=1003))
        reacquired = loop.run_until_complete(ds.acquire_action_lock(user_id=1003))
        assert reacquired is True

    def test_different_users_do_not_block_each_other(self):
        ds = fresh_state()
        loop = asyncio.get_event_loop()
        loop.run_until_complete(ds.acquire_action_lock(user_id=1004))
        other = loop.run_until_complete(ds.acquire_action_lock(user_id=1005))
        assert other is True  # different user, not blocked


# ─────────────────────────────────────────────────────────────────────────────
# 2. Session State  —  set / get / clear / validate
# ─────────────────────────────────────────────────────────────────────────────

class TestSessionState:
    def test_set_and_get_session(self):
        ds = fresh_state()
        loop = asyncio.get_event_loop()
        loop.run_until_complete(ds.set_session_state(100, 200, "ACTIVE"))
        state = loop.run_until_complete(ds.get_session_state(100, 200))
        assert state == "ACTIVE"

    def test_session_key_is_order_independent(self):
        ds = fresh_state()
        loop = asyncio.get_event_loop()
        loop.run_until_complete(ds.set_session_state(100, 200, "ACTIVE"))
        state_reversed = loop.run_until_complete(ds.get_session_state(200, 100))
        assert state_reversed == "ACTIVE"

    def test_clear_session(self):
        ds = fresh_state()
        loop = asyncio.get_event_loop()
        loop.run_until_complete(ds.set_session_state(100, 200, "ACTIVE"))
        loop.run_until_complete(ds.clear_session_state(100, 200))
        state = loop.run_until_complete(ds.get_session_state(100, 200))
        assert state is None

    def test_get_session_without_partner_returns_none(self):
        ds = fresh_state()
        state = asyncio.get_event_loop().run_until_complete(
            ds.get_session_state(999)  # user2=None, partner not set
        )
        assert state is None


# ─────────────────────────────────────────────────────────────────────────────
# 3. Target Integrity  —  validate_target
# ─────────────────────────────────────────────────────────────────────────────

class TestValidateTarget:
    def test_zero_target_always_valid(self):
        from state.match_state import match_state
        valid, _ = asyncio.get_event_loop().run_until_complete(
            match_state.validate_target(0)
        )
        assert valid is True

    def test_missing_user_returns_invalid(self):
        from state.match_state import match_state
        with patch(
            "database.repositories.user_repository.UserRepository.get_by_telegram_id",
            new_callable=AsyncMock, return_value=None
        ):
            valid, reason = asyncio.get_event_loop().run_until_complete(
                match_state.validate_target(9999)
            )
        assert valid is False
        assert "no longer exists" in reason

    def test_banned_user_returns_invalid(self):
        from state.match_state import match_state
        with patch(
            "database.repositories.user_repository.UserRepository.get_by_telegram_id",
            new_callable=AsyncMock, return_value={"is_banned": True}
        ):
            valid, reason = asyncio.get_event_loop().run_until_complete(
                match_state.validate_target(9998)
            )
        assert valid is False
        assert "no longer available" in reason

    def test_active_user_is_valid(self):
        from state.match_state import match_state
        with patch(
            "database.repositories.user_repository.UserRepository.get_by_telegram_id",
            new_callable=AsyncMock, return_value={"is_banned": False, "id": 42}
        ):
            valid, _ = asyncio.get_event_loop().run_until_complete(
                match_state.validate_target(42)
            )
        assert valid is True


# ─────────────────────────────────────────────────────────────────────────────
# 4. State Authority  —  SYSTEM_ONLY_STATES & is_client_settable
# ─────────────────────────────────────────────────────────────────────────────

class TestStateAuthority:
    def test_home_is_client_settable(self):
        from state.match_state import UserState
        assert UserState.is_client_settable(UserState.HOME) is True

    def test_searching_is_client_settable(self):
        from state.match_state import UserState
        assert UserState.is_client_settable(UserState.SEARCHING) is True

    def test_chatting_is_not_client_settable(self):
        from state.match_state import UserState
        assert UserState.is_client_settable(UserState.CHATTING) is False

    def test_matched_pending_is_not_client_settable(self):
        from state.match_state import UserState
        assert UserState.is_client_settable(UserState.MATCHED_PENDING) is False

    def test_content_review_is_not_client_settable(self):
        from state.match_state import UserState
        assert UserState.is_client_settable(UserState.CONTENT_REVIEW) is False
