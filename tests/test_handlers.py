"""
Tests for handlers/actions/: MatchingHandler, StatsHandler, SocialHandler,
EconomyHandler, OnboardingHandler, AdminHandler
All of these return response dicts — no Pyrogram decorator magic involved.
"""
import time
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ═══════════════════════════════════════════════════════
# 1. MatchingHandler Tests
# ═══════════════════════════════════════════════════════
class TestMatchingHandler:
    @pytest.mark.asyncio
    async def test_handle_search_returns_search_menu(self):
        from handlers.actions.matching import MatchingHandler
        client = AsyncMock()
        response = await MatchingHandler.handle_search(client, 100)
        assert response is not None
        assert "text" in response or "reply_markup" in response

    @pytest.mark.asyncio
    async def test_handle_stop_not_in_chat(self):
        from handlers.actions.matching import MatchingHandler
        client = AsyncMock()
        # disconnect returns None when user is not in a chat
        with patch("services.matchmaking.MatchmakingService.disconnect", new_callable=AsyncMock) as MockDisconnect:
            MockDisconnect.return_value = None
            response = await MatchingHandler.handle_stop(client, 100)
            assert response is not None
            assert "chat ended" in response.get("text", "").lower() or "alert" in response

    @pytest.mark.asyncio
    async def test_handle_stop_in_chat(self):
        from handlers.actions.matching import MatchingHandler
        client = AsyncMock()
        mock_stats = {
            "partner_id": 200, "duration_minutes": 5,
            "coins_earned": 20, "xp_earned": 10,
            "u2_coins_earned": 15, "u2_xp_earned": 8,
            "u1_levelup": None, "u2_levelup": None,
            "total_matches": 3
        }
        with patch("services.matchmaking.MatchmakingService.disconnect") as MockDisconnect, \
             patch("database.repositories.user_repository.UserRepository.get_by_telegram_id") as MockGet, \
             patch("state.match_state.match_state.get_user_state") as MockState:
            from state.match_state import UserState
            MockState.return_value = UserState.CHATTING
            MockDisconnect.return_value = mock_stats
            MockGet.return_value = {"coins": 50}
            response = await MatchingHandler.handle_stop(client, 100)
            assert "text" in response
            assert "Summary" in response["text"] or "Duration" in response["text"]

    @pytest.mark.asyncio
    async def test_handle_cancel(self):
        from handlers.actions.matching import MatchingHandler
        client = AsyncMock()
        with patch("services.matchmaking.MatchmakingService.remove_from_queue", new_callable=AsyncMock) as MockRemove, \
             patch("database.repositories.user_repository.UserRepository.get_by_telegram_id") as MockGet:
            MockRemove.return_value = None
            MockGet.return_value = {"coins": 30}
            response = await MatchingHandler.handle_cancel(client, 100)
            # Cancel returns home/start menu, so just check it's a valid response
            assert response is not None
            assert "text" in response

    @pytest.mark.asyncio
    async def test_handle_next_cooldown_triggered(self):
        from handlers.actions.matching import MatchingHandler
        from utils.behavior_tracker import behavior_tracker
        from utils.rate_limiter import rate_limiter
        client = AsyncMock()
        user_id = 100
        
        # behavior_tracker.get_next_cooldown is now async
        with patch.object(rate_limiter, 'get_cooldown_remaining', return_value=5.0), \
             patch.object(behavior_tracker, 'get_next_cooldown', new_callable=AsyncMock) as mock_cooldown, \
             patch.object(behavior_tracker, 'record_next', new_callable=AsyncMock):
            mock_cooldown.return_value = 5.0
            # Next now checks if in chat; patch get_user_state to pass
            with patch("state.match_state.match_state.get_user_state", new_callable=AsyncMock) as MockState:
                from state.match_state import UserState
                MockState.return_value = UserState.CHATTING
                response = await MatchingHandler.handle_next(client, user_id)
                assert "alert" in response
                assert "slow down" in response["alert"].lower()

    @pytest.mark.asyncio
    async def test_handle_icebreaker(self):
        from handlers.actions.matching import MatchingHandler
        from state.match_state import match_state
        from services.distributed_state import distributed_state
        # Set user in chat
        await distributed_state.set_partner(100, 200)
        match_state.active_chats[100] = 200
        match_state.active_chats[200] = 100
        
        client = AsyncMock()
        response = await MatchingHandler.handle_icebreaker(client, 100)
        assert response is not None
        # Cleanup
        await distributed_state.clear_partner(100)
        match_state.active_chats.clear()


