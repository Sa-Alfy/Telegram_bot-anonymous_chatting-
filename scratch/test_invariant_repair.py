
import asyncio
import os
import time
from services.distributed_state import distributed_state
from dotenv import load_dotenv

async def test_invariants():
    load_dotenv()
    try:
        await distributed_state.connect()
        
        if not distributed_state.redis:
            print("MISSING: Redis not connected.")
            return

        # Use IDs in the 999xxx range
        uA, uB = 999001, 999002
        
        print("\n[Phase 3A] Scenario: state=CHATTING but no partner key")
        await distributed_state.redis.set(f"state:{uA}", "CHATTING")
        await distributed_state.redis.delete(f"chat:{uA}")
        
        val = await distributed_state.redis.get(f"state:{uA}")
        print(f"Pre-repair state A: {val}")
        
        # Run validation with repair=True
        is_valid = await distributed_state.validate_session(uA, repair=True)
        
        print(f"Validation result (is_valid): {is_valid}")
        new_state = await distributed_state.redis.get(f"state:{uA}")
        print(f"Post-repair state A: {new_state}")
        
        if is_valid is False and new_state == "HOME":
            print("SUCCESS: Detection + Force Reset verified.")
        else:
            print("FAILURE: State not repaired correctly.")

        print("\n[Phase 3B] Scenario: Partner Mismatch (Split-Brain)")
        uC = 999003
        await distributed_state.redis.set(f"state:{uA}", "CHATTING")
        await distributed_state.redis.set(f"state:{uB}", "CHATTING")
        await distributed_state.redis.set(f"chat:{uA}", str(uB))
        await distributed_state.redis.set(f"chat:{uB}", str(uC))
        
        is_valid = await distributed_state.validate_session(uA, repair=True)
        print(f"Validation result (is_valid): {is_valid}")
        
        stateA = await distributed_state.redis.get(f"state:{uA}")
        stateB = await distributed_state.redis.get(f"state:{uB}")
        print(f"Post-repair state A: {stateA}, B: {stateB}")
        
        if is_valid is False and stateA == "HOME" and stateB == "HOME":
            print("SUCCESS: Split-brain repair verified.")
        else:
            print("FAILURE: Split-brain repair failed.")

        # Cleanup
        for uid in [uA, uB, uC]:
            await distributed_state.redis.delete(f"state:{uid}", f"chat:{uid}", f"chat_start:{uid}")
        print("\nCLEANED UP test user states.")
    finally:
        if distributed_state.redis:
            await distributed_state.redis.aclose()

if __name__ == "__main__":
    asyncio.run(test_invariants())
