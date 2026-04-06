import asyncio
import time
import math
from datetime import datetime
from state.persistence import get_user_profile, save_profiles, load_profiles

def add_xp(user_id: int, amount: int) -> int | None:
    """Awards XP to user and returns the new level if a level-up occurred."""
    profile = get_user_profile(user_id)
    
    # Step 4: Coin Booster check
    booster = profile.get("coin_booster", {})
    if booster.get("active") and booster.get("expires_at", 0) > time.time():
        amount *= 2
        
    profile["xp"] += amount
    
    old_level = profile.get("level", 1)
    # Level formula: floor(sqrt(xp / 10)) + 1
    new_level = int(math.floor(math.sqrt(profile["xp"] / 10))) + 1
    
    if new_level > old_level:
        profile["level"] = new_level
        asyncio.create_task(save_profiles())
        return new_level
    
    asyncio.create_task(save_profiles())
    return None

def check_daily_reward(user_id: int) -> dict | None:
    """Checks and applies daily login reward based on streak."""
    profile = get_user_profile(user_id)
    now = int(time.time())
    
    # Get dates for comparison (ignoring time for daily check)
    today_date = datetime.fromtimestamp(now).date()
    last_login_raw = profile.get("last_login", 0)
    
    if last_login_raw == 0:
        # First login ever
        profile["last_login"] = now
        profile["daily_streak"] = 1
        profile["weekly_streak"] = 0
        reward = 5
        profile["coins"] += reward
        asyncio.create_task(save_profiles())
        return {"streak": 1, "reward": reward, "vip": False}

    last_login_date = datetime.fromtimestamp(last_login_raw).date()
    
    if today_date > last_login_date:
        # New calendar day login
        days_diff = (today_date - last_login_date).days
        
        # Reset daily matches & challenge
        profile["matches_today"] = 0
        profile["daily_challenge"] = {
            "matches_completed": 0,
            "messages_sent": 0,
            "completed": False
        }
        
        # Check if new week
        last_week = last_login_date.isocalendar()[1]
        this_week = today_date.isocalendar()[1]
        if this_week != last_week:
            profile["matches_this_week"] = 0

        if days_diff == 1:
            # Consecutive day
            profile["daily_streak"] += 1
            if profile["daily_streak"] >= 7:
                # 7-day streak reached
                profile["weekly_streak"] += 1
                profile["daily_streak"] = 0 # Reset daily but keep weekly
                
                # Step 6: Monthly streak (4 weeks)
                if profile["weekly_streak"] >= 4:
                    profile["monthly_streak"] += 1
                    profile["weekly_streak"] = 0
                    profile["vip"] = True
                    profile["coins"] += 100 # Huge bonus
                else:
                    profile["vip"] = True # Weekly VIP
        else:
            # Gap in login, reset streak
            profile["daily_streak"] = 1
            
        profile["last_login"] = now
        streak = profile["daily_streak"]
        weekly = profile["weekly_streak"]
        monthly = profile.get("monthly_streak", 0)
        
        # Base rewards + streak bonus
        base_reward = 10 if profile.get("vip") else 2
        reward = base_reward + (streak * 2) + (weekly * 15) + (monthly * 50)
        
        profile["coins"] += reward
        asyncio.create_task(save_profiles())
        return {
            "streak": streak, 
            "weekly": weekly, 
            "monthly": monthly,
            "reward": reward, 
            "vip": profile.get("vip")
        }
        
    return None

async def initialize_user_service():
    await load_profiles()

def add_coins(user_id: int, amount: int):
    profile = get_user_profile(user_id)
    
    # Step 4: Coin Booster check
    booster = profile.get("coin_booster", {})
    if booster.get("active") and booster.get("expires_at", 0) > time.time():
        amount *= 2
        
    profile["coins"] += amount
    asyncio.create_task(save_profiles())

def deduct_coins(user_id: int, amount: int) -> bool:
    profile = get_user_profile(user_id)
    if profile["coins"] >= amount:
        profile["coins"] -= amount
        asyncio.create_task(save_profiles())
        return True
    return False

def get_coins(user_id: int) -> int:
    profile = get_user_profile(user_id)
    return profile.get("coins", 0)

def update_last_active(user_id: int):
    profile = get_user_profile(user_id)
    profile["last_active"] = int(time.time())
    asyncio.create_task(save_profiles())