# ═══════════════════════════════════════════════════════
# 2. StatsHandler Tests
# ═══════════════════════════════════════════════════════
class TestStatsHandler:
    @pytest.mark.asyncio
    async def test_handle_stats_no_user(self):
        from handlers.actions.stats import StatsHandler
        client = AsyncMock()
        with patch("handlers.actions.stats.StatsRepository.get_user_stats") as MockGet:
            MockGet.return_value = None
            response = await StatsHandler.handle_stats(client, 100)
            assert "text" in response or "alert" in response

    @pytest.mark.asyncio
    async def test_handle_stats_with_user(self):
        from handlers.actions.stats import StatsHandler
        client = AsyncMock()
        # Patch directly on the source module used inside StatsHandler
        with patch("handlers.actions.stats.StatsRepository.get_user_stats") as MockStats:
            MockStats.return_value = {
                "first_name": "Test User", "is_guest": False, "vip_status": True, 
                "coins": 100, "total_matches": 50, "xp": 500, "daily_streak": 3,
                "level": 8, "reports": 0, "total_chat_time": 10
            }
            response = await StatsHandler.handle_stats(client, 100)
            assert "text" in response
            assert "100" in response["text"]  # coins
            assert "Level" in response["text"] or "level" in response["text"].lower()

    @pytest.mark.asyncio
    async def test_handle_leaderboard(self):
        from handlers.actions.stats import StatsHandler
        client = AsyncMock()
        response = await StatsHandler.handle_leaderboard(client, 100)
        assert "text" in response
        assert "Leaderboard" in response["text"]

    @pytest.mark.asyncio
    async def test_handle_leaderboard_category(self):
        from handlers.actions.stats import StatsHandler
        client = AsyncMock()
        with patch("handlers.actions.stats.StatsRepository.get_leaderboard") as MockGet:
            MockGet.return_value = [
                {"telegram_id": 1, "xp": 1000, "first_name": "Alice", "level": 10},
                {"telegram_id": 2, "xp": 800, "first_name": "Bob", "level": 5},
            ]
            response = await StatsHandler.handle_leaderboard_category(client, 100, "all")
            assert "text" in response
            assert "Alice" in response["text"]


# ═══════════════════════════════════════════════════════
# 3. OnboardingHandler Tests
# ═══════════════════════════════════════════════════════
class TestOnboardingHandler:
    @pytest.mark.asyncio
    async def test_handle_start(self):
        from handlers.actions.onboarding import OnboardingHandler
        client = AsyncMock()
        response = await OnboardingHandler.handle_start(client, 100)
        assert "text" in response
        # handle_start shows the gender selection keyboard, no set_state in return dict
        assert "reply_markup" in response

    @pytest.mark.asyncio
    async def test_handle_skip(self):
        from handlers.actions.onboarding import OnboardingHandler
        client = AsyncMock()
        response = await OnboardingHandler.handle_skip(client, 100)
        assert "text" in response

    @pytest.mark.asyncio
    async def test_handle_set_gender(self):
        from handlers.actions.onboarding import OnboardingHandler
        client = AsyncMock()
        with patch("database.repositories.user_repository.UserRepository.update") as MockUpdate:
            MockUpdate.return_value = AsyncMock()
            response = await OnboardingHandler.handle_set_gender(client, 100, "male")
            assert "text" in response
            assert "reply_markup" in response  # Now shows age menu, no state
            MockUpdate.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_location_skip(self):
        from handlers.actions.onboarding import OnboardingHandler
        client = AsyncMock()
        response = await OnboardingHandler.handle_location_skip(client, 100)
        assert "text" in response
        assert "set_state" in response

    @pytest.mark.asyncio
    async def test_handle_bio_skip(self):
        from handlers.actions.onboarding import OnboardingHandler
        client = AsyncMock()
        with patch("handlers.actions.onboarding.UserRepository") as MockRepo:
            MockRepo.update = AsyncMock()
            MockRepo.get_by_telegram_id = AsyncMock(return_value={
                "gender": "Male", "location": "Secret", "is_guest": False
            })
            response = await OnboardingHandler.handle_bio_skip(client, 100)
            assert "text" in response



