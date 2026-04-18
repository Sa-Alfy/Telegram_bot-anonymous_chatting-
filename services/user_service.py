import asyncio
import time
import math
from datetime import datetime
from typing import Optional, Dict, Any, List

from database.repositories.user_repository import UserRepository
from database.repositories.admin_repository import AdminRepository
from database.repositories.report_repository import ReportRepository
from database.connection import db
from utils.logger import logger

class UserService:
    @staticmethod
    async def add_xp(user_id: int, amount: int) -> Optional[int]:
        """Awards XP to user and returns the new level if a level-up occurred."""
        user = await UserRepository.get_by_telegram_id(user_id)
        if not user or user.get("is_guest"):
            return None

        # Check for boosters
        booster = user.get("coin_booster", {})
        if booster.get("active") and booster.get("expires_at", 0) > time.time():
            amount *= 2
            
        new_xp = (user.get("xp") or 0) + amount
        
        old_level = user.get("level", 1)
        # Level formula: floor(sqrt(xp / 10)) + 1
        new_level = int(math.floor(math.sqrt(new_xp / 10))) + 1
        
        update_data = {"xp": new_xp}
        level_up = None
        if new_level > old_level:
            update_data["level"] = new_level
            level_up = new_level
            
        await UserRepository.update(user_id, **update_data)
        return level_up

    @staticmethod
    async def add_coins(user_id: int, amount: int):
        """Adds coins to a user's balance."""
        user = await UserRepository.get_by_telegram_id(user_id)
        if not user or user.get("is_guest"):
            return
            
        # Check for boosters
        booster = user.get("coin_booster", {})
        if booster.get("active") and booster.get("expires_at", 0) > time.time():
            amount *= 2
            
        await UserRepository.increment_coins(user_id, amount)

    @staticmethod
    async def deduct_coins(user_id: int, amount: int) -> bool:
        """Deducts coins atomically. Returns True only if coins were sufficient."""
        query = (
            "UPDATE users SET coins = coins - $1 "
            "WHERE telegram_id = $2 AND coins >= $3 AND is_guest = false"
        )
        cursor = await db.execute(query, (amount, user_id, amount))
        return cursor.rowcount > 0

    @staticmethod
    async def check_daily_reward(user_id: int) -> Optional[Dict[str, Any]]:
        """Checks and applies daily login reward based on streak."""
        user = await UserRepository.get_by_telegram_id(user_id)
        if not user:
            return None
            
        now = int(time.time())
        today_date = datetime.fromtimestamp(now).date()
        last_login_raw = user.get("last_login") or 0
        
        if last_login_raw == 0:
            # First login
            update_data = {
                "last_login": now,
                "daily_streak": 1,
                "weekly_streak": 0,
            }
            await UserRepository.update(user_id, **update_data)
            await UserRepository.increment_coins(user_id, 5)
            return {"streak": 1, "reward": 5, "vip": False}

        last_login_date = datetime.fromtimestamp(last_login_raw).date()
        
        if today_date > last_login_date:
            days_diff = (today_date - last_login_date).days
            
            # Reset daily counters in JSON data
            daily_challenge = {
                "matches_completed": 0,
                "messages_sent": 0,
                "completed": False
            }
            
            update_data = {
                "last_login": now,
                "daily_challenge": daily_challenge
            }
            
            # Check weekly match reset
            last_week = last_login_date.isocalendar()[1]
            this_week = today_date.isocalendar()[1]
            if this_week != last_week:
                update_data["matches_this_week"] = 0

            # Streak logic
            daily_streak = user.get("daily_streak", 0)
            weekly_streak = user.get("weekly_streak", 0)
            monthly_streak = user.get("monthly_streak", 0)
            vip = bool(user.get("vip_status", False))
            
            if days_diff == 1:
                daily_streak += 1
                if daily_streak >= 7:
                    weekly_streak += 1
                    daily_streak = 0
                    if weekly_streak >= 4:
                        monthly_streak += 1
                        weekly_streak = 0
                        vip = True
                    else:
                        vip = True
            else:
                daily_streak = 1
                
            update_data.update({
                "daily_streak": daily_streak,
                "weekly_streak": weekly_streak,
                "monthly_streak": monthly_streak,
                "vip_status": vip
            })
            
            # Calculate reward
            base_reward = 10 if vip else 2
            reward = base_reward + (daily_streak * 2) + (weekly_streak * 15) + (monthly_streak * 50)

            await UserRepository.update(user_id, **update_data)
            await UserRepository.increment_coins(user_id, reward)
            return {
                "streak": daily_streak,
                "weekly": weekly_streak,
                "monthly": monthly_streak,
                "reward": reward,
                "vip": vip
            }
            
        return None

    @staticmethod
    async def update_profile(user_id: int, gender: str, location: str, bio: str):
        """Completes onboarding and updates profile."""
        await UserRepository.update(
            user_id,
            gender=gender,
            location=location,
            bio=bio,
            is_guest=False
        )

    @staticmethod
    async def report_user(reporter_id: int, reported_id: int, reason: str = "Excessive reports") -> bool:
        """Reports a user and auto-blocks if thresholds met."""
        await ReportRepository.create(reporter_id, reported_id, reason)

        # Atomic increment — no read-then-write race condition
        await db.execute(
            "UPDATE users SET reports = reports + 1 WHERE telegram_id = $1",
            (reported_id,)
        )
        row = await db.fetchone(
            "SELECT reports FROM users WHERE telegram_id = $1", (reported_id,)
        )
        reports_count = row["reports"] if row else 0

        is_blocked = False
        if reports_count >= 3:
            is_blocked = True
            await UserRepository.set_blocked(reported_id, True)
            logger.error(f"User {reported_id} has been AUTO-BLOCKED.")
        return is_blocked

    @staticmethod
    async def increment_challenge(user_id: int, challenge_type: str, amount: int = 1):
        """Increments matching mini-challenge (e.g. 'matches_completed')"""
        user = await UserRepository.get_by_telegram_id(user_id)
        challenges = user.get("mini_challenges", {})
        challenges[challenge_type] = challenges.get(challenge_type, 0) + amount
        await UserRepository.update(user_id, mini_challenges=challenges)

    @staticmethod
    async def check_milestones(user_id: int, challenge_type: str) -> Optional[Dict[str, Any]]:
        """Checks for reached milestones and returns reward data."""
        user = await UserRepository.get_by_telegram_id(user_id)
        challenges = user.get("mini_challenges", {})
        val = challenges.get(challenge_type, 0)
        
        milestones = {
            "messages_sent": [10, 50, 100, 500, 1000],
            "matches_completed": [5, 10, 50, 100, 500]
        }
        
        milestone_key = f"{challenge_type}_{val}"
        completed = user.get("completed_milestones", [])
        if challenge_type in milestones and val in milestones[challenge_type] and milestone_key not in completed:
            reward_xp = val // 5
            reward_coins = val // 10
            await UserRepository.increment_xp(user_id, reward_xp)
            await UserRepository.increment_coins(user_id, reward_coins)
            completed.append(milestone_key)
            await UserRepository.update(user_id, completed_milestones=completed)
            return {
                "milestone": val,
                "reward_xp": reward_xp,
                "reward_coins": reward_coins
            }
        return None
