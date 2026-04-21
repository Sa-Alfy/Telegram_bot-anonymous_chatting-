"""
Tests for services/: UserService, EconomyService, MatchmakingService, event_manager
All DB calls are mocked — these are pure logic unit tests.
"""
import time
import math
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock


# ═══════════════════════════════════════════════════════
# 1. UserService Tests
# ═══════════════════════════════════════════════════════
class TestUserServiceAddXP:
    @pytest.mark.asyncio
    async def test_add_xp_guest_returns_none(self):
        with patch("database.repositories.user_repository.UserRepository.get_by_telegram_id") as MockGet:
            MockGet.return_value = {"is_guest": True, "xp": 0, "level": 1}
            from services.user_service import UserService
            result = await UserService.add_xp(100, 10)
            assert result is None

    @pytest.mark.asyncio
    async def test_add_xp_no_user_returns_none(self):
        with patch("services.user_service.UserRepository") as MockRepo:
            MockRepo.get_by_telegram_id = AsyncMock(return_value=None)
            from services.user_service import UserService
            result = await UserService.add_xp(100, 10)
            assert result is None

    @pytest.mark.asyncio
    async def test_add_xp_normal_no_levelup(self):
        with patch("services.user_service.UserRepository") as MockRepo:
            MockRepo.get_by_telegram_id = AsyncMock(return_value={
                "is_guest": False, "xp": 0, "level": 1,
                "coin_booster": {}
            })
            MockRepo.increment_xp = AsyncMock(return_value=5)
            MockRepo.update = AsyncMock()
            from services.user_service import UserService
            result = await UserService.add_xp(100, 5)
            assert result is None  # 5 XP is level floor(sqrt(0.5))+1 = 1, no change
            MockRepo.update.assert_not_called()

    @pytest.mark.asyncio
    async def test_add_xp_with_levelup(self):
        with patch("services.user_service.UserRepository") as MockRepo:
            MockRepo.get_by_telegram_id = AsyncMock(return_value={
                "is_guest": False, "xp": 0, "level": 1,
                "coin_booster": {}
            })
            MockRepo.increment_xp = AsyncMock(return_value=10)
            MockRepo.update = AsyncMock()
            from services.user_service import UserService
            # Need enough XP to reach level 2: floor(sqrt(xp/10)) + 1 ≥ 2
            # sqrt(xp/10) ≥ 1 → xp ≥ 10
            result = await UserService.add_xp(100, 10)
            assert result == 2

    @pytest.mark.asyncio
    async def test_add_xp_booster_doubles(self):
        with patch("services.user_service.UserRepository") as MockRepo:
            MockRepo.get_by_telegram_id = AsyncMock(return_value={
                "is_guest": False, "xp": 0, "level": 1,
                "coin_booster": {"active": True, "expires_at": time.time() + 1000}
            })
            MockRepo.increment_xp = AsyncMock(return_value=10)
            MockRepo.update = AsyncMock()
            from services.user_service import UserService
            # 5 XP doubled to 10 → level 2
            result = await UserService.add_xp(100, 5)
            assert result == 2


class TestUserServiceAddCoins:
    @pytest.mark.asyncio
    async def test_add_coins_guest_skipped(self):
        with patch("services.user_service.UserRepository") as MockRepo:
            MockRepo.get_by_telegram_id = AsyncMock(return_value={"is_guest": True})
            MockRepo.increment_coins = AsyncMock()
            from services.user_service import UserService
            await UserService.add_coins(100, 10)
            MockRepo.increment_coins.assert_not_called()

    @pytest.mark.asyncio
    async def test_add_coins_normal(self):
        with patch("services.user_service.UserRepository") as MockRepo:
            MockRepo.get_by_telegram_id = AsyncMock(return_value={
                "is_guest": False, "coin_booster": {}
            })
            MockRepo.increment_coins = AsyncMock()
            from services.user_service import UserService
            await UserService.add_coins(100, 10)
            MockRepo.increment_coins.assert_called_once_with(100, 10)

    @pytest.mark.asyncio
    async def test_add_coins_booster_doubles(self):
        with patch("services.user_service.UserRepository") as MockRepo:
            MockRepo.get_by_telegram_id = AsyncMock(return_value={
                "is_guest": False,
                "coin_booster": {"active": True, "expires_at": time.time() + 500}
            })
            MockRepo.increment_coins = AsyncMock()
            from services.user_service import UserService
            await UserService.add_coins(100, 10)
            MockRepo.increment_coins.assert_called_once_with(100, 20)


