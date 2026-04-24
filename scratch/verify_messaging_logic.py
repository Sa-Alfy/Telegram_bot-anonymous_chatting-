
import asyncio
import sys
import os

# Add the project root to sys.path
sys.path.append(os.path.abspath("f:/Code/Youn1q(4-24-26)/Telegram_bot-anonymous_chatting-"))

from unittest.mock import AsyncMock, MagicMock, patch
from core.engine.state_machine import UnifiedState
from database.repositories.user_repository import UserRepository
from utils.platform_adapter import PlatformAdapter
import app_state

async def test_messaging_flows():
    print("Starting Messaging Flow Verification...")
    
    # Mock Telegram Client
    async def mock_tg_send(chat_id, text, **kw):
        print(f"  [TELEGRAM SEND] -> {chat_id}: {text}")
        return MagicMock(id=123)
    
    mock_tg = MagicMock()
    mock_tg.send_message = AsyncMock(side_effect=mock_tg_send)
    app_state.telegram_app = mock_tg
    
    # Mock Messenger API
    mock_messenger_send = MagicMock()
    
    # Mock Redis State
    # We'll use a local dict to simulate distributed_state
    state_store = {}
    
    async def mock_get_partner(uid):
        return state_store.get(f"sm:partner:{uid}")
    
    async def mock_get_state(uid):
        return state_store.get(f"sm:state:{uid}")

    # --- Setup Pairs ---
    # TG User 1001 <-> Messenger User psid_c (Virtual ID: 10^15 + 1)
    tg_id = 1001
    msg_psid = "psid_c"
    msg_uid = f"msg_{msg_psid}"
    msg_vid = UserRepository._sanitize_id(msg_uid)
    
    state_store[f"sm:partner:{tg_id}"] = msg_uid
    state_store[f"sm:partner:{msg_vid}"] = str(tg_id)
    state_store[f"sm:partner:{msg_uid}"] = str(tg_id) # For good measure
    
    state_store[f"sm:state:{tg_id}"] = "CHAT_ACTIVE"
    state_store[f"sm:state:{msg_uid}"] = "CHAT_ACTIVE"
    state_store[f"sm:state:{msg_vid}"] = "CHAT_ACTIVE"

    # Mock Database
    async def mock_repo_get(vid):
        return {"telegram_id": vid, "username": f"user_{vid}"}
    
    async def mock_repo_update(vid, **kw): return True
    
    with patch("services.distributed_state.distributed_state.get_partner", side_effect=mock_get_partner), \
         patch("services.distributed_state.distributed_state.get_user_state", side_effect=mock_get_state), \
         patch("database.repositories.user_repository.UserRepository.get_by_telegram_id", side_effect=mock_repo_get), \
         patch("database.repositories.user_repository.UserRepository.update", side_effect=mock_repo_update), \
         patch("messenger_api.send_message", side_effect=lambda psid, text: print(f"  [MESSENGER SEND] -> {psid}: {text}")), \
         patch("messenger_api.send_quick_replies", side_effect=lambda psid, text, buttons: print(f"  [MESSENGER QR] -> {psid}: {text}")):

        # Test TG -> MSG
        print(f"\nScenario: Telegram ({tg_id}) -> Messenger ({msg_uid})")
        # In ActionRouter, SEND_MESSAGE logic does:
        partner_id = await mock_get_partner(tg_id)
        print(f"  ActionRouter found partner: {partner_id}")
        await PlatformAdapter.send_cross_platform(mock_tg, partner_id, "hi from tg")
        
        # Test MSG -> TG
        print(f"\nScenario: Messenger ({msg_uid}) -> Telegram ({tg_id})")
        # Sender ID is msg_uid
        c_uid = UserRepository._sanitize_id(msg_uid)
        partner_id = await mock_get_partner(c_uid)
        print(f"  ActionRouter found partner for {c_uid}: {partner_id}")
        await PlatformAdapter.send_cross_platform(mock_tg, partner_id, "hi from messenger")
        
        # Test MSG -> MSG
        msg_psid_d = "psid_d"
        msg_uid_d = f"msg_{msg_psid_d}"
        msg_vid_d = UserRepository._sanitize_id(msg_uid_d)
        
        state_store[f"sm:partner:{msg_vid}"] = msg_uid_d
        state_store[f"sm:partner:{msg_vid_d}"] = msg_uid
        
        print(f"\nScenario: Messenger ({msg_uid}) -> Messenger ({msg_uid_d})")
        partner_id = await mock_get_partner(msg_vid)
        print(f"  ActionRouter found partner for {msg_vid}: {partner_id}")
        await PlatformAdapter.send_cross_platform(mock_tg, partner_id, "hello peer")

if __name__ == "__main__":
    asyncio.run(test_messaging_flows())