# ═══════════════════════════════════════════════════════
# 4. SocialHandler Tests
# ═══════════════════════════════════════════════════════
class TestSocialHandler:
    @pytest.mark.asyncio
    async def test_handle_report_not_in_chat(self):
        from handlers.actions.social import SocialHandler
        client = AsyncMock()
        response = await SocialHandler.handle_report(client, 100)
        assert response is not None
        assert "alert" in response or "text" in response

    @pytest.mark.asyncio
    async def test_handle_report_in_chat(self):
        from handlers.actions.social import SocialHandler
        from state.match_state import match_state
        from services.distributed_state import distributed_state
        await distributed_state.set_partner(100, 200)
        match_state.active_chats[100] = 200
        match_state.active_chats[200] = 100
        client = AsyncMock()
        response = await SocialHandler.handle_report(client, 100)
        assert response is not None
        # Cleanup
        await distributed_state.clear_partner(100)
        match_state.active_chats.clear()

    @pytest.mark.asyncio
    async def test_handle_open_reactions_not_in_chat(self):
        from handlers.actions.social import SocialHandler
        client = AsyncMock()
        response = await SocialHandler.handle_open_reactions(client, 100)
        assert "alert" in response

    @pytest.mark.asyncio
    async def test_handle_back_to_chat(self):
        from handlers.actions.social import SocialHandler
        client = AsyncMock()
        response = await SocialHandler.handle_back_to_chat(client, 100)
        assert "text" in response

    @pytest.mark.asyncio
    async def test_handle_peek_not_in_chat(self):
        from handlers.actions.social import SocialHandler
        client = AsyncMock()
        response = await SocialHandler.handle_peek(client, 100)
        assert "alert" in response

    @pytest.mark.asyncio
    async def test_handle_add_friend_not_in_chat(self):
        from handlers.actions.social import SocialHandler
        client = AsyncMock()
        response = await SocialHandler.handle_add_friend(client, 100)
        assert "alert" in response

    @pytest.mark.asyncio
    async def test_handle_user_appeal(self):
        from handlers.actions.social import SocialHandler
        client = AsyncMock()
        response = await SocialHandler.handle_user_appeal(client, 100)
        assert response is not None
        assert "set_state" in response or "text" in response


# ═══════════════════════════════════════════════════════
# 5. EconomyHandler Tests
# ═══════════════════════════════════════════════════════
class TestEconomyHandler:
    @pytest.mark.asyncio
    async def test_handle_priority_search_no_user(self):
        from handlers.actions.economy import EconomyHandler
        client = AsyncMock()
        with patch("database.repositories.user_repository.UserRepository.get_by_telegram_id") as MockGet:
            MockGet.return_value = None
            response = await EconomyHandler.handle_priority_search(client, 100)
            assert response is not None

    @pytest.mark.asyncio
    async def test_handle_reveal_not_in_chat(self):
        from handlers.actions.economy import EconomyHandler
        client = AsyncMock()
        response = await EconomyHandler.handle_reveal(client, 100)
        assert "alert" in response

    @pytest.mark.asyncio
    async def test_handle_booster_menu(self):
        from handlers.actions.economy import EconomyHandler
        client = AsyncMock()
        response = await EconomyHandler.handle_booster_menu(client, 100)
        assert "text" in response

    @pytest.mark.asyncio
    async def test_handle_priority_packs(self):
        from handlers.actions.economy import EconomyHandler
        client = AsyncMock()
        response = await EconomyHandler.handle_priority_packs(client, 100)
        assert "text" in response

    @pytest.mark.asyncio
    async def test_handle_seasonal_shop(self):
        from handlers.actions.economy import EconomyHandler
        client = AsyncMock()
        response = await EconomyHandler.handle_seasonal_shop(client, 100)
        assert "text" in response

    @pytest.mark.asyncio
    async def test_handle_buy_pack_insufficient_coins(self):
        from handlers.actions.economy import EconomyHandler
        client = AsyncMock()
        with patch("handlers.actions.economy.UserService") as MockUS:
            MockUS.deduct_coins = AsyncMock(return_value=False)
            response = await EconomyHandler.handle_buy_pack(client, 100, 5)
            assert "alert" in response
            assert "insufficient" in response["alert"].lower() or "coins" in response["alert"].lower()

    @pytest.mark.asyncio
    async def test_handle_buy_pack_success(self):
        from handlers.actions.economy import EconomyHandler
        client = AsyncMock()
        with patch("handlers.actions.economy.UserService") as MockUS, \
             patch("handlers.actions.economy.UserRepository") as MockRepo, \
             patch("handlers.actions.economy.get_start_text") as MockText:
            MockUS.deduct_coins = AsyncMock(return_value=True)
            MockRepo.get_by_telegram_id = AsyncMock(return_value={
                "priority_matches": 0, "coins": 100, "is_guest": False
            })
            MockRepo.update = AsyncMock()
            MockText.return_value = "Welcome back!"
            response = await EconomyHandler.handle_buy_pack(client, 100, 5)
            assert "alert" in response
            assert "success" in response["alert"].lower() or "purchased" in response["alert"].lower() or "added" in response["alert"].lower()


