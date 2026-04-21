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
from utils.ui_formatters import get_match_found_text
from utils.helpers import update_user_ui
from utils.keyboard import chat_menu
from database.repositories.user_repository import UserRepository


async def start_matchmaker_loop(client: Client):
    """
    Continuously scans the waiting queue and pairs compatible users.
    Runs every 3 seconds. This is the engine that makes cross-platform
    matching work.
    """
    from services.matchmaking import MatchmakingService
    logger.info("🔁 Matchmaker loop started.")

    while True:
        try:
            await asyncio.sleep(3)

            candidates = await distributed_state.get_queue_candidates()
            if len(candidates) < 2:
                continue

            already_matched = set()

            for user_id in candidates:
                if user_id in already_matched:
                    continue

                # Try to find and claim a match for this user
                partner_id = await match_state.find_match(user_id)

                if partner_id:
                    already_matched.add(user_id)
                    already_matched.add(partner_id)
                    logger.info(
                        f"🔁 Loop matched: {user_id} <-> {partner_id}"
                    )

                    # Standardized match setup (Rewards, DB, UI)
                    # We fire this as a task so the loop can keep going
                    asyncio.create_task(
                        MatchmakingService.initialize_match(client, user_id, partner_id)
                    )

        except Exception as e:
            logger.error(f"Matchmaker loop error: {e}")
            await asyncio.sleep(5)


        except Exception as e:
            logger.error(f"Matchmaker loop error: {e}")
            await asyncio.sleep(5)  # back off on error, don't spin