def get_streak_warning(user_id: int) -> str | None:
    """Checks if user hasn't logged in today and their streak is at risk."""
    profile = get_user_profile(user_id)
    last_login = profile.get("last_login", 0)
    if last_login == 0:
        return None
        
    now = int(time.time())
    today_date = datetime.fromtimestamp(now).date()
    last_login_date = datetime.fromtimestamp(last_login).date()
    
    if today_date > last_login_date:
        days_diff = (today_date - last_login_date).days
        if days_diff == 1:
            # User logged in yesterday but not yet today
            # It's late in the day? (say after 6 PM)
            hour = datetime.fromtimestamp(now).hour
            if hour >= 18:
                return "⚠️ **Streak Warning!**\nLog in now to maintain your daily streak and VIP progress!"
    return None

def check_achievements(user_id: int) -> list[str]:
    """Checks for newly unlocked achievements and returns their names."""
    profile = get_user_profile(user_id)
    unlocked = profile.get("achievements", [])
    newly_unlocked = []
    
    # Milestone checks
    milestones = [
        {"id": "rookie", "title": "Rookie Connector", "desc": "Completed 5 matches", "condition": lambda p: p.get("matches", 0) >= 5},
        {"id": "economist", "title": "Economist", "desc": "Held 50 or more coins", "condition": lambda p: p.get("coins", 0) >= 50},
        {"id": "marathoner", "title": "Chat Marathoner", "desc": "Completed 10 matches", "condition": lambda p: p.get("matches", 0) >= 10},
    ]
    
    for m in milestones:
        if m["id"] not in unlocked and m["condition"](profile):
            unlocked.append(m["id"])
            newly_unlocked.append(f"{m['title']}: {m['desc']}")
            
    if newly_unlocked:
        profile["achievements"] = unlocked
        asyncio.create_task(save_profiles())
        
    return newly_unlocked

def increment_challenge(user_id: int, challenge_type: str, amount: int = 1):
    """Increments a specific mini-challenge metric."""
    profile = get_user_profile(user_id)
    challenges = profile.get("mini_challenges", {})
    challenges[challenge_type] = challenges.get(challenge_type, 0) + amount
    profile["mini_challenges"] = challenges
    asyncio.create_task(save_profiles())

def check_milestone(user_id: int, challenge_type: str) -> dict | None:
    """Checks if a milestone has been reached for a challenge."""
    profile = get_user_profile(user_id)
    challenges = profile.get("mini_challenges", {})
    current_value = challenges.get(challenge_type, 0)
    
    # Define milestones
    milestones = {
        "messages_sent": [10, 50, 100, 500, 1000],
        "matches_completed": [5, 10, 50, 100, 500]
    }
    
    if challenge_type in milestones:
        for m in milestones[challenge_type]:
            # Trigger if exactly at milestone
            if current_value == m:
                return {
                    "type": challenge_type,
                    "milestone": m,
                    "reward_xp": m // 5,
                    "reward_coins": m // 10
                }
    return None

def report_user(user_id: int):
    profile = get_user_profile(user_id)
    profile["reports"] += 1
    if profile["reports"] >= 3:
        profile["blocked"] = True
    asyncio.create_task(save_profiles())
    return profile["blocked"]

def increment_daily_challenge(user_id: int, challenge_type: str, amount: int = 1):
    """Increments a daily challenge metric and checks for completion."""
    profile = get_user_profile(user_id)
    challenge = profile.get("daily_challenge", {})
    
    if challenge.get("completed", False):
        return None
        
    challenge[challenge_type] = challenge.get(challenge_type, 0) + amount
    
    # Check completion
    matches = challenge.get("matches_completed", 0)
    messages = challenge.get("messages_sent", 0)
    
    if matches >= 5 and messages >= 50:
        challenge["completed"] = True
        # Award rewards
        profile["coins"] += 20
        profile["xp"] += 50
        asyncio.create_task(save_profiles())
        return "🏆 **Daily Challenge Completed!**\nYou've earned **+20 Coins** and **+50 XP**!"
        
    profile["daily_challenge"] = challenge
    asyncio.create_task(save_profiles())
    return None

def is_user_blocked(user_id: int) -> bool:
    profile = get_user_profile(user_id)
    return profile.get("blocked", False)
