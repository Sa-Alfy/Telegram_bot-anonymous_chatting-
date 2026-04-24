import asyncio
import os
import sys
from dotenv import load_dotenv

# Load .env early
load_dotenv()

# Mocking app_state
class MockAppState:
    def __init__(self):
        self.engine = None
        self.tg_adapter = None
        self.msg_adapter = None
sys.modules['app_state'] = MockAppState()

from core.engine.actions import ActionRouter
from database.connection import db
from services.distributed_state import distributed_state
from state.match_state import match_state

async def test_social_unification():
    print("--- Final Social Unification Test ---", flush=True)
    
    msg_uid = "msg_26642135455381080"
    tg_uid = "8763437543"
    
    # Setup: Create a match in Redis
    await match_state.set_user_state(msg_uid, "CHAT_ACTIVE")
    await match_state.set_user_state(tg_uid, "CHAT_ACTIVE")
    await match_state.set_partner(msg_uid, tg_uid)
    await match_state.set_partner(tg_uid, msg_uid)
    
    # Test 1: SHOW_GIFTS for Messenger User
    print("\n[TEST 1] SHOW_GIFTS (Messenger)...")
    res_gifts = await ActionRouter.process_event({
        "event_type": "SHOW_GIFTS",
        "user_id": msg_uid,
        "payload": {},
        "timestamp": 123456789
    })
    print(f"Result: {res_gifts['success']}")
    if res_gifts['success']:
        print(f"PASS: Found {len(res_gifts['reply_markup'])} gift buttons.")
    else:
        print(f"FAIL: {res_gifts.get('error')}")

    # Test 2: SUBMIT_REACTION (Telegram -> Messenger)
    print("\n[TEST 2] SUBMIT_REACTION (TG -> MSG)...")
    res_react = await ActionRouter.process_event({
        "event_type": "SUBMIT_REACTION",
        "user_id": tg_uid,
        "payload": {"value": "🔥"},
        "timestamp": 123456790
    })
    print(f"Result: {res_react['success']}")
    if res_react['success']:
        target = res_react['notify_partner']['user_id']
        print(f"PASS: Reaction routed to partner: {target}")
        if target == msg_uid:
            print("PASS: Correctly identified Messenger partner with msg_ prefix!")
    else:
        print(f"FAIL: {res_react.get('error')}")

    # Test 3: SHOW_TOOLS (Messenger)
    print("\n[TEST 3] SHOW_TOOLS (Messenger)...")
    res_tools = await ActionRouter.process_event({
        "event_type": "SHOW_TOOLS",
        "user_id": msg_uid,
        "payload": {},
        "timestamp": 123456791
    })
    print(f"Result: {res_tools['success']}")
    if res_tools['success']:
        print(f"PASS: Tools menu generated: {[b['title'] for b in res_tools['reply_markup']]}")

async def main():
    try:
        await distributed_state.connect()
        await db.connect()
        await test_social_unification()
    finally:
        # Cleanup
        if distributed_state.redis:
            await distributed_state.redis.delete(f"sm:state:{msg_uid}")
            await distributed_state.redis.delete(f"sm:state:{tg_uid}")
            await distributed_state.redis.delete(f"sm:partner:{msg_uid}")
            await distributed_state.redis.delete(f"sm:partner:{tg_uid}")
        if db.is_connected:
            await db.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
