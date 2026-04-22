# scratch/verify_unified_arch.py

import asyncio
import time
import os
from dotenv import load_dotenv

# Load environment variables from .env
load_dotenv()
from core.engine.actions import ActionRouter
from core.engine.state_machine import UnifiedState
from services.distributed_state import distributed_state

async def test_hard_voting_gate():
    print("Testing Hard Voting Gate...")
    user_id = "test_user_123"
    match_id = "match_abc"
    
    # 1. Manually set to CHAT_ACTIVE
    from services.distributed_state import distributed_state as ds
    await ds.connect()
    redis = ds.redis
    if not redis:
        print("Error: Could not connect to Redis. Check REDIS_URL.")
        return

    print("Connected to Redis. Resetting test user states...")
    await redis.set(f"sm:state:{user_id}", UnifiedState.CHAT_ACTIVE)

    await redis.set(f"sm:partner:{user_id}", "partner_456")
    await redis.set(f"sm:partner:partner_456", user_id)
    await redis.set(f"sm:state:partner_456", UnifiedState.CHAT_ACTIVE)

    # 2. End Chat -> Should force VOTING
    print("Action: END_CHAT")
    res = await ActionRouter.process_event({
        "event_type": "END_CHAT",
        "user_id": user_id,
        "match_id": match_id,
        "timestamp": int(time.time()),
        "payload": {}
    })
    print(f"Result: {res}")
    
    state = await redis.get(f"sm:state:{user_id}")
    print(f"State after END_CHAT: {state}")
    assert state == UnifiedState.VOTING

    # 3. Try to START_SEARCH -> Should FAIL (Hard Gate)
    print("Action: START_SEARCH (Should Fail)")
    res = await ActionRouter.process_event({
        "event_type": "START_SEARCH",
        "user_id": user_id,
        "timestamp": int(time.time())
    })
    print(f"Result: {res}")
    # The Lua script START_SEARCH checks if current == HOME. 
    # Since it's VOTING, it should return INVALID_STATE.
    
    state = await redis.get(f"sm:state:{user_id}")
    print(f"State after illegal search attempt: {state}")
    assert state == UnifiedState.VOTING

    # 4. Try to NEXT_MATCH -> Should FAIL (VOTING_INCOMPLETE)
    print("Action: NEXT_MATCH (Should Fail)")
    res = await ActionRouter.process_event({
        "event_type": "NEXT_MATCH",
        "user_id": user_id,
        "match_id": match_id,
        "timestamp": int(time.time())
    })
    print(f"Result: {res}")
    assert res.get("error") == "VOTING_INCOMPLETE"

    # 5. Submit Signal 1: Reputation
    print("Action: SUBMIT_VOTE (Reputation)")
    await ActionRouter.process_event({
        "event_type": "SUBMIT_VOTE",
        "user_id": user_id,
        "match_id": match_id,
        "payload": {"type": "reputation", "value": "good"}
    })
    state = await redis.get(f"sm:state:{user_id}")
    print(f"State after 1st vote: {state}")
    assert state == UnifiedState.VOTING

    # 6. Submit Signal 2: Identity -> Should open gate to HOME
    print("Action: SUBMIT_VOTE (Identity)")
    await ActionRouter.process_event({
        "event_type": "SUBMIT_VOTE",
        "user_id": user_id,
        "match_id": match_id,
        "payload": {"type": "identity", "value": "male"}
    })
    state = await redis.get(f"sm:state:{user_id}")
    print(f"State after 2nd vote: {state}")
    assert state == UnifiedState.HOME

    print("Verification script: Hard Voting Gate Test Passed!")


if __name__ == "__main__":
    asyncio.run(test_hard_voting_gate())
