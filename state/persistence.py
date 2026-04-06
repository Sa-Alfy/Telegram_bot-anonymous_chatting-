import os
import ujson
import asyncio
from utils.logger import logger

DATA_FILE = os.path.join(os.path.dirname(__file__), '..', 'data', 'users.json')

# user_profiles = { "user_id": { "reports": 0, "blocked": False } }
user_profiles = {}
_file_lock = asyncio.Lock()

async def load_profiles():
    global user_profiles
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                content = f.read()
                if content.strip():
                    user_profiles = ujson.loads(content)
                    # Convert string keys back to int format
                    user_profiles = {int(k): v for k, v in user_profiles.items()}
            logger.info(f"Loaded {len(user_profiles)} user profiles.")
        except Exception as e:
            logger.error(f"Error loading profiles: {e}")

async def save_profiles():
    async with _file_lock:
        try:
            os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
            with open(DATA_FILE, 'w', encoding='utf-8') as f:
                f.write(ujson.dumps(user_profiles, indent=4))
        except Exception as e:
            logger.error(f"Error saving profiles: {e}")

import time

def get_user_profile(user_id: int) -> dict:
    if user_id not in user_profiles:
        user_profiles[user_id] = {
            "coins": 10,
            "matches": 0,
            "total_chat_time": 0,
            "revealed": False,
            "blocked": False,
            "reports": 0,
            "last_active": int(time.time()),
            "daily_streak": 0,
            "weekly_streak": 0,
            "last_login": 0,
            "vip": False,
            "xp": 0,
            "level": 1,
            "achievements": [],
            "priority_matches": 0,
            "matches_this_week": 0,
            "matches_today": 0,
            "total_coins_earned": 0,
            "total_xp_earned": 0,
            "avg_duration_seconds": 0,
            "mini_challenges": {
                "messages_sent": 0,
                "matches_completed": 0
            },
            "priority_pack": {
                "active": False,
                "expires_at": 0
            },
            "coin_booster": {
                "active": False,
                "expires_at": 0
            },
            "monthly_streak": 0,
            "mini_events_triggered": [],
            "last_event_time": 0,
            "reaction_history": [],
            "friends": [],
            "daily_challenge": {
                "matches_completed": 0,
                "messages_sent": 0,
                "completed": False
            },
            "reaction_notifications": [],
            "rematch_available": False,
            "last_partner_id": 0,
            "seasonal_events": {
                "current_event_id": None,
                "participation_count": 0,
                "event_points": 0
            },
            "coin_shop_purchases": [],
            "dynamic_costs": {
                "identity_reveal": 15,
                "priority_match": 5,
                "peek_stats": 5
            }
        }
        asyncio.create_task(save_profiles())
    else:
        # Step 1: Migration - provide defaults for missing fields
        profile = user_profiles[user_id]
        defaults = {
            "coins": 10,
            "matches": 0,
            "total_chat_time": 0,
            "revealed": False,
            "blocked": False,
            "reports": 0,
            "last_active": int(time.time()),
            "daily_streak": 0,
            "weekly_streak": 0,
            "last_login": 0,
            "vip": False,
            "xp": 0,
            "level": 1,
            "achievements": [],
            "priority_matches": 0,
            "matches_this_week": 0,
            "matches_today": 0,
            "total_coins_earned": 0,
            "total_xp_earned": 0,
            "avg_duration_seconds": 0,
            "mini_challenges": {
                "messages_sent": 0,
                "matches_completed": 0
            },
            "priority_pack": {
                "active": False,
                "expires_at": 0
            },
            "coin_booster": {
                "active": False,
                "expires_at": 0
            },
            "monthly_streak": 0,
            "mini_events_triggered": [],
            "last_event_time": 0,
            "reaction_history": [],
            "friends": [],
            "daily_challenge": {
                "matches_completed": 0,
                "messages_sent": 0,
                "completed": False
            },
            "reaction_notifications": [],
            "rematch_available": False,
            "last_partner_id": 0,
            "seasonal_events": {
                "current_event_id": None,
                "participation_count": 0,
                "event_points": 0
            },
            "coin_shop_purchases": [],
            "dynamic_costs": {
                "identity_reveal": 15,
                "priority_match": 5,
                "peek_stats": 5
            }
        }
        changed = False
        for key, value in defaults.items():
            if key not in profile:
                profile[key] = value
                changed = True
        
        if changed:
            asyncio.create_task(save_profiles())
            
    return user_profiles[user_id]
