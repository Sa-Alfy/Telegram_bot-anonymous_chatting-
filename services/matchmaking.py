import asyncio
from state.memory import waiting_queue, active_chats, queue_lock
from services.user_service import get_user_profile
from services.event_manager import get_active_event, add_event_points

async def add_to_queue(user_id: int):
    async with queue_lock:
        if user_id in active_chats:
            return False # Already in chat
            
        # Step 4: Timed Priority Pack check
        profile = get_user_profile(user_id)
        timed_pack = profile.get("priority_pack", {})
        if timed_pack.get("active") and timed_pack.get("expires_at", 0) > time.time():
            if user_id in waiting_queue:
                waiting_queue.remove(user_id)
            waiting_queue.insert(0, user_id)
            return True

        if user_id not in waiting_queue:
            waiting_queue.append(user_id)
        return True

async def add_priority_to_queue(user_id: int):
    async with queue_lock:
        if user_id in active_chats:
            return False
        if user_id in waiting_queue:
            waiting_queue.remove(user_id)
        waiting_queue.insert(0, user_id)
        return True

async def remove_from_queue(user_id: int):
    async with queue_lock:
        if user_id in waiting_queue:
            if user_id in waiting_queue:
                waiting_queue.remove(user_id)

import time
from state.memory import waiting_queue, active_chats, queue_lock, chat_start_times
from services.user_service import get_user_profile, add_coins, save_profiles

async def find_partner(user_id: int) -> int | None:
    async with queue_lock:
        if user_id not in waiting_queue:
            return None
            
        # We try to match with someone else in queue
        for partner_id in waiting_queue:
            if partner_id != user_id:
                # Security: ensure partner isn't blocked
                profile = get_user_profile(partner_id)
                if profile.get('blocked'):
                    continue
                
                # Double secure: ensure user isn't blocked
                user_profile = get_user_profile(user_id)
                if user_profile.get('blocked'):
                    return None
                
                # Match found
                waiting_queue.remove(user_id)
                waiting_queue.remove(partner_id)
                
                active_chats[user_id] = partner_id
                active_chats[partner_id] = user_id
                
                # Update match stats and coins
                now = time.time()
                chat_start_times[user_id] = now
                chat_start_times[partner_id] = now
                
                add_coins(user_id, 2)
                add_coins(partner_id, 2)
                
                user_profile["matches"] += 1
                profile["matches"] += 1
                
                # Daily and Weekly stats
                user_profile["matches_today"] += 1
                profile["matches_today"] += 1
                user_profile["matches_this_week"] += 1
                profile["matches_this_week"] += 1
                
                # Step 4: Daily Challenges & Mini-challenges
                from services.user_service import increment_challenge, increment_daily_challenge
                increment_challenge(user_id, "matches_completed")
                increment_challenge(partner_id, "matches_completed")
                
                # Daily challenge updates
                res1 = increment_daily_challenge(user_id, "matches_completed")
                if res1: asyncio.create_task(client.send_message(user_id, res1))
                res2 = increment_daily_challenge(partner_id, "matches_completed")
                if res2: asyncio.create_task(client.send_message(partner_id, res2))
                import asyncio
                asyncio.create_task(save_profiles())
                
                return partner_id
                
        return None

