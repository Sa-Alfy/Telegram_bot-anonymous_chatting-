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
from state.match_state import match_state, UserState
from services.distributed_state import distributed_state
from utils.ui_formatters import get_match_found_text
from utils.helpers import update_user_ui
from utils.keyboard import chat_menu
from database.repositories.user_repository import UserRepository


async def _notify_matched_user(client: Client, user_id: int, partner_id: int):
    """Send match-found notification to one user on their correct platform."""
    try:
        now = time.time()
        user = await UserRepository.get_by_telegram_id(user_id)
        if not user:
            return

        last_safety = user.get("safety_last_seen", 0)
        show_safety = (now - last_safety > 86400)
        if show_safety:
            asyncio.create_task(
                UserRepository.update(user_id, safety_last_seen=int(now))
            )

        match_text = get_match_found_text(include_safety=show_safety)

        if user_id >= 10**15:
            # Messenger user
            username = user.get("username", "")
            if username.startswith("msg_"):
                psid = username[4:]
                from messenger_api import send_quick_replies
                from messenger.ui import get_chat_menu_buttons
                buttons = get_chat_menu_buttons(UserState.CHATTING)
                send_quick_replies(psid, match_text, buttons)
        else:
            # Telegram user
            await update_user_ui(client, user_id, match_text, chat_menu())

    except Exception as e:
        logger.error(f"Match notification failed for {user_id}: {e}")


async def start_matchmaker_loop(client: Client):
    """
    Continuously scans the waiting queue and pairs compatible users.
    Runs every 3 seconds. This is the engine that makes cross-platform
    matching work — without it, Telegram and Messenger users sitting in
    the queue never find each other.
    """
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

                    # Notify both users concurrently
                    await asyncio.gather(
                        _notify_matched_user(client, user_id, partner_id),
                        _notify_matched_user(client, partner_id, user_id),
                        return_exceptions=True
                    )

        except Exception as e:
            logger.error(f"Matchmaker loop error: {e}")
            await asyncio.sleep(5)  # back off on error, don't spin
