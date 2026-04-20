
import asyncio
import os
import time
import uuid
from typing import List
import redis.asyncio as redis
from dotenv import load_dotenv

# Import the scripts directly from our target file to ensure we test EXACTLY what is in prod
from services.distributed_state import DistributedState

async def test_lua_scripts():
    load_dotenv()
    redis_url = os.getenv("REDIS_URL")
    if not redis_url:
        print("MISSING: REDIS_URL not found.")
        return

    client = redis.from_url(redis_url, decode_responses=True)
    print(f"CONNECTED to Redis: {redis_url}")

    ds = DistributedState()
    
    # Prefix for all test keys
    T = f"test:{uuid.uuid4().hex[:8]}"
    
    def K(key): return f"{T}:{key}"

    print(f"Using test prefix: {T}")

    try:
        # -- Test 1: CLAIM_AND_INITIALIZE (Normal) --
        print("\n[Case 1A] CLAIM_AND_INITIALIZE (Normal)")
        uA, uB = 111, 222
        keys = [K(f"state:{uA}"), K(f"state:{uB}"), K(f"chat:{uA}"), K(f"chat:{uB}"), K(f"start:{uA}"), K(f"start:{uB}"), K("queue")]
        
        # Setup: Add to queue
        await client.rpush(K("queue"), uA, uB)
        
        res = await client.eval(ds._CLAIM_AND_INITIALIZE_LUA, len(keys), *keys, uA, uB, str(time.time()))
        print(f"Result: {res}")
        
        # Verify state
        assert res[0] == 1
        assert await client.get(K(f"state:{uA}")) == "CHATTING"
        assert await client.get(K(f"chat:{uA}")) == "222"
        assert await client.llen(K("queue")) == 0
        print("SUCCESS")

        # -- Test 1B: CLAIM_AND_INITIALIZE (Conflict: Already Chatting) --
        print("\n[Case 1B] CLAIM_AND_INITIALIZE (Conflict)")
        res = await client.eval(ds._CLAIM_AND_INITIALIZE_LUA, len(keys), *keys, uA, 333, str(time.time()))
        print(f"Result: {res}")
        assert res[0] == 0
        assert res[1] == "USER_A_BUSY"
        print("SUCCESS (Protected)")

        # -- Test 2A: ATOMIC_DISCONNECT (Normal) --
        print("\n[Case 2A] ATOMIC_DISCONNECT (Normal)")
        res = await client.eval(ds._ATOMIC_DISCONNECT_LUA, 6, *keys[:6], uA, uB)
        print(f"Result: {res}")
        assert res[0] == 1
        assert await client.get(K(f"state:{uA}")) == "HOME"
        assert await client.get(K(f"chat:{uA}")) is None
        print("SUCCESS")

        # -- Test 2B: ATOMIC_DISCONNECT (Idempotency) --
        print("\n[Case 2B] ATOMIC_DISCONNECT (Idempotency)")
        res = await client.eval(ds._ATOMIC_DISCONNECT_LUA, 6, *keys[:6], uA, uB)
        print(f"Result: {res}")
        assert res[0] == 1
        print("SUCCESS")

        # -- Test 3: VALIDATE_SESSION (Corruption Detection) --
        print("\n[Case 3] VALIDATE_SESSION (Ghost Recovery)")
        # Simulate corruption: User A is CHATTING but has no partner
        await client.set(K(f"state:{uA}"), "CHATTING")
        await client.delete(K(f"chat:{uA}"))
        
        v_keys = [K(f"state:{uA}"), K(f"state:{uB}"), K(f"chat:{uA}"), K(f"chat:{uB}")]
        res = await client.eval(ds._VALIDATE_SESSION_LUA, len(v_keys), *v_keys, uA, uB)
        print(f"Result: {res}")
        assert res[0] == 0
        assert res[1] == "A_INVALID_PARTNER"
        print("SUCCESS (Detection Verified)")

    finally:
        # Cleanup
        all_keys = await client.keys(f"{T}:*")
        if all_keys:
            await client.delete(*all_keys)
        await client.aclose()
        print(f"\nCLEANED UP {len(all_keys)} test keys.")

if __name__ == "__main__":
    asyncio.run(test_lua_scripts())