# ═══════════════════════════════════════════════════════
# 6. AdminHandler Tests
# ═══════════════════════════════════════════════════════
class TestAdminHandler:
    @pytest.mark.asyncio
    async def test_handle_stats_non_admin(self):
        from handlers.actions.admin import AdminHandler
        client = AsyncMock()
        response = await AdminHandler.handle_stats(client, 12345)  # not ADMIN_ID
        assert "alert" in response
        assert "Unauthorized" in response["alert"]

    @pytest.mark.asyncio
    async def test_handle_stats_admin(self):
        from handlers.actions.admin import AdminHandler
        from config import ADMIN_ID
        client = AsyncMock()
        with patch("database.repositories.admin_repository.AdminRepository.get_system_stats") as MockGet:
            MockGet.return_value = {
                "total_users": 100, "sessions_24h": 500, "pending_reports": 5
            }
            response = await AdminHandler.handle_stats(client, ADMIN_ID)
            assert "text" in response
            assert "100" in response["text"]

    @pytest.mark.asyncio
    async def test_handle_admin_health(self):
        from handlers.actions.admin import AdminHandler
        from config import ADMIN_ID
        from state.match_state import match_state
        match_state.bot_start_time = time.time() - 3600
        client = AsyncMock()
        response = await AdminHandler.handle_admin_health(client, ADMIN_ID)
        assert "text" in response
        assert "Health" in response["text"]

    @pytest.mark.asyncio
    async def test_handle_broadcast_prompt_non_admin(self):
        from handlers.actions.admin import AdminHandler
        client = AsyncMock()
        response = await AdminHandler.handle_broadcast_prompt(client, 12345)
        assert "Unauthorized" in response.get("alert", "")

    @pytest.mark.asyncio
    async def test_handle_gift_prompt_admin(self):
        from handlers.actions.admin import AdminHandler
        from config import ADMIN_ID
        client = AsyncMock()
        response = await AdminHandler.handle_gift_prompt(client, ADMIN_ID)
        # gift_prompt returns a text prompt with a cancel button, no set_state
        assert "text" in response

    @pytest.mark.asyncio
    async def test_handle_debug_admin(self):
        from handlers.actions.admin import AdminHandler
        from config import ADMIN_ID
        client = AsyncMock()
        with patch("state.match_state.match_state.add_to_chat", new_callable=AsyncMock) as MockAdd:
            response = await AdminHandler.handle_debug(client, ADMIN_ID)
            assert "text" in response
            MockAdd.assert_called_once()


    @pytest.mark.asyncio
    async def test_handle_reset_confirm(self):
        from handlers.actions.admin import AdminHandler
        from config import ADMIN_ID
        client = AsyncMock()
        response = await AdminHandler.handle_reset_confirm(client, ADMIN_ID)
        assert "text" in response
        # Text says CRITICAL ACTION, not reset
        assert "critical" in response["text"].lower() or "clear" in response["text"].lower()

    @pytest.mark.asyncio
    async def test_handle_set_vip_button_non_admin(self):
        from handlers.actions.admin import AdminHandler
        client = AsyncMock()
        response = await AdminHandler.handle_set_vip_button(client, 12345, 200, "true")
        assert "Unauthorized" in response.get("alert", "")

    @pytest.mark.asyncio
    async def test_handle_set_vip_button_admin(self):
        from handlers.actions.admin import AdminHandler
        from config import ADMIN_ID
        client = AsyncMock()
        with patch("handlers.actions.admin.UserRepository") as MockRepo:
            MockRepo.update = AsyncMock()
            client.send_message = AsyncMock()
            response = await AdminHandler.handle_set_vip_button(client, ADMIN_ID, 200, "true")
            assert "alert" in response
            MockRepo.update.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_quick_gift(self):
        from handlers.actions.admin import AdminHandler
        from config import ADMIN_ID
        client = AsyncMock()
        with patch("handlers.actions.admin.UserRepository") as MockRepo:
            MockRepo.increment_coins = AsyncMock()
            client.send_message = AsyncMock()
            response = await AdminHandler.handle_quick_gift(client, ADMIN_ID, 200, 50)
            assert "alert" in response

    @pytest.mark.asyncio
    async def test_handle_quick_deduct(self):
        from handlers.actions.admin import AdminHandler
        from config import ADMIN_ID
        client = AsyncMock()
        with patch("handlers.actions.admin.UserRepository") as MockRepo:
            MockRepo.increment_coins = AsyncMock()
            client.send_message = AsyncMock()
            response = await AdminHandler.handle_quick_deduct(client, ADMIN_ID, 200, 30)
            assert "alert" in response

    @pytest.mark.asyncio
    async def test_handle_list_banned(self):
        from handlers.actions.admin import AdminHandler
        from config import ADMIN_ID
        client = AsyncMock()
        with patch("handlers.actions.admin.AdminRepository") as MockRepo:
            MockRepo.get_banned_users = AsyncMock(return_value=[])
            response = await AdminHandler.handle_list_banned(client, ADMIN_ID)
            # Empty list returns alert "No users are currently banned"
            assert "text" in response or "alert" in response
