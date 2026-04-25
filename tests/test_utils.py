"""
Tests for utils/ modules: rate_limiter, helpers, platform_adapter, ui_formatters
"""
import time
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch


# ═══════════════════════════════════════════════════════
# 1. RateLimiter Tests
# ═══════════════════════════════════════════════════════
class TestRateLimiter:
    def setup_method(self):
        from utils.rate_limiter import RateLimiter
        self.rl = RateLimiter()

    @pytest.mark.asyncio
    async def test_can_send_message_first_time(self):
        can_send, reason = await self.rl.can_send_message(1001)
        assert can_send is True
        assert reason == "OK"

    @pytest.mark.asyncio
    async def test_can_send_message_rapid_blocked(self):
        await self.rl.can_send_message(1001)
        # Immediately again should be blocked (< 1.0s)
        can_send, reason = await self.rl.can_send_message(1001)
        assert can_send is False
        assert reason in ("COOLDOWN", "MUTED")

    @pytest.mark.asyncio
    async def test_can_send_message_after_cooldown(self):
        await self.rl.can_send_message(1001)
        # Manually force the fallback store to think time passed
        self.rl._last_message[1001] = time.time() - 2.0
        can_send, reason = await self.rl.can_send_message(1001)
        assert can_send is True
        assert reason == "OK"

    @pytest.mark.asyncio
    async def test_can_matchmake_first_time(self):
        assert await self.rl.can_matchmake(2001) is True

    @pytest.mark.asyncio
    async def test_can_matchmake_rapid_blocked(self):
        await self.rl.can_matchmake(2001)
        assert await self.rl.can_matchmake(2001) is False

    @pytest.mark.asyncio
    async def test_can_matchmake_after_cooldown(self):
        await self.rl.can_matchmake(2001)
        self.rl._last_matchmaking[2001] = time.time() - 4.0
        assert await self.rl.can_matchmake(2001) is True

    @pytest.mark.asyncio
    async def test_can_report_first_time(self):
        assert await self.rl.can_report(3001) is True

    @pytest.mark.asyncio
    async def test_can_report_rapid_blocked(self):
        await self.rl.can_report(3001)
        assert await self.rl.can_report(3001) is False

    @pytest.mark.asyncio
    async def test_can_report_after_cooldown(self):
        await self.rl.can_report(3001)
        self.rl._last_report[3001] = time.time() - 6.0
        assert await self.rl.can_report(3001) is True

    @pytest.mark.asyncio
    async def test_different_users_independent(self):
        await self.rl.can_send_message(1001)
        can_send, _ = await self.rl.can_send_message(1002)
        assert can_send is True


# ═══════════════════════════════════════════════════════
# 2. is_vip_active Tests
# ═══════════════════════════════════════════════════════
class TestIsVipActive:
    def test_none_user(self):
        from utils.helpers import is_vip_active
        assert is_vip_active(None) is False

    def test_no_vip_status(self):
        from utils.helpers import is_vip_active
        assert is_vip_active({"vip_status": False}) is False

    def test_vip_active_no_expiry(self):
        from utils.helpers import is_vip_active
        assert is_vip_active({"vip_status": True}) is True

    def test_vip_expired(self):
        from utils.helpers import is_vip_active
        assert is_vip_active({"vip_status": True, "vip_expires_at": time.time() - 100}) is False

    def test_vip_not_expired(self):
        from utils.helpers import is_vip_active
        assert is_vip_active({"vip_status": True, "vip_expires_at": time.time() + 1000}) is True


# ═══════════════════════════════════════════════════════
# 3. UI Formatters Tests
# ═══════════════════════════════════════════════════════
class TestUIFormatters:
    def test_get_progression_text_no_levelup(self):
        from utils.ui_formatters import get_progression_text
        stats = {"u1_levelup": None, "u2_levelup": None}
        assert get_progression_text(stats, True) == ""

    def test_get_progression_text_with_levelup(self):
        from utils.ui_formatters import get_progression_text
        stats = {"u1_levelup": 5, "u2_levelup": None}
        result = get_progression_text(stats, True)
        assert "Level Up!" in result
        assert "Level 5" in result

    def test_get_progression_text_user2(self):
        from utils.ui_formatters import get_progression_text
        stats = {"u1_levelup": None, "u2_levelup": 3}
        result = get_progression_text(stats, False)
        assert "Level 3" in result

    def test_get_progress_bar(self):
        from utils.ui_formatters import get_progress_bar
        # Level 1 is 0-9 XP. Level 2 starts at 10 XP.
        # current_xp = 5 (Level 1, 5/10 XP progress)
        result = get_progress_bar(5)
        assert "Level 1" in result
        assert "5/10 XP" in result
        assert "█████" in result # 5 filled blocks for 50%
        
        # current_xp = 10 (Level 2, 0/30 XP progress since Level 3 starts at 40)
        # Level 2 base = (2-1)^2 * 10 = 10. Level 3 base = (3-1)^2 * 10 = 40.
        result = get_progress_bar(10)
        assert "Level 2" in result
        assert "0/30 XP" in result
        assert "░░░░░░░░░░" in result

    def test_format_session_summary_user1(self):
        from utils.ui_formatters import format_session_summary
        stats = {
            "duration_minutes": 10,
            "coins_earned": 25,
            "xp_earned": 20,
            "u2_coins_earned": 15,
            "u2_xp_earned": 10,
            "partner_id": 2002,
            "user_id": 1001,
            "u1_levelup": None,
            "u2_levelup": None,
        }
        result = format_session_summary(stats, is_user1=True, coins_balance=100)
        assert "10 min" in result
        assert "+25" in result
        assert "+20" in result
        assert "100 coins" in result

    def test_format_session_summary_user2(self):
        from utils.ui_formatters import format_session_summary
        stats = {
            "duration_minutes": 5,
            "coins_earned": 25,
            "xp_earned": 20,
            "u2_coins_earned": 15,
            "u2_xp_earned": 10,
            "partner_id": 2002,
            "user_id": 1001,
            "u1_levelup": None,
            "u2_levelup": None,
            "total_xp": 45  # Level 3 (0-9, 10-39, 40-89)
        }
        result = format_session_summary(stats, is_user1=False, coins_balance=50)
        assert "+15" in result  # u2_coins_earned
        assert "+10" in result  # u2_xp_earned
        assert "Level 3" in result
        assert "5/50 XP" in result # Level 3 starts at 40, Level 4 at 90. 45-40=5. 90-40=50.

    def test_get_match_found_text_concise(self):
        from utils.ui_formatters import get_match_found_text
        result = get_match_found_text(include_safety=False)
        assert "Match Found!" in result
        assert "Safety Reminder" not in result

    def test_get_match_found_text_with_safety(self):
        from utils.ui_formatters import get_match_found_text
        result = get_match_found_text(include_safety=True)
        assert "Match Found!" in result
        assert "Safety Reminder" in result
        assert "10 coin penalty" in result


