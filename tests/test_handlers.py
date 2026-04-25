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
        from utils.rate_limiter import rate_limiter
        client = AsyncMock()
        with patch.object(rate_limiter, 'can_matchmake', return_value=True):
            response = await MatchingHandler.handle_search(client, 100)
            assert response is not None
            assert "text" in response
            assert "reply_markup" in response

    @pytest.mark.asyncio
    async def test_handle_stop(self):
        from handlers.actions.matching import MatchingHandler
        import app_state
        client = AsyncMock()
        app_state.engine = MagicMock()
        with patch.object(app_state.engine, "process_event", new_callable=AsyncMock) as mock_process:
            mock_process.return_value = {"success": True}
            response = await MatchingHandler.handle_stop(client, 100)
            assert response is None  # Engine handles UI
            mock_process.assert_called_once_with({"event_type": "END_CHAT", "user_id": "100"})

    @pytest.mark.asyncio
    async def test_handle_cancel(self):
        from handlers.actions.matching import MatchingHandler
        import app_state
        client = AsyncMock()
        app_state.engine = MagicMock()
        with patch.object(app_state.engine, "process_event", new_callable=AsyncMock) as mock_process:
            mock_process.return_value = {"success": True}
            response = await MatchingHandler.handle_cancel(client, 100)
            assert response is None  # Engine handles UI
            mock_process.assert_called_once_with({"event_type": "STOP_SEARCH", "user_id": "100"})

    @pytest.mark.asyncio
    async def test_handle_next(self):
        from handlers.actions.matching import MatchingHandler
        import app_state
        client = AsyncMock()
        app_state.engine = MagicMock()
        with patch.object(app_state.engine, "process_event", new_callable=AsyncMock) as mock_process:
            mock_process.return_value = {"success": True}
            response = await MatchingHandler.handle_next(client, 100)
            assert response is None  # Engine handles UI
            mock_process.assert_called_once_with({"event_type": "NEXT_MATCH", "user_id": "100"})

    @pytest.mark.asyncio
    async def test_handle_icebreaker(self):
        from handlers.actions.matching import MatchingHandler
        from state.match_state import match_state
        from services.distributed_state import distributed_state
        # Set user in chat
        await distributed_state.set_partner(100, 200)
        
        client = AsyncMock()
        with patch("services.user_service.UserService.deduct_coins", return_value=True):
            response = await MatchingHandler.handle_icebreaker(client, 100)
            assert response is not None
            assert "text" in response
        # Cleanup
        await distributed_state.clear_partner(100)


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
        from services.distributed_state import distributed_state
        await distributed_state.set_partner(100, 200)
        client = AsyncMock()
        response = await SocialHandler.handle_report(client, 100)
        assert response is not None
        # Cleanup
        await distributed_state.clear_partner(100)

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
        with patch("database.repositories.admin_repository.AdminRepository.get_system_stats") as MockGet, \
             patch("state.match_state.match_state.get_stats") as MockLive, \
             patch("services.distributed_state.distributed_state.get_queue_candidates") as MockQueue:
            MockGet.return_value = {
                "new_users_24h": 10, "total_users": 100, "sessions_24h": 500, "pending_reports": 5
            }
            MockLive.return_value = {"active_chats": 20, "queue_length": 10}
            MockQueue.return_value = ["100", "msg_200"]
            response = await AdminHandler.handle_stats(client, ADMIN_ID)
            assert "text" in response
            assert "100" in response["text"]




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
