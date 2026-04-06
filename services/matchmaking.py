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
        
        success = await match_state.add_to_queue(
            user_id, 
            priority=priority, 
            gender=user_gender, 
            pref=gender_pref
        )
        return success

    @staticmethod
    async def find_partner(client: Client, user_id: int) -> Optional[int]:
        """Attempts to match the user with another person in the queue."""
        partner_id = await match_state.find_match(user_id)
        if not partner_id:
            return None
            
        # Initialize match logic (award base coins, increment matches)
        # We do this for both users
        for uid in [user_id, partner_id]:
            await UserService.add_coins(uid, 2)
            user = await UserRepository.get_by_telegram_id(uid)
            matches = (user.get("total_matches") or 0) + 1
            await UserRepository.update(uid, total_matches=matches)
            await UserService.increment_challenge(uid, "matches_completed")
            
        logger.info(f"📡 Match Established: {user_id} <-> {partner_id}")
        return partner_id

    @staticmethod
    async def disconnect(user_id: int) -> Optional[Dict[str, Any]]:
        """Ends a chat session and calculates rewards."""
        result = await match_state.disconnect(user_id)
        if not result:
            return None
            
        partner_id, duration_seconds = result
        duration_minutes = duration_seconds // 60
        
        # Base rewards
        match_reward = 5
        time_reward = duration_minutes * 2
        xp_reward = max(2, duration_minutes * 2)
        
        # Event multipliers
        active_event = get_active_event()
        event_mult = active_event.get("multiplier", 1.0)
        
        # User 1 specific (the one who initiated disconnect)
        u1 = await UserRepository.get_by_telegram_id(user_id)
        u1_coins = int(time_reward * event_mult)
        if u1.get("coin_booster", {}).get("active"): u1_coins *= 2
        await UserService.add_coins(user_id, match_reward + u1_coins)
        u1_levelup = await UserService.add_xp(user_id, int(xp_reward * event_mult))
        
        # User 2 specific
        u2 = await UserRepository.get_by_telegram_id(partner_id)
        u2_coins = int(time_reward * event_mult)
        if u2:
            if u2.get("coin_booster", {}).get("active"): u2_coins *= 2
            await UserService.add_coins(partner_id, match_reward + u2_coins)
            u2_levelup = await UserService.add_xp(partner_id, int(xp_reward * event_mult))
            
            # Analytics / Sessions DB - Only log real user matches
            await SessionRepository.create(user_id, partner_id)
        
        # Challenge updates
        # (Assuming messages_sent is tracked elsewhere in message handlers)
        
        return {
            "user_id": user_id,
            "partner_id": partner_id,
            "duration_seconds": duration_seconds,
            "duration_minutes": duration_minutes,
            "coins_earned": match_reward + u1_coins,
            "xp_earned": int(xp_reward * event_mult),
            "u2_coins_earned": match_reward + u2_coins,
            "u2_xp_earned": int(xp_reward * event_mult),
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
