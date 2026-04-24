import asyncio
import os
import sys
from dotenv import load_dotenv

# Load .env early
load_dotenv()

# Mocking app_state before imports
class MockAppState:
    def __init__(self):
        self.engine = None
        self.tg_adapter = None
        self.msg_adapter = None

sys.modules['app_state'] = MockAppState()

from core.engine.actions import ActionRouter
from database.repositories.user_repository import UserRepository
from database.connection import db
from services.distributed_state import distributed_state
from state.match_state import match_state

async def verify_id_pattern():
    print("--- Verifying Self-Sanitizing ID Pattern ---", flush=True)
    
    msg_uid = "msg_26642135455381080"
    tg_uid = "8763437543"
    
    # 1. Test UserRepository (DB)
    print("Testing UserRepository...")
    user1 = await UserRepository.get_by_telegram_id(msg_uid)
    user2 = await UserRepository.get_by_telegram_id(tg_uid)
    print(f"PASS: msg_uid resolved to DB record? {user1 is not None or 'Correct if new'}")
    
    # 2. Test MatchState (Redis)
    print("\nTesting MatchState Partner Lookup...")
    # Simulate a match stored in Redis with Raw IDs
    await match_state.set_user_state(msg_uid, "CHAT_ACTIVE")
    await match_state.set_user_state(tg_uid, "CHAT_ACTIVE")
    await match_state.set_partner(msg_uid, tg_uid)
    
    # Verify lookup using RAW ID
    partner = await match_state.get_partner(msg_uid)
    print(f"Lookup using '{msg_uid}': Found partner {partner}")
    if str(partner) == tg_uid:
        print("PASS: MatchState correctly found partner using Raw ID.")
    else:
        print(f"FAIL: MatchState returned {partner} instead of {tg_uid}")

    # 3. Test ActionRouter (Engine)
    print("\nTesting ActionRouter SEND_MESSAGE Logic...")
    # This simulates the exact scenario that was failing
    result = await ActionRouter.process_event({
        "event_type": "SEND_MESSAGE",
        "user_id": msg_uid,
        "payload": {"text": "Hello from Messenger!"},
        "timestamp": 123456789
    })
    
    print(f"Engine Success: {result['success']}")
    if not result['success']:
        print(f"FAIL: Engine error: {result.get('error')}")
    else:
        print("PASS: Engine successfully processed message for Messenger user!")

async def main():
    try:
        await distributed_state.connect()
        await db.connect()
        await verify_id_pattern()
    finally:
        # Cleanup
        if distributed_state.redis:
            await distributed_state.redis.delete("sm:state:msg_26642135455381080")
            await distributed_state.redis.delete("sm:state:8763437543")
            await distributed_state.redis.delete("sm:partner:msg_26642135455381080")
            await distributed_state.redis.delete("sm:partner:8763437543")
        if db.is_connected:
            await db.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
