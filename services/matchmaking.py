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
    async def initialize_match(client: Client, user1_id: Any, user2_id: Any):
        """Standardized match setup: Rewards, DB updates, Behavior tracking, and Platform UI."""
        from services.user_service import UserService
        from database.repositories.user_repository import UserRepository
        from utils.ui_formatters import get_match_found_text
        from utils.helpers import update_user_ui
        from adapters.telegram.keyboards import get_chat_keyboard, persistent_chat_menu
        from core.behavior_engine import behavior_engine
        from core.engine.state_machine import UnifiedState
        from services.distributed_state import distributed_state
        from state.match_state import UserState
        import time
        import app_state

        uids = [user1_id, user2_id]
        now = time.time()

        # 1. DB & Reward Updates
        try:
            for uid in uids:
                # Clean ID for DB operations (strip prefixes if any)
                if isinstance(uid, str) and uid.startswith("msg_"):
                    from messenger.utils import _raw
                    psid = _raw(uid)
                    import hashlib
                    psid_hash = int(hashlib.sha256(psid.encode()).hexdigest(), 16)
                    db_id = (psid_hash % (10**15)) + 10**15
                else:
                    db_id = int(uid)

                await UserService.add_coins(db_id, 2)
                user = await UserRepository.get_by_telegram_id(db_id)
                if user:
                    matches = (user.get("total_matches") or 0) + 1
                    await UserRepository.update(db_id, total_matches=matches)
                    await UserService.increment_challenge(db_id, "matches_completed")
                    await behavior_engine.record_session_start(db_id)
        except Exception as e:
            logger.error(f"Post-match DB updates failed for {user1_id}-{user2_id}: {e}")

        # 1.5 Sync engine states via ActionRouter (Unified Engine Step 3)
        for uid in uids:
            try:
                await app_state.engine.process_event({
                    "event_type": "CONNECT",
                    "user_id": str(uid),
                    "timestamp": int(now)
                })
            except Exception as e:
                logger.error(f"Engine CONNECT failed for {uid}: {e}")

        # 1.7 UI Delivery — Primary match notification for both users
        match_text = get_match_found_text(include_safety=True)
        for uid in uids:
            try:
                if isinstance(uid, str) and uid.startswith("msg_"):
                    from messenger.utils import _raw
                    psid = _raw(uid)
                    import hashlib
                    psid_hash = int(hashlib.sha256(psid.encode()).hexdigest(), 16)
                    notify_id = (psid_hash % (10**15)) + 10**15
                else:
                    notify_id = int(uid)

                await update_user_ui(client, notify_id, match_text, persistent_chat_menu(), force_new=True)
            except Exception as e:
                logger.error(f"Match notification failed for {uid}: {e}")

        # 2. Safety Warning & Additional Context (Post-Engine)
        for uid in uids:
            try:
                if isinstance(uid, str) and uid.startswith("msg_"):
                    from messenger.utils import _raw
                    psid = _raw(uid)
                    import hashlib
                    psid_hash = int(hashlib.sha256(psid.encode()).hexdigest(), 16)
                    db_id = (psid_hash % (10**15)) + 10**15
                else:
                    db_id = int(uid)

                user = await UserRepository.get_by_telegram_id(db_id)
                if not user: continue
                
                warning = await behavior_engine.get_match_warning(db_id)
                if warning:
                    from utils.helpers import send_cross_platform
                    await send_cross_platform(client, db_id, warning)
            except Exception as e:
                logger.error(f"Post-match cleanup failed for {uid}: {e}")

        logger.info(f"📡 Match Initialized: {user1_id} <-> {user2_id} (Engine-mediated)")


    @staticmethod
    async def disconnect(user_id: Any) -> Optional[Dict[str, Any]]:
        """Ends a chat session and calculates rewards (Atomic Disconnect -> Calc -> DB)."""
        from core.behavior_engine import behavior_engine
        
        # Derive virtual integer ID for DB operations
        if isinstance(user_id, str) and user_id.startswith("msg_"):
            from messenger.utils import _raw
            psid = _raw(user_id)
            import hashlib
            psid_hash = int(hashlib.sha256(psid.encode()).hexdigest(), 16)
            db_id = (psid_hash % (10**15)) + 10**15
        else:
            db_id = int(user_id)

        # 1. ATOMIC DISCONNECT FIRST (Provides Idempotency)
        # MatchState.disconnect handles both TG ints and MSG strings via DistributedState
        stats = await match_state.disconnect(user_id)
        if not stats:
            await match_state.remove_from_queue(user_id)
            return None
            
        partner_id, duration_seconds = stats
        duration_minutes = duration_seconds // 60
        
        # Derive partner DB ID
        if isinstance(partner_id, str) and partner_id.startswith("msg_"):
            psid = partner_id[4:]
            import hashlib
            psid_hash = int(hashlib.sha256(psid.encode()).hexdigest(), 16)
            db_p_id = (psid_hash % (10**15)) + 10**15
        else:
            db_p_id = int(partner_id)

        u1 = await UserRepository.get_by_telegram_id(db_id)
        u2 = await UserRepository.get_by_telegram_id(db_p_id)
        
        if not u1:
            logger.warning(f"Disconnect failed: User {user_id} (DB:{db_id}) not found in DB.")
            return None

        # 2. CALCULATION
        match_reward = 5
        time_reward = duration_minutes * 2
        xp_reward = max(2, duration_minutes * 2)
        
        from services.event_manager import get_active_event
        active_event = get_active_event()
        event_mult = active_event.get("multiplier", 1.0)
        
        u1_b_mult = await behavior_engine.get_reward_multiplier(db_id)
        u2_b_mult = await behavior_engine.get_reward_multiplier(db_p_id)

        u1_coins = int(time_reward * event_mult * u1_b_mult)
        if u1.get("coin_booster", {}).get("active"): u1_coins *= 2
        
        u2_coins = int(time_reward * event_mult * u2_b_mult)
        if u2 and u2.get("coin_booster", {}).get("active"): u2_coins *= 2

        u1_coins_total = match_reward + u1_coins
        u2_coins_total = match_reward + u2_coins
        u1_xp_total = int(xp_reward * event_mult * u1_b_mult)
        u2_xp_total = int(xp_reward * event_mult * u2_b_mult)

        u1_levelup = u2_levelup = False

        # 3. DB COMMIT (Best effort)
        try:
            await UserService.add_coins(db_id, u1_coins_total)
            u1_levelup = await UserService.add_xp(db_id, u1_xp_total)
            
            if u2:
                await UserService.add_coins(db_p_id, u2_coins_total)
                u2_levelup = await UserService.add_xp(db_p_id, u2_xp_total)
            
                await SessionRepository.create_and_end(
                    db_id, db_p_id, duration_seconds,
                    u1_coins_total, u2_coins_total, u1_xp_total, u2_xp_total
                )
                await UserRepository.update(db_id, last_partner_id=db_p_id)
                await UserRepository.update(db_p_id, last_partner_id=db_id)
        except Exception as e:
            logger.error(f"Disconnect DB batch failed for {db_id}-{db_p_id}: {e}")

        # 4. ALWAYS CLEAR STATE (Invariant Enforcement)
        try:
            # This is the most critical step: atomic Redis cleanup
            await behavior_engine.record_disconnect(user_id)
            await behavior_engine.record_disconnect(partner_id)
        except Exception as e:
            logger.critical(f"CRITICAL: Redis cleanup failed after DB commit: {e}")
        
        # Challenge updates
        # (Assuming messages_sent is tracked elsewhere in message handlers)
        
        return {
            "user_id": user_id,
            "partner_id": partner_id,
            "duration_seconds": duration_seconds,
            "duration_minutes": duration_minutes,
            "coins_earned": u1_coins_total,
            "xp_earned": u1_xp_total,
            "u2_coins_earned": u2_coins_total,
            "u2_xp_earned": u2_xp_total,
            "u1_levelup": u1_levelup,
            "u2_levelup": u2_levelup,
            "total_matches": u1.get("total_matches", 0) if u1 else 0
        }

    @staticmethod
    async def remove_from_queue(user_id: int):
        await match_state.remove_from_queue(user_id)

    @staticmethod
    async def request_rematch(user_id: int, partner_id: int) -> tuple[bool, int]:
        """Handles rematch logic via MatchState. Returns (success, code)."""
        return await match_state.set_rematch(user_id, partner_id)
