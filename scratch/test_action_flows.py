
import asyncio
import os
import time
from unittest.mock import patch, MagicMock
from services.distributed_state import distributed_state
from services.matchmaking import MatchmakingService
from state.match_state import match_state, UserState
from dotenv import load_dotenv

async def test_session_flows():
    load_dotenv()
    try:
        await distributed_state.connect()
        
        if not distributed_state.redis:
            print("MISSING: Redis not connected.")
            return

        # Mock Client
        client = MagicMock()

        uA, uB = 999201, 999202
        
        print("\n[Phase 4A] Flow: MATCH -> SKIP")
        await distributed_state.force_disconnect_single(uA)
        await distributed_state.force_disconnect_single(uB)
        await distributed_state.remove_from_queue(uA)
        await distributed_state.remove_from_queue(uB)
        
        # 1. Setup: Users in queue
        await match_state.add_to_queue(uA, gender="Male", pref="Any")
        await match_state.add_to_queue(uB, gender="Female", pref="Any")
        
        # Verify 
        candidates = await distributed_state.get_queue_candidates()
        print(f"Queue candidates: {candidates} (Types: {[type(c) for c in candidates]})")
        
        uA_pref = await distributed_state.get_user_queue_data(uA)
        uB_pref = await distributed_state.get_user_queue_data(uB)
        print(f"uA pref data: {uA_pref}")
        print(f"uB pref data: {uB_pref}")

        # 2. Matchmaking with verbose interception
        # We patch BlockedRepository to ensure it doesn't block the test IDs
        with patch('database.repositories.blocked_repository.BlockedRepository.is_mutually_blocked', return_value=False):
            print(f"Attempting find_match for {uA}...")
            partner = await match_state.find_match(uA)
            print(f"Match result: {partner}")
            
            if partner is None:
                # One last check: maybe the claim failed?
                success, reason = await distributed_state.atomic_claim_match(uA, uB)
                print(f"Manual claim check for {uA}-{uB}: Success={success}, Reason={reason}")
            
            assert partner == uB
        
        # 3. Skip
        stats = await MatchmakingService.disconnect(uA)
        assert stats["partner_id"] == uB
        print("SUCCESS: SKIP flow state changes verified.")

    finally:
        for uid in [uA, uB]:
            await distributed_state.force_disconnect_single(uid)
            if distributed_state.redis:
                await distributed_state.redis.delete(f"state:{uid}", f"chat:{uid}", f"chat_start:{uid}")
        if distributed_state.redis:
             # Clean up the exact rematch key if needed
             await distributed_state.redis.delete(f"rematch:{min(uA,uB)}:{max(uA,uB)}")
             await distributed_state.redis.aclose()
        print("\nCLEANED UP test users.")

if __name__ == "__main__":
    asyncio.run(test_session_flows())
