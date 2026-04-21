# ═══════════════════════════════════════════════════════════════════════
# FILE: services/matchmaker_loop.py
# PURPOSE: Background task that actively pairs users waiting in the queue.
# Without this, cross-platform matches (Telegram <-> Messenger) never fire
# because find_partner() is only called at the moment a user joins.
# ═══════════════════════════════════════════════════════════════════════

import asyncio
import time
from pyrogram import Client
from utils.logger import logger
from state.match_state import match_state
from core.engine.state_machine import UnifiedState
from services.distributed_state import distributed_state
from database.repositories.user_repository import UserRepository
from database.repositories.blocked_repository import BlockedRepository


async def start_matchmaker_loop(client: Client):
    """
    Continuously scans the waiting queue and pairs compatible users using
    a batch-processed, O(N) Redis pass to prevent O(N^2) scaling issues.
    Runs every 3 seconds.
    """
    from services.matchmaking import MatchmakingService
    logger.info("🔁 Matchmaker loop started.")

    while True:
        try:
            await asyncio.sleep(3)

            # 1. Fetch full candidate list ONCE per cycle
            candidates = await distributed_state.get_queue_candidates()
            if len(candidates) < 2:
                continue

            # 2. Batch fetch preferences before pairing loop
            user_prefs = {}
            for uid in candidates:
                user_prefs[uid] = await distributed_state.get_user_queue_data(uid)

            already_matched = set()

            # 3. Greedy pairing pass
            for i, u_id in enumerate(candidates):
                if u_id in already_matched:
                    continue

                u_data = user_prefs.get(u_id, {})
                u_gen = u_data.get("gender", "Not specified")
                u_pref = u_data.get("pref", "Any")

                for p_id in candidates[i+1:]:
                    if p_id in already_matched:
                        continue

                    p_data = user_prefs.get(p_id, {})
                    p_gen = p_data.get("gender", "Not specified")
                    p_pref = p_data.get("pref", "Any")

                    # Compatibility check
                    u_likes_p = (u_pref.lower() == "any") or (u_pref.lower() == p_gen.lower())
                    p_likes_u = (p_pref.lower() == "any") or (p_pref.lower() == u_gen.lower())

                    if u_likes_p and p_likes_u:
                        # Mutation-level check: mutally blocked?
                        # Handle string IDs safely for BlockedRepository
                        try:
                            clean_u = int(u_id[4:]) if u_id.startswith("msg_") else int(u_id)
                            clean_p = int(p_id[4:]) if p_id.startswith("msg_") else int(p_id)
                            if await BlockedRepository.is_mutually_blocked(clean_u, clean_p):
                                continue
                        except Exception as e:
                            logger.warning(f"Blocked check fallback for {u_id}-{p_id}: {e}")

                        # ATOMIC CLAIM (No local lock needed)
                        success, reason = await distributed_state.atomic_claim_match(u_id, p_id)
                        
                        if success:
                            already_matched.add(u_id)
                            already_matched.add(p_id)
                            logger.info(f"🔁 Loop matched (Batch): {u_id} <-> {p_id}")

                            # 4. Fire initialization as background task
                            asyncio.create_task(
                                MatchmakingService.initialize_match(client, u_id, p_id)
                            )
                            break  # Move to next u_id

        except Exception as e:
            logger.error(f"Matchmaker loop error: {e}")
            await asyncio.sleep(5)  # back off on error, don't spin