class TestUserServiceDeductCoins:
    @pytest.mark.asyncio
    async def test_deduct_coins_success(self):
        mock_cursor = MagicMock()
        mock_cursor.rowcount = 1
        with patch("services.user_service.db") as MockDB:
            MockDB.execute = AsyncMock(return_value=mock_cursor)
            from services.user_service import UserService
            result = await UserService.deduct_coins(100, 5)
            assert result is True

    @pytest.mark.asyncio
    async def test_deduct_coins_insufficient(self):
        mock_cursor = MagicMock()
        mock_cursor.rowcount = 0
        with patch("services.user_service.db") as MockDB:
            MockDB.execute = AsyncMock(return_value=mock_cursor)
            from services.user_service import UserService
            result = await UserService.deduct_coins(100, 5)
            assert result is False


class TestUserServiceUpdateProfile:
    @pytest.mark.asyncio
    async def test_update_profile(self):
        with patch("services.user_service.UserRepository") as MockRepo:
            MockRepo.update = AsyncMock()
            from services.user_service import UserService
            await UserService.update_profile(100, "Male", "NYC", "Hello!")
            MockRepo.update.assert_called_once_with(
                100, gender="Male", location="NYC", bio="Hello!", is_guest=False
            )


class TestUserServiceReportUser:
    @pytest.mark.asyncio
    async def test_report_auto_block_on_3(self):
        with patch("database.repositories.report_repository.ReportRepository.create") as MockCreate, \
             patch("services.user_service.db") as MockDB, \
             patch("database.repositories.user_repository.UserRepository.set_blocked") as MockBlock:
            MockCreate.return_value = AsyncMock()
            MockDB.execute = AsyncMock()
            MockDB.fetchone = AsyncMock(return_value={"reports": 3})
            MockBlock.return_value = AsyncMock()
            from services.user_service import UserService
            result = await UserService.report_user(100, 200, "spam")
            assert result is True
            MockBlock.assert_called_once_with(200, True)

    @pytest.mark.asyncio
    async def test_report_no_block_under_threshold(self):
        with patch("services.user_service.ReportRepository") as MockReport, \
             patch("services.user_service.db") as MockDB:
            MockReport.create = AsyncMock()
            MockDB.execute = AsyncMock()
            MockDB.fetchone = AsyncMock(return_value={"reports": 2})
            from services.user_service import UserService
            result = await UserService.report_user(100, 200, "spam")
            assert result is False


class TestUserServiceIncrementChallenge:
    @pytest.mark.asyncio
    async def test_increment_challenge(self):
        with patch("services.user_service.UserRepository") as MockRepo:
            MockRepo.get_by_telegram_id = AsyncMock(return_value={
                "mini_challenges": {"messages_sent": 5}
            })
            MockRepo.update = AsyncMock()
            from services.user_service import UserService
            await UserService.increment_challenge(100, "messages_sent")
            call_args = MockRepo.update.call_args
            assert call_args[1]["mini_challenges"]["messages_sent"] == 6


class TestUserServiceCheckMilestones:
    @pytest.mark.asyncio
    async def test_milestone_reached(self):
        with patch("services.user_service.UserRepository") as MockRepo:
            MockRepo.get_by_telegram_id = AsyncMock(return_value={
                "mini_challenges": {"messages_sent": 10},
                "completed_milestones": []
            })
            MockRepo.increment_xp = AsyncMock()
            MockRepo.increment_coins = AsyncMock()
            MockRepo.update = AsyncMock()
            from services.user_service import UserService
            result = await UserService.check_milestones(100, "messages_sent")
            assert result is not None
            assert result["milestone"] == 10

    @pytest.mark.asyncio
    async def test_milestone_already_completed(self):
        with patch("services.user_service.UserRepository") as MockRepo:
            MockRepo.get_by_telegram_id = AsyncMock(return_value={
                "mini_challenges": {"messages_sent": 10},
                "completed_milestones": ["messages_sent_10"]
            })
            from services.user_service import UserService
            result = await UserService.check_milestones(100, "messages_sent")
            assert result is None

    @pytest.mark.asyncio
    async def test_milestone_not_at_threshold(self):
        with patch("services.user_service.UserRepository") as MockRepo:
            MockRepo.get_by_telegram_id = AsyncMock(return_value={
                "mini_challenges": {"messages_sent": 7},
                "completed_milestones": []
            })
            from services.user_service import UserService
            result = await UserService.check_milestones(100, "messages_sent")
            assert result is None


