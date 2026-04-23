import pytest
import asyncio
from unittest.mock import patch, MagicMock
from services.economy_service import EconomyService
from database.repositories.user_repository import UserRepository
from database.repositories.gift_repository import GiftRepository
from core.engine.actions import ActionRouter
import time

@pytest.fixture
def mock_db():
    with patch("database.connection.db") as mock:
        yield mock

@pytest.mark.asyncio
async def test_send_gift_insufficient_coins():
    with patch("services.economy_service.UserRepository.get_by_telegram_id") as mock_get_user:
        mock_get_user.return_value = {"coins": 5} # Rose costs 10
        
        result = await EconomyService.send_gift(100, 200, "rose")
        assert result["success"] == False
        assert "Insufficient" in result["message"]

@pytest.mark.asyncio
async def test_send_gift_rose_success():
    with patch("services.economy_service.UserRepository.get_by_telegram_id") as mock_get_user, \
         patch("services.economy_service.UserService.deduct_coins") as mock_deduct, \
         patch("services.economy_service.UserRepository.update") as mock_update, \
         patch("database.repositories.gift_repository.GiftRepository.log_gift") as mock_log:
         
        # Mock sender and receiver
        mock_get_user.side_effect = [
            {"coins": 50, "generosity": 0}, # Sender
            {"karma": 5} # Receiver
        ]
        mock_deduct.return_value = True
        
        result = await EconomyService.send_gift(100, 200, "rose")
        
        assert result["success"] == True
        mock_deduct.assert_called_with(100, 10)
        mock_log.assert_called_with(100, 200, "rose", 10)
        
        # Check karma was updated for receiver (second update call usually)
        update_calls = mock_update.call_args_list
        assert any(call[1].get("karma") == 6 for call in update_calls)
        # Check generosity updated for sender
        assert any(call[1].get("generosity") == 10 for call in update_calls)

@pytest.mark.asyncio
async def test_send_gift_diamond_boost():
    with patch("services.economy_service.UserRepository.get_by_telegram_id") as mock_get_user, \
         patch("services.economy_service.UserService.deduct_coins") as mock_deduct, \
         patch("database.repositories.gift_repository.GiftRepository.log_gift") as mock_log, \
         patch("services.economy_service.EconomyService.activate_booster") as mock_boost, \
         patch("services.economy_service.UserRepository.update") as mock_update:
         
        mock_get_user.return_value = {"coins": 500, "generosity": 0}
        mock_deduct.return_value = True
        
        result = await EconomyService.send_gift(100, 200, "diamond")
        
        assert result["success"] == True
        # Diamond triggers 2x XP (3600s) for both users
        assert mock_boost.call_count == 2
        
@pytest.mark.asyncio
async def test_send_gift_treasure_reveal():
    with patch("services.economy_service.UserRepository.get_by_telegram_id") as mock_get_user, \
         patch("services.economy_service.UserService.deduct_coins") as mock_deduct, \
         patch("database.repositories.gift_repository.GiftRepository.log_gift") as mock_log, \
         patch("services.economy_service.EconomyService.activate_booster") as mock_boost, \
         patch("services.economy_service.UserRepository.update") as mock_update, \
         patch("database.repositories.reveal_repository.RevealRepository.log_reveal") as mock_reveal:
         
        mock_get_user.side_effect = [
            {"coins": 1000, "generosity": 0}, # Sender
            {"bio": "I love cats", "location": "London"} # Receiver
        ]
        mock_deduct.return_value = True
        
        result = await EconomyService.send_gift(100, 200, "treasure")
        
        assert result["success"] == True
        assert result["reveal_data"]["bio"] == "I love cats"
        assert result["reveal_data"]["location"] == "London"
        
        # Treasure triggers 2x Coins (10800s)
        assert mock_boost.call_count == 2
        assert mock_reveal.called

@pytest.mark.asyncio
async def test_engine_send_gift_event():
    with patch("handlers.actions.social.SocialHandler.handle_send_gift") as mock_handle:
        mock_handle.return_value = {"text": "✅ Gift Sent!"}
        
        event = {
            "event_type": "SEND_GIFT",
            "user_id": 100,
            "payload": {"gift_key": "rose"}
        }
        
        # Mock redis with AsyncMock
        from services.distributed_state import distributed_state
        from unittest.mock import AsyncMock
        distributed_state.redis = MagicMock()
        distributed_state.redis.exists = AsyncMock(return_value=False)
        distributed_state.redis.setex = AsyncMock(return_value=True)
        distributed_state.redis.publish = AsyncMock(return_value=1)
        distributed_state.redis.xadd = AsyncMock(return_value=True)
        distributed_state.redis.get = AsyncMock(return_value=None)
        distributed_state.redis.set = AsyncMock(return_value=True)
        
        result = await ActionRouter.process_event(event)



        
        assert result["success"] == True
        assert mock_handle.called

