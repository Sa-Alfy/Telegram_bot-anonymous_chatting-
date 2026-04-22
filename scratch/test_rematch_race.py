
import asyncio
import os
import time
from services.distributed_state import distributed_state
from state.match_state import match_state, UserState
from database.connection import db
from dotenv import load_dotenv

async def test_rematch_race():
    load_dotenv()
    try:
        await distributed_state.connect()
        await db.connect() # Required for handle_rematch logic if called (but we'll test state layer)
        
        if not distributed_state.redis:
            print("MISSING: Redis not connected.")
            return

        uA, uB, uC = 999301, 999302, 999303
        
        # Ensure clean state
        for u in [uA, uB, uC]:
            await distributed_state.force_disconnect_single(u)
            await distributed_state.remove_from_queue(u)

        print("\n[Race 1] Triple Race: A/B Rematch vs C Queue Match")
        # 1. A and B intend to Rematch
        # 2. C enters queue to find A
        from state.match_state import match_state
        await match_state.add_to_queue(uC, gender="Female", pref="Any")
        
        # Concurrent clicks
        print("Simulating concurrent Rematch(A,B) and FindMatch(C)...")
        # Workers:
        # W1: A clicks rematch B
        # W2: B clicks rematch A
        # W3: C's loop finds A
        
        # We need to simulate the exact order where A clicks first, then C tries, then B clicks.
        # But in a true race, we just gather them.
        
        async def worker_rematch(uid, target):
            return await match_state.set_rematch(uid, target)
            
        async def worker_find(uid):
            return await match_state.find_match(uid)

        # TRIGGER
        results = await asyncio.gather(
            worker_rematch(uA, uB),
            worker_find(uC),
            worker_rematch(uB, uA)
        )
        
        # Results[0] (A) -> should be (False, 2) [Wait]
        # Results[2] (B) -> should be (True, 1) [Success]
        # Results[1] (C) -> should be None or fail to claim A because A is already matched or busy
        
        print(f"Results: A={results[0]}, C_find={results[1]}, B={results[2]}")
        
        # Invariants
        stateA = await distributed_state.get_user_state(uA)
        stateB = await distributed_state.get_user_state(uB)
        stateC = await distributed_state.get_user_state(uC)
        partnerA = await distributed_state.get_partner(uA)
        partnerB = await distributed_state.get_partner(uB)
        
        print(f"Final States: A={stateA}, B={stateB}, C={stateC}")
        print(f"Partners: A={partnerA}, B={partnerB}")
        
        assert stateA == "CHATTING"
        assert stateB == "CHATTING"
        assert partnerA == uB
        assert partnerB == uA
        assert stateC != "CHATTING" or partnerA != uC # C should not have hijacked A
        print("SUCCESS: Triple race invariant maintained.")

        print("\n[Race 2] Spam Test (Double Click)")
        await distributed_state.force_disconnect_single(uA)
        await distributed_state.force_disconnect_single(uB)
        
        # A clicks 5 times rapidly
        spam_results = await asyncio.gather(*[worker_rematch(uA, uB) for _ in range(5)])
        print(f"Spam results: {spam_results}")
        # All should be (False, 2) - WAITING
        assert all(r == (False, 2) for r in spam_results)
        print("SUCCESS: Spam double-click handled.")

        print("\n[Race 3] Expiry Boundary")
        # 1. A clicks
        await worker_rematch(uA, uB)
        rkey = f"rematch:{min(uA,uB)}:{max(uA,uB)}"
        # 2. Artificially expire the key
        await distributed_state.redis.delete(rkey)
        print("Rematch key expired/deleted...")
        # 3. B clicks
        resB = await worker_rematch(uB, uA)
        print(f"B result after expiry: {resB}")
        # Should be (False, 2) - B is now the "First" as A's intent expired
        assert resB == (False, 2)
        print("SUCCESS: Expiry boundary handled.")

    finally:
        for u in [uA, uB, uC]:
            await distributed_state.force_disconnect_single(u)
        await distributed_state.redis.aclose()
        await db.close()

if __name__ == "__main__":
    asyncio.run(test_rematch_race())
