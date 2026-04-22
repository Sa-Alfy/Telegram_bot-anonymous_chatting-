import asyncio
import os
import sys
from unittest.mock import AsyncMock, patch, MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# We need to mock database lookup for messenger PSID
mock_users = {}

async def _mock_get_user(telegram_id: int):
    return mock_users.get(telegram_id)

async def test_cross_platform_messaging():
    from handlers.chat import relay_message
    from messenger_handlers import _handle_relay_message
    from state.match_state import match_state, UserState
    from services.distributed_state import distributed_state
    
    from database.repositories.user_repository import UserRepository
    UserRepository.get_by_telegram_id = _mock_get_user

    await distributed_state.connect()

    # Create mock Telegram client
    mock_tg_client = MagicMock()
    mock_tg_client.send_message = AsyncMock()
    mock_tg_client.send_chat_action = AsyncMock()
    
    # We patch app_state to make the telegram client generically available
    import app_state
    app_state.telegram_app = mock_tg_client

    print("\n--- STANDALONE CROSS-PLATFORM RECORDING MOCKUP ---")

    # We will test 3 combinations:
    # 1. Telegram -> Telegram
    # 2. Messenger -> Telegram
    # 3. Messenger -> Messenger

    # 1. Telegram to Telegram
    u1_tg = 900101
    u2_tg = 900102
    
    mock_users[u1_tg] = {"telegram_id": u1_tg}
    mock_users[u2_tg] = {"telegram_id": u2_tg}
    
    await distributed_state.set_partner(u1_tg, u2_tg)
    await distributed_state.set_user_state(u2_tg, "CHATTING")

    tg_message = MagicMock()
    tg_message.from_user.id = u1_tg
    tg_message.text = "Hello from Telegram!"
    tg_message.voice = None
    tg_message.video = None
    tg_message.photo = None
    tg_message.video_note = None
    tg_message.audio = None
    tg_message.sticker = None
    tg_message.animation = None
    tg_message.document = None
    tg_message.caption = None
    tg_message.copy = AsyncMock()

    import asyncio
    with patch('asyncio.sleep', new_callable=AsyncMock), \
         patch('services.chat_service.get_active_event', return_value={"id": None, "type": None}), \
         patch('messenger_handlers.check_message', return_value=(True, None)):

        print("\n[Test 1: Telegram -> Telegram]")
        print(f"[{u1_tg} (TG)] sending: 'Hello from Telegram!' to [{u2_tg} (TG)]")
        await relay_message(mock_tg_client, tg_message)
        
        # Verify message was copied to u2_tg
        tg_message.copy.assert_called_with(chat_id=u2_tg)
        print("Verified: Pyrogram message.copy() called for TG partner.")

        tg_message.copy.reset_mock()


        # 2. Messenger to Telegram
        u3_msg = 1000000000000010  # Messenger ID ( >= 10**15 )
        psid3 = "123456789"
        u4_tg = 900104

        mock_users[u3_msg] = {"telegram_id": u3_msg, "username": f"msg_{psid3}"}
        mock_users[u4_tg] = {"telegram_id": u4_tg}

        await distributed_state.set_partner(u3_msg, u4_tg)
        await distributed_state.set_user_state(u4_tg, "CHATTING")

        with patch('services.user_service.UserService.increment_challenge', new_callable=AsyncMock):
            print("\n[Test 2: Messenger -> Telegram]")
            print(f"[{u3_msg} (MSG)] sending: 'Hello from Messenger!' to [{u4_tg} (TG)]")
            await _handle_relay_message(psid=psid3, virtual_id=u3_msg, text="Hello from Messenger!")
            
            # Verify mock_tg_client was used
            mock_tg_client.send_message.assert_called_with(chat_id=u4_tg, text="💬 Hello from Messenger!")
            print("Verified: Telegram app correctly relayed Messenger text.")

        mock_tg_client.send_message.reset_mock()


    # 3. Messenger to Messenger
    u5_msg = 1000000000000020
    psid5 = "987654321"

    mock_users[u5_msg] = {"telegram_id": u5_msg, "username": f"msg_{psid5}"}
    
    await distributed_state.set_partner(u3_msg, u5_msg)
    await distributed_state.set_user_state(u5_msg, "CHATTING")

    with patch('messenger_handlers.send_quick_replies') as mock_send_qr:
        with patch('services.user_service.UserService.increment_challenge', new_callable=AsyncMock):
            print("\n[Test 3: Messenger -> Messenger]")
            print(f"[{u3_msg} (MSG)] sending: 'Hey fellow FB user!' to [{u5_msg} (MSG)]")
            
            await _handle_relay_message(psid=psid3, virtual_id=u3_msg, text="Hey fellow FB user!")
            
            # Verify Messenger API was called
            # Note: _notify_user checks state, since u5_msg is CHATTING, it uses send_quick_replies
            mock_send_qr.assert_called_once()
            called_psid = mock_send_qr.call_args[0][0]
            called_text = mock_send_qr.call_args[0][1]
            
            assert called_psid == psid5
            assert "Hey fellow FB user!" in called_text
            
            print(f"Verified: Messenger API send_quick_replies called for psid {psid5}")

            
    print("\n--- ALL CROSS-PLATFORM MESSAGE RELAY TESTS PASSED ---")
    await distributed_state.redis.delete(f"chat:{u1_tg}", f"chat:{u3_msg}")

if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    
    from core.behavior_engine import behavior_engine
    behavior_engine.record_message_sent = AsyncMock()
    behavior_engine.record_message_received = AsyncMock()
    
    asyncio.run(test_cross_platform_messaging())