# ═══════════════════════════════════════════════════════
# 2. EconomyService Tests
# ═══════════════════════════════════════════════════════
class TestEconomyServiceDynamicCost:
    @pytest.mark.asyncio
    async def test_no_user_returns_default(self):
        with patch("database.repositories.user_repository.UserRepository.get_by_telegram_id") as MockGet:
            MockGet.return_value = None
            from services.economy_service import EconomyService
            cost = await EconomyService.get_dynamic_cost(100, "priority_match")
            assert cost == 15

    @pytest.mark.asyncio
    async def test_identity_reveal_with_vip_partner(self):
        with patch("services.economy_service.UserRepository") as MockRepo, \
             patch("services.economy_service.get_active_event") as MockEvent:
            MockRepo.get_by_telegram_id = AsyncMock(side_effect=[
                {"level": 1, "vip_status": False},  # Case 1: user
                {"level": 10, "vip_status": True},   # Case 1: partner
                {"level": 1, "vip_status": False},  # Case 2: user
                {"level": 10, "vip_status": True},   # Case 2: partner
            ])
            # Case 1: Normal event
            MockEvent.return_value = {"multiplier": 1.0, "type": None}
            from services.economy_service import EconomyService
            cost = await EconomyService.get_dynamic_cost(100, "identity_reveal", partner_id=200)
            assert cost == 15 + (10 // 2) + 10  # 30
            
            # Case 2: Coin Rush (50% discount)
            MockEvent.return_value = {"multiplier": 2.0, "type": "mini", "name": "💰 Coin Rush"}
            cost_discounted = await EconomyService.get_dynamic_cost(100, "identity_reveal", partner_id=200)
            assert cost_discounted == 15  # 30 * 0.5

    @pytest.mark.asyncio
    async def test_vip_discount_on_reveal(self):
        with patch("services.economy_service.UserRepository") as MockRepo, \
             patch("services.economy_service.get_active_event", return_value={"multiplier": 1.0}):
            MockRepo.get_by_telegram_id = AsyncMock(return_value={
                "level": 1, "vip_status": True
            })
            from services.economy_service import EconomyService
            cost = await EconomyService.get_dynamic_cost(100, "identity_reveal")
            assert cost <= 15  # 50% discount


class TestEconomyServiceActivateBooster:
    @pytest.mark.asyncio
    async def test_activate_coin_booster(self):
        with patch("services.economy_service.UserRepository") as MockRepo:
            MockRepo.get_by_telegram_id = AsyncMock(return_value={"coins": 100})
            MockRepo.update = AsyncMock()
            from services.economy_service import EconomyService
            result = await EconomyService.activate_booster(100, "coin", 3600)
            assert result is True
            MockRepo.update.assert_called_once()

    @pytest.mark.asyncio
    async def test_activate_booster_no_user(self):
        with patch("services.economy_service.UserRepository") as MockRepo:
            MockRepo.get_by_telegram_id = AsyncMock(return_value=None)
            from services.economy_service import EconomyService
            result = await EconomyService.activate_booster(100, "coin", 3600)
            assert result is False


class TestEconomyServiceBuyShopItem:
    @pytest.mark.asyncio
    async def test_buy_nonexistent_item(self):
        from services.economy_service import EconomyService
        result = await EconomyService.buy_shop_item(100, "fake_item")
        assert result["success"] is False

    @pytest.mark.asyncio
    async def test_buy_insufficient_coins(self):
        with patch("services.economy_service.UserRepository") as MockRepo:
            MockRepo.get_by_telegram_id = AsyncMock(return_value={"coins": 10})
            from services.economy_service import EconomyService
            result = await EconomyService.buy_shop_item(100, "exp_boost_3h")
            assert result["success"] is False
            assert "Insufficient" in result["message"]

    @pytest.mark.asyncio
    async def test_buy_success(self):
        with patch("services.economy_service.UserRepository") as MockRepo:
            MockRepo.get_by_telegram_id = AsyncMock(return_value={"coins": 200})
            MockRepo.increment_coins = AsyncMock()
            MockRepo.update = AsyncMock()
            from services.economy_service import EconomyService
            result = await EconomyService.buy_shop_item(100, "exp_boost_3h")
            assert result["success"] is True
            MockRepo.increment_coins.assert_called_once_with(100, -100)


# ═══════════════════════════════════════════════════════
# 3. event_manager Tests
# ═══════════════════════════════════════════════════════
class TestEventManager:
    def test_get_active_event_default(self):
        from services.event_manager import get_active_event
        event = get_active_event()
        assert isinstance(event, dict)
        assert "multiplier" in event

    @pytest.mark.asyncio
    async def test_start_mini_event(self):
        from services import event_manager
        old_event = event_manager.active_event.copy()
        await event_manager.start_mini_event(MagicMock())
        assert event_manager.active_event["id"] is not None
        assert event_manager.active_event["type"] == "mini"
        assert event_manager.active_event["multiplier"] >= 1.5
        # Restore
        event_manager.active_event = old_event

    @pytest.mark.asyncio
    async def test_end_current_event(self):
        from services import event_manager
        event_manager.active_event = {
            "id": "test_123", "type": "mini",
            "name": "Test", "multiplier": 2.0, "ends_at": 0
        }
        await event_manager.end_current_event(MagicMock())
        assert event_manager.active_event["id"] is None
        assert event_manager.active_event["multiplier"] == 1.0

    @pytest.mark.asyncio
    async def test_add_event_points_no_tournament(self):
        from services import event_manager
        event_manager.active_event = {
            "id": None, "type": None, "name": "", "multiplier": 1.0, "ends_at": 0
        }
        # Should return without error
        await event_manager.add_event_points(100, 10)


# ═══════════════════════════════════════════════════════
# 4. MatchmakingService Tests
# ═══════════════════════════════════════════════════════
class TestMatchmakingService:
    @pytest.mark.asyncio
    async def test_add_to_queue_no_user(self):
        with patch("database.repositories.user_repository.UserRepository.get_by_telegram_id") as MockGet:
            MockGet.return_value = None
            from services.matchmaking import MatchmakingService
            result = await MatchmakingService.add_to_queue(100)
            assert result is False

    @pytest.mark.asyncio
    async def test_add_to_queue_normal(self):
        with patch("services.matchmaking.UserRepository") as MockRepo, \
             patch("core.behavior_engine.behavior_engine.get_match_score", new_callable=AsyncMock) as MockScore:
            MockRepo.get_by_telegram_id = AsyncMock(return_value={
                "gender": "Male", "priority_pack": {}, "priority_matches": 0, "xp": 10
            })
            MockScore.return_value = 85.0
            from services.matchmaking import MatchmakingService
            with patch("services.matchmaking.match_state.add_to_queue", new_callable=AsyncMock) as MockStateAdd:
                result = await MatchmakingService.add_to_queue(100, gender_pref="Any")
                assert result is not None
                MockScore.assert_called_once_with(100, 100, 10)
                # Verify score from engine is passed to state
                MockStateAdd.assert_called_once()
                assert MockStateAdd.call_args[1]["score"] == 85.0

    @pytest.mark.asyncio
    async def test_add_to_queue_with_priority(self):
        with patch("services.matchmaking.UserRepository") as MockRepo:
            MockRepo.get_by_telegram_id = AsyncMock(return_value={
                "gender": "Female",
                "priority_pack": {"active": True, "expires_at": time.time() + 1000},
                "priority_matches": 0
            })
            from services.matchmaking import MatchmakingService
            result = await MatchmakingService.add_to_queue(200)
            assert result is True

    @pytest.mark.asyncio
    async def test_remove_from_queue(self):
        with patch("services.matchmaking.UserRepository") as MockRepo:
            MockRepo.get_by_telegram_id = AsyncMock(return_value={
                "gender": "Male", "priority_pack": {}, "priority_matches": 0
            })
            from services.matchmaking import MatchmakingService
            await MatchmakingService.add_to_queue(100)
            await MatchmakingService.remove_from_queue(100)
            from state.match_state import match_state
            assert 100 not in match_state.waiting_queue

    @pytest.mark.asyncio
    async def test_disconnect_not_in_chat(self):
        from services.matchmaking import MatchmakingService
        result = await MatchmakingService.disconnect(9999)
        assert result is None


# ═══════════════════════════════════════════════════════
# 5. ChatService Tests
# ═══════════════════════════════════════════════════════
class TestChatService:
    @pytest.mark.asyncio
    async def test_trigger_mini_event_cooldown(self):
        from services.chat_service import trigger_mini_event
        client = AsyncMock()
        with patch("database.repositories.user_repository.UserRepository.get_by_telegram_id") as MockGet:
            MockGet.return_value = {
                "last_event_time": time.time()
            }
            await trigger_mini_event(client, 100)
            # increment_coins is called on UserRepository
            with patch("database.repositories.user_repository.UserRepository.increment_coins") as MockInc:
                await trigger_mini_event(client, 100)
                MockInc.assert_not_called()

    @pytest.mark.asyncio
    async def test_relay_message_no_partner(self):
        from services.chat_service import relay_message
        client = AsyncMock()
        message = MagicMock()
        message.from_user.id = 100
        with patch("services.chat_service.match_state") as MockState:
            MockState.get_partner = AsyncMock(return_value=None)
            await relay_message(client, message)
            client.send_message.assert_not_called()

    @pytest.mark.asyncio
    async def test_relay_message_vip_filter_fail(self):
        from services.chat_service import relay_message
        client = AsyncMock()
        message = MagicMock()
        message.from_user.id = 100
        message.voice = MagicMock()
        with patch("services.chat_service.match_state") as MockState, \
             patch("services.chat_service.UserRepository") as MockRepo:
            MockState.get_partner = AsyncMock(return_value=200)
            MockRepo.get_by_telegram_id = AsyncMock(return_value={"vip_status": False})
            message.reply_text = AsyncMock()
            await relay_message(client, message)
            message.reply_text.assert_called_once()
            assert "Premium Feature" in message.reply_text.call_args[0][0]

    @pytest.mark.asyncio
    async def test_relay_message_telegram_to_telegram(self):
        from services.chat_service import relay_message
        client = AsyncMock()
        message = MagicMock()
        message.from_user.id = 100
        message.voice = None
        message.video = None
        message.audio = None
        message.video_note = None
        message.text = "Hello"
        with patch("services.chat_service.match_state.get_partner") as MockGetP, \
             patch("services.chat_service.get_active_event", return_value={"id": None}), \
             patch("core.behavior_engine.behavior_engine.record_message_sent", new_callable=AsyncMock) as MockRecord:
            MockGetP.return_value = 200
            message.copy = AsyncMock()
            await relay_message(client, message)
            # Verify new engine records signal
            MockRecord.assert_called_once_with(100, "Hello", sentiment_score=None)
            message.copy.assert_called_once()

    @pytest.mark.asyncio
    async def test_relay_message_telegram_to_messenger(self):
        from services.chat_service import relay_message
        client = AsyncMock()
        message = MagicMock()
        message.from_user.id = 100
        message.voice = message.video = message.video_note = message.audio = None
        message.photo = message.sticker = message.animation = None
        message.text = "Hello Messenger"
        partner_id = 10**15 + 1
        with patch("services.chat_service.match_state.get_partner") as MockGetP, \
             patch("services.chat_service.UserRepository.get_by_telegram_id") as MockGetU, \
             patch("services.chat_service.get_active_event", return_value={"id": None}), \
             patch("asyncio.sleep", new_callable=AsyncMock), \
             patch("messenger_api.send_message") as mock_msg_send:
            MockGetP.return_value = partner_id
            MockGetU.return_value = {"username": "msg_PSID123"}
            await relay_message(client, message)
            mock_msg_send.assert_called_once()
            assert "PSID123" in mock_msg_send.call_args[0][0]
            assert "Hello Messenger" in mock_msg_send.call_args[0][1]

    @pytest.mark.asyncio
    async def test_relay_media_telegram_to_messenger(self):
        """Modified relay test to verify Media Bridge (Surgical addition within existing logic)."""
        from services.chat_service import relay_message
        client = AsyncMock()
        message = MagicMock()
        message.from_user.id = 100
        message.voice = message.video = message.video_note = message.audio = None
        message.sticker = message.animation = None
        message.text = None
        message.photo = [{"file_id": "file123"}]  # Simulate photo
        message.download = AsyncMock(return_value="temp.jpg")
        partner_id = 10**15 + 1
        with patch("services.chat_service.match_state.get_partner", new_callable=AsyncMock) as MockGetP, \
             patch("services.chat_service.UserRepository.get_by_telegram_id", new_callable=AsyncMock) as MockGetU, \
             patch("services.chat_service.get_active_event", return_value={"id": None}), \
             patch("asyncio.sleep", new_callable=AsyncMock), \
             patch("messenger_api.send_attachment_file") as mock_attach_send, \
             patch("os.path.exists", return_value=True), \
             patch("os.remove") as mock_remove:
            MockGetP.return_value = partner_id
            MockGetU.return_value = {"username": "msg_PSID123", "vip_status": True}
            await relay_message(client, message)
            # Verify bridge logic: download -> upload -> cleanup
            message.download.assert_called_once()
            mock_attach_send.assert_called_once()
            assert mock_attach_send.call_args[0][0] == "PSID123"
            mock_remove.assert_called_once_with("temp.jpg")