# ═══════════════════════════════════════════════════════
# 4. PlatformAdapter Tests
# ═══════════════════════════════════════════════════════
class TestPlatformAdapter:
    @pytest.mark.asyncio
    async def test_send_to_telegram_user(self):
        from utils.platform_adapter import PlatformAdapter
        client = AsyncMock()
        client.send_message = AsyncMock()
        await PlatformAdapter.send_cross_platform(client, 12345, "Hello")
        client.send_message.assert_called_once()
        args = client.send_message.call_args
        assert args[1]["chat_id"] == 12345
        assert args[1]["text"] == "Hello"

    @pytest.mark.asyncio
    async def test_send_to_messenger_user(self):
        from utils.platform_adapter import PlatformAdapter
        client = AsyncMock()
        mock_user = {"username": "msg_PSID123"}

        with patch("database.repositories.user_repository.UserRepository.get_by_telegram_id", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_user
            with patch("messenger_api._send_payload") as mock_send:
                mock_send.return_value = {"success": True}
                await PlatformAdapter.send_cross_platform(client, 10**15 + 1, "Hi from TG")
                assert mock_send.called
                # Verify PSID was extracted correctly
                args, kwargs = mock_send.call_args
                assert args[0]["recipient"]["id"] == "PSID123"

    @pytest.mark.asyncio
    async def test_send_to_messenger_no_user(self):
        from utils.platform_adapter import PlatformAdapter
        client = AsyncMock()

        with patch("database.repositories.user_repository.UserRepository") as MockRepo:
            MockRepo.get_by_telegram_id = AsyncMock(return_value=None)
            with patch("messenger_api.send_message") as mock_send:
                await PlatformAdapter.send_cross_platform(client, 10**15 + 1, "fail")
                mock_send.assert_not_called()


# ═══════════════════════════════════════════════════════
# 5. helpers.send_cross_platform Tests
# ═══════════════════════════════════════════════════════
class TestHelpersSendCrossPlatform:
    @pytest.mark.asyncio
    async def test_delegates_to_adapter(self):
        from utils.helpers import send_cross_platform
        client = AsyncMock()
        with patch("utils.platform_adapter.PlatformAdapter.send_cross_platform") as MockSend:
            MockSend.return_value = AsyncMock()
            await send_cross_platform(client, 555, "test")
            MockSend.assert_called_once_with(client, 555, "test", None)


# ═══════════════════════════════════════════════════════
# 6. helpers.update_user_ui Tests
# ═══════════════════════════════════════════════════════
class TestUpdateUserUI:
    @pytest.mark.asyncio
    async def test_skip_echo_partner(self):
        """User ID 1 (echo partner) should be silently skipped."""
        from utils.helpers import update_user_ui
        client = AsyncMock()
        result = await update_user_ui(client, 1, "test", None)
        assert result is None
        client.send_message.assert_not_called()

    @pytest.mark.asyncio
    async def test_messenger_user_routes_to_cross_platform(self):
        from utils.helpers import update_user_ui
        client = AsyncMock()
        with patch("utils.helpers.send_cross_platform", new_callable=AsyncMock) as mock_send:
            await update_user_ui(client, 10**15 + 5, "hello", None)
            mock_send.assert_called_once()

    @pytest.mark.asyncio
    async def test_telegram_user_edits_previous_message(self):
        from utils.helpers import update_user_ui
        from state.match_state import match_state
        match_state.user_ui_messages[9999] = 42
        client = AsyncMock()
        client.edit_message_text = AsyncMock()
        await update_user_ui(client, 9999, "updated", None)
        client.edit_message_text.assert_called_once()
        # Cleanup
        match_state.user_ui_messages.pop(9999, None)

    @pytest.mark.asyncio
    async def test_telegram_user_sends_new_if_no_previous(self):
        from utils.helpers import update_user_ui
        from state.match_state import match_state
        match_state.user_ui_messages.pop(8888, None)
        match_state.ui_history.pop(8888, None)
        client = AsyncMock()
        sent_msg = MagicMock()
        sent_msg.id = 99
        client.send_message = AsyncMock(return_value=sent_msg)
        await update_user_ui(client, 8888, "new msg", None)
        client.send_message.assert_called_once()
        # Verify both legacy and new history tracking
        assert match_state.user_ui_messages.get(8888) == 99
        assert any(item["id"] == 99 for item in match_state.ui_history.get(8888, []))
        # Cleanup
        match_state.user_ui_messages.pop(8888, None)
        match_state.ui_history.pop(8888, None)
