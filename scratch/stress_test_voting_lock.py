# scratch/stress_test_voting_lock.py

import asyncio
import time
from core.engine.actions import ActionRouter
from core.engine.state_machine import UnifiedState
from services.distributed_state import distributed_state

async def stress_test_voting_lock():
    print("Stress Testing Atomic Voting Lock & Versions...")

    user_id = "stress_user_999"
    match_id = "stress_match_777"
    
    from services.distributed_state import distributed_state as ds
    await ds.connect()
    redis = ds.redis
    if not redis:
        print("Redis connection failed.")
        return

    # Mock Adapters for rehydration flow
    import app_state
    class MockAdapter:
        async def render_state(self, *args, **kwargs): return True
    app_state.msg_adapter = MockAdapter()
    app_state.tg_adapter = MockAdapter()

    print("Connected to Redis. Resetting test user states...")
    # Setup: User in VOTING state with a partner
    await redis.set(f"sm:state:{user_id}", UnifiedState.VOTING)
    await redis.set(f"sm:partner:{user_id}", "partner_888")
    await redis.set(f"sm:ver:m:{match_id}", "10")
    await redis.delete(f"sm:vote:{match_id}:{user_id}")
    await redis.delete(f"sm:lock:vote:{match_id}")

    # Define concurrent tasks
    async def submit_vote(vtype, value):
        return await ActionRouter.process_event({
            "event_type": "SUBMIT_VOTE",
            "user_id": user_id,
            "match_id": match_id,
            "payload": {"type": vtype, "value": value}
        })

    async def trigger_timeout():
        return await ActionRouter.process_event({
            "event_type": "TIMEOUT_VOTING",
            "user_id": user_id,
            "match_id": match_id
        })

    print("Simulating 3 simultaneous events: Reputation, Identity, and Timeout...")
    # These should all try to acquire the same match lock
    results = await asyncio.gather(
        submit_vote("reputation", "good"),
        submit_vote("identity", "male"),
        trigger_timeout()
    )

    for i, res in enumerate(results):
        print(f"Task {i} Result: {res}")

    # Verification:
    # 1. State should be HOME (if both votes won) or HOME (if timeout won)
    # 2. Version should have incremented correctly
    # 3. Exactly one type of transition should have happened (or sequence)
    
    final_state = await redis.get(f"sm:state:{user_id}")
    final_ver = await redis.get(f"sm:ver:m:{match_id}")
    print(f"Final State: {final_state}")
    print(f"Final Version: {final_ver}")
    
    # Audit Log verification
    audit_log = await redis.lrange(f"sm:audit_log:{match_id}", 0, -1)
    print(f"Audit Log (subset): {audit_log}")

    print("Stress Test: Checks Complete.")

if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    asyncio.run(stress_test_voting_lock())
