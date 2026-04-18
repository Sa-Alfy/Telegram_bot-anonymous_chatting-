import asyncio
import time
from typing import Optional, Dict, Any
from pyrogram import Client

from state.match_state import match_state
from database.repositories.user_repository import UserRepository
from database.repositories.session_repository import SessionRepository
from services.user_service import UserService
from services.event_manager import get_active_event, add_event_points
from utils.logger import logger

class MatchmakingService:
    @staticmethod
    async def add_to_queue(user_id: int, gender_pref: str = "Any") -> bool:
        """Adds a user to the matchmaking queue, storing their gender and preference."""
        user = await UserRepository.get_by_telegram_id(user_id)
        if not user:
            return False
            
        # Priority logic
        priority = False
        timed_pack = user.get("priority_pack", {})
        if timed_pack.get("active") and timed_pack.get("expires_at", 0) > time.time():
            priority = True
        elif user.get("priority_matches", 0) > 0:
            priority = True
            
        user_gender = user.get("gender", "Not specified")
        
        from core.behavior_engine import behavior_engine
        base_reputation = 100 - (user.get("reports", 0) * 10)
        user_xp = user.get("xp", 0)
        match_score = await behavior_engine.get_match_score(user_id, base_reputation, user_xp)
        
        success = await match_state.add_to_queue(
            user_id, 
            priority=priority, 
            gender=user_gender, 
            pref=gender_pref,
            score=match_score
        )
        return success

    @staticmethod
    async def find_partner(client: Client, user_id: int) -> Optional[int]:
        """Attempts to match the user with another person in the queue.
        Note: If found, you MUST call initialize_match to set up UI/Rewards.
        """
        return await match_state.find_match(user_id)

    @staticmethod
    async def initialize_match(client: Client, user1_id: int, user2_id: int):
        """Standardized match setup: Rewards, DB updates, Behavior tracking, and Platform UI."""
        from services.user_service import UserService
        from database.repositories.user_repository import UserRepository
        from utils.ui_formatters import get_match_found_text
        from utils.helpers import update_user_ui
        from utils.keyboard import chat_menu, persistent_chat_menu
        from core.behavior_engine import behavior_engine
        from state.match_state import UserState
        import time

        uids = [user1_id, user2_id]
        now = time.time()

        # 1. DB & Reward Updates
        try:
            for uid in uids:
                await UserService.add_coins(uid, 2)
                user = await UserRepository.get_by_telegram_id(uid)
                if user:
                    matches = (user.get("total_matches") or 0) + 1
                    await UserRepository.update(uid, total_matches=matches)
                    await UserService.increment_challenge(uid, "matches_completed")
                    await behavior_engine.record_session_start(uid)
        except Exception as e:
            logger.error(f"Post-match DB updates failed for {user1_id}-{user2_id}: {e}")

        # 2. Platform-Specific Notifications
        for i, uid in enumerate(uids):
            partner_id = uids[1-i]
            try:
                user = await UserRepository.get_by_telegram_id(uid)
                if not user: continue

                # Safety warning logic
                last_safety = user.get("safety_last_seen", 0)
                show_safety = (now - last_safety > 86400)
                if show_safety:
                    asyncio.create_task(UserRepository.update(uid, safety_last_seen=int(now)))
                
                match_text = get_match_found_text(include_safety=show_safety)

                if uid >= 10**15:
                    # Messenger Path
                    from messenger_api import send_quick_replies
                    from messenger.ui import get_chat_menu_buttons
                    buttons = get_chat_menu_buttons(UserState.CHATTING)
                    psid = user.get("username", "")[4:] if user.get("username", "").startswith("msg_") else None
                    if psid:
                        send_quick_replies(psid, match_text, buttons)
                        # Optional: Send contextual hint
                        hint = await behavior_engine.get_contextual_hint(uid, "connected")
                        if hint: from messenger_api import send_message; send_message(psid, f"💡 {hint}")
                else:
                    # Telegram Path
                    # Send persistent keyboard first so it's ready
                    await client.send_message(uid, "🎮 **Match controls ready.**", reply_markup=persistent_chat_menu())
                    # Send inline match notification
                    await update_user_ui(client, uid, match_text, chat_menu(UserState.CHATTING, partner_id))

            except Exception as e:
                logger.error(f"Notification failed for {uid} in match {user1_id}-{user2_id}: {e}")

        logger.info(f"📡 Match Initialized: {user1_id} <-> {user2_id}")


    @staticmethod
    async def disconnect(user_id: int) -> Optional[Dict[str, Any]]:
        """Ends a chat session and calculates rewards."""
        result = await match_state.disconnect(user_id)
        if not result:
            return None
            
        from core.behavior_engine import behavior_engine
        await behavior_engine.record_disconnect(user_id)
            
        partner_id, duration_seconds = result
        duration_minutes = duration_seconds // 60
        
        # Base rewards
        match_reward = 5
        time_reward = duration_minutes * 2
        xp_reward = max(2, duration_minutes * 2)
        
        # Event multipliers
        active_event = get_active_event()
        event_mult = active_event.get("multiplier", 1.0)
        
        # Behavior multipliers
        u1_b_mult = await behavior_engine.get_reward_multiplier(user_id)
        u2_b_mult = await behavior_engine.get_reward_multiplier(partner_id)
        
        # User 1 specific (the one who initiated disconnect)
        u1 = await UserRepository.get_by_telegram_id(user_id)
        if not u1:
            logger.warning(f"Disconnect failed: User {user_id} not found in DB.")
            return None
            
        u1_coins = int(time_reward * event_mult * u1_b_mult)
        if u1.get("coin_booster", {}).get("active"): u1_coins *= 2
        await UserService.add_coins(user_id, match_reward + u1_coins)
        u1_levelup = await UserService.add_xp(user_id, int(xp_reward * event_mult * u1_b_mult))
        
        # User 2 specific — initialise before the if block to avoid NameError
        u2_levelup = None
        u2_coins = int(time_reward * event_mult * u2_b_mult)
        u2 = await UserRepository.get_by_telegram_id(partner_id)
        if u2:
            if u2.get("coin_booster", {}).get("active"): u2_coins *= 2
            await UserService.add_coins(partner_id, match_reward + u2_coins)
            u2_levelup = await UserService.add_xp(partner_id, int(xp_reward * event_mult * u2_b_mult))
            
            # C12: Use atomic create_and_end to prevent orphaned sessions on crash
            await SessionRepository.create_and_end(
                user_id, partner_id, duration_seconds,
                match_reward + u1_coins, match_reward + u2_coins,
                int(xp_reward * event_mult * u1_b_mult), int(xp_reward * event_mult * u2_b_mult)
            )
            # Save last partner so rematch works
            await UserRepository.update(user_id, last_partner_id=partner_id)
            await UserRepository.update(partner_id, last_partner_id=user_id)
        
        # Challenge updates
        # (Assuming messages_sent is tracked elsewhere in message handlers)
        
        return {
            "user_id": user_id,
            "partner_id": partner_id,
            "duration_seconds": duration_seconds,
            "duration_minutes": duration_minutes,
            "coins_earned": match_reward + u1_coins,
            "xp_earned": int(xp_reward * event_mult * u1_b_mult),
            "u2_coins_earned": match_reward + u2_coins,
            "u2_xp_earned": int(xp_reward * event_mult * u2_b_mult),
            "u1_levelup": u1_levelup,
            "u2_levelup": u2_levelup,
            "total_matches": u1.get("total_matches", 0)
        }

    @staticmethod
    async def remove_from_queue(user_id: int):
        await match_state.remove_from_queue(user_id)

    @staticmethod
    async def request_rematch(user_id: int, partner_id: int) -> bool:
        """Handles rematch logic via MatchState."""
        return await match_state.set_rematch(user_id, partner_id)