async def disconnect(user_id: int) -> dict | None:
    """Disconnects user and returns session summary (partner_id, duration, coins)."""
    async with queue_lock:
        if user_id in active_chats:
            partner_id = active_chats.pop(user_id)
            if partner_id in active_chats:
                active_chats.pop(partner_id)
            
            # Session tracking and coin reward
            now = time.time()
            start_time = chat_start_times.pop(user_id, now)
            chat_start_times.pop(partner_id, None) # Clear partner's time too
            
            duration_seconds = int(now - start_time)
            duration_minutes = int(duration_seconds // 60)
            
            # Update total chat time
            user_profile = get_user_profile(user_id)
            partner_profile = get_user_profile(partner_id)
            
            user_profile["total_chat_time"] += duration_seconds
            partner_profile["total_chat_time"] += duration_seconds

            # Award XP (2 XP per minute, min 2)
            xp_to_add = max(2, duration_minutes * 2)
            from services.user_service import add_xp, check_achievements
            u1_levelup = add_xp(user_id, xp_to_add)
            u2_levelup = add_xp(partner_id, xp_to_add)
            
            # Check for new achievements
            u1_achievements = check_achievements(user_id)
            u2_achievements = check_achievements(partner_id)
            
            # Base coins for matching (5) + 2 coins per minute
            match_reward = 5
            time_reward = duration_minutes * 2
            
            # Step 6: Reaction Bonuses
            u1_reactions = len(user_profile.get("reaction_notifications", []))
            u2_reactions = len(partner_profile.get("reaction_notifications", []))
            
            u1_bonus_coins = u1_reactions * 1
            u1_bonus_xp = u1_reactions * 2
            u2_bonus_coins = u2_reactions * 1
            u2_bonus_xp = u2_reactions * 2
            
            # Reset reaction notifications for new session
            user_profile["reaction_notifications"] = []
            partner_profile["reaction_notifications"] = []

            # Apply multipliers (Coin Booster & Event Multiplier)
            active_event = get_active_event()
            event_mult = active_event.get("multiplier", 1.0)
            
            total_u1_coins = (time_reward + u1_bonus_coins) * event_mult
            total_u2_coins = (time_reward + u2_bonus_coins) * event_mult
            
            xp_to_add = (xp_to_add + u1_bonus_xp) * event_mult
            u2_xp_add = (xp_to_add + u2_bonus_xp) * event_mult # U2's XP base + reactions
            
            if user_profile.get("coin_booster", {}).get("active"):
                total_u1_coins *= 2
            if partner_profile.get("coin_booster", {}).get("active"):
                total_u2_coins *= 2
            
            # Phase 5: Event Points (Tournament)
            u1_event_points = 0
            u2_event_points = 0
            if active_event.get("type") == "tournament":
                # Points: 10 per match + 5 per minute
                pts = 10 + (duration_minutes * 5)
                u1_event_points = pts
                u2_event_points = pts
                add_event_points(user_id, u1_event_points)
                add_event_points(partner_id, u2_event_points)

            from services.user_service import add_coins
            add_coins(user_id, int(total_u1_coins)) 
            add_coins(partner_id, int(total_u2_coins))
            add_xp(user_id, int(xp_to_add))
            add_xp(partner_id, int(u2_xp_add))

            # Update total chat stats for analytics
            user_profile["total_coins_earned"] += (match_reward + total_u1_coins)
            partner_profile["total_coins_earned"] += (match_reward + total_u2_coins)
            user_profile["total_xp_earned"] += (xp_to_add + u1_bonus_xp)
            partner_profile["total_xp_earned"] += (xp_to_add + u2_bonus_xp)
            
            for profile in [user_profile, partner_profile]:
                # Update avg duration: (old_avg * (total_matches - 1) + current_duration) / total_matches
                old_avg = profile.get("avg_duration_seconds", 0)
                total_matches = profile.get("matches", 0)
                if total_matches > 0:
                    new_avg = (old_avg * (total_matches - 1) + duration_seconds) // total_matches
                    profile["avg_duration_seconds"] = int(new_avg)
            
            import asyncio
            asyncio.create_task(save_profiles())
            
            return {
                "partner_id": partner_id,
                "duration_seconds": duration_seconds,
                "duration_minutes": duration_minutes,
                "coins_earned": match_reward + total_u1_coins, # U1's reward for display
                "u2_coins_earned": match_reward + total_u2_coins, # U2's reward for display
                "u1_levelup": u1_levelup,
                "u2_levelup": u2_levelup,
                "xp_earned": xp_to_add + u1_bonus_xp,
                "u2_xp_earned": xp_to_add + u2_bonus_xp,
                "u1_reactions": u1_reactions,
                "u2_reactions": u2_reactions,
                "u1_achievements": u1_achievements,
                "u2_achievements": u2_achievements,
                "event_points": u1_event_points,
                "u2_event_points": u2_event_points,
                "matches_total": user_profile.get("matches", 0)
            }
        return None
