import asyncio
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Mock app_state early
class MockAppState:
    def __init__(self):
        self.engine = None
        self.tg_adapter = None
        self.msg_adapter = None
        self.telegram_app = MagicMock()
sys.modules['app_state'] = MockAppState()

from core.engine.actions import ActionRouter
from database.repositories.user_repository import UserRepository
from adapters.messenger.adapter import MessengerAdapter
from state.match_state import match_state, UnifiedState
from services.distributed_state import distributed_state

async def run_full_validation():
    print("Starting Full System Validation...\n")
    
    # 1. Polymorphic ID Handling Test
    print("[TEST 1] Polymorphic ID Handling")
    msg_id = "msg_26642135455381080"
    sanitized = UserRepository._sanitize_id(msg_id)
    print(f"Raw ID: {msg_id} -> Sanitized: {sanitized}")
    assert isinstance(sanitized, int), "Sanitization failed to return integer"
    print("OK: Polymorphic ID logic verified.\n")

    # 2. SHOW_GIFTS Event Validation (Engine)
    print("[TEST 2] Engine: SHOW_GIFTS")
    with patch("state.match_state.match_state.get_partner", AsyncMock(return_value="partner_123")):
        event = {
            "event_type": "SHOW_GIFTS",
            "user_id": msg_id,
            "payload": {},
            "timestamp": 123456789
        }
        # Mock Redis
        distributed_state.redis = MagicMock()
        distributed_state.redis.exists = AsyncMock(return_value=False)
        distributed_state.redis.setex = AsyncMock(return_value=True)
        distributed_state.redis.xadd = AsyncMock(return_value=True)
        distributed_state.redis.delete = AsyncMock(return_value=1)
        distributed_state.redis.set = AsyncMock(return_value=True)
        distributed_state.redis.get = AsyncMock(return_value=None)
        
        result = await ActionRouter.process_event(event)
        assert result["success"] is True, f"SHOW_GIFTS failed: {result.get('error')}"
        assert "reply_markup" in result, "No buttons returned in SHOW_GIFTS"
        print("OK: SHOW_GIFTS engine logic verified.\n")

    # 3. Messenger Adapter Translation (UI -> Engine)
    print("[TEST 3] Messenger Adapter: Translation")
    adapter = MessengerAdapter()
    # Mocking a "Gifts" button click from Messenger
    messenger_payload = {
        "sender": {"id": msg_id[4:]},
        "message": {"quick_reply": {"payload": "GIFT_MENU"}}
    }
    translated_event = await adapter.translate_event(messenger_payload)
    assert translated_event["event_type"] == "SHOW_GIFTS", f"Translation failed: {translated_event}"
    assert translated_event["user_id"] == msg_id, f"ID preservation failed: {translated_event['user_id']}"
    print("OK: Messenger translation (GIFT_MENU -> SHOW_GIFTS) verified.\n")

    # 4. Messenger Adapter Rendering (Engine -> UI)
    print("[TEST 4] Messenger Adapter: Rendering")
    # Mocking the engine result we got in Test 2
    render_payload = {
        "text": "Choose a gift!",
        "reply_markup": [{"title": "Rose", "payload": "SEND_GIFT_rose"}]
    }
    
    with patch("adapters.messenger.adapter.send_quick_replies") as mock_send:
        # We need to mock the state because render_state checks sm:last_render
        distributed_state.redis.get = AsyncMock(return_value=None)
        distributed_state.redis.set = AsyncMock(return_value=True)
        
        # Also need to mock UserRepository to avoid DB call in render_state if needed
        with patch("database.repositories.user_repository.UserRepository.get_by_telegram_id", AsyncMock(return_value={"id": 1})):
            success = await adapter.render_state(msg_id, UnifiedState.CHAT_ACTIVE, render_payload)
            
            assert success is True, "Messenger render_state failed"
            assert mock_send.called, "Messenger API was not called"
            args, kwargs = mock_send.call_args
            assert args[0] == msg_id[4:], f"Incorrect PSID sent to Messenger API: {args[0]}"
            assert "Rose" in str(args[2]), "Gifts button missing in rendered output"
            
    print("OK: Messenger rendering verified.\n")

    # 5. RECOVER Logic (Self-Healing)
    print("[TEST 5] Engine: RECOVER")
    # Test case: User is in CHAT_ACTIVE but partner is missing in Redis
    with patch("state.match_state.match_state.get_user_state", AsyncMock(return_value=UnifiedState.CHAT_ACTIVE)), \
         patch("state.match_state.match_state.get_partner", AsyncMock(return_value=None)):
        
        event_recover = {
            "event_type": "RECOVER",
            "user_id": msg_id,
            "payload": {},
            "timestamp": 123456790
        }
        
        result_recover = await ActionRouter.process_event(event_recover)
        print(f"RECOVER Result: {result_recover}")
        assert result_recover["success"] is True
        assert result_recover["state"] == UnifiedState.HOME, f"Recovery failed to reset state. Found: {result_recover['state']}"
        
    print("OK: RECOVER self-healing logic verified.\n")

    print("FULL SYSTEM VALIDATION PASSED!")

if __name__ == "__main__":
    asyncio.run(run_full_validation())
