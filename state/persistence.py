import os
import ujson
import sqlite3
import asyncio
import time
from utils.logger import logger
from state.database import db_conn, DB_PATH

JSON_DATA_FILE = os.path.join(os.path.dirname(__file__), '..', 'data', 'users.json')

# Cache for active user profiles (to avoid heavy DB reads for every message)
# In-memory dictionary like before, but backed by SQLite
user_profiles = {}
_db_lock = asyncio.Lock()

async def migrate_from_json():
    """Migrates data from users.json to SQLite if the database is empty."""
    if not os.path.exists(JSON_DATA_FILE):
        return

    cursor = db_conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM users")
    if cursor.fetchone()[0] > 0:
        logger.info("📡 Database already contains data. Skipping JSON migration.")
        return

    try:
        with open(JSON_DATA_FILE, 'r', encoding='utf-8') as f:
            data = ujson.load(f)
            
        logger.info(f"🚚 Migrating {len(data)} profiles from JSON to SQLite...")
        
        for uid_str, profile in data.items():
            uid = int(uid_str)
            
            # Map top-level fields
            fields = {
                "user_id": uid,
                "first_name": profile.get("first_name", "Unknown"),
                "coins": profile.get("coins", 10),
                "xp": profile.get("xp", 0),
                "level": profile.get("level", 1),
                "vip": 1 if profile.get("vip") else 0,
                "matches": profile.get("matches", 0),
                "matches_today": profile.get("matches_today", 0),
                "matches_this_week": profile.get("matches_this_week", 0),
                "total_chat_time": profile.get("total_chat_time", 0),
                "daily_streak": profile.get("daily_streak", 0),
                "weekly_streak": profile.get("weekly_streak", 0),
                "monthly_streak": profile.get("monthly_streak", 0),
                "last_login": profile.get("last_login", 0),
                "last_active": profile.get("last_active", 0),
                "blocked": 1 if profile.get("blocked") else 0,
                "reports": profile.get("reports", 0),
                "revealed": 1 if profile.get("revealed") else 0,
                "last_partner_id": profile.get("last_partner_id", 0),
                "rematch_available": 1 if profile.get("rematch_available") else 0,
                "is_guest": 0 # Existing users are not guests
            }
            
            # Pack the rest into JSON data
            core_keys = set(fields.keys())
            extra_data = {k: v for k, v in profile.items() if k not in core_keys and k != "user_id"}
            fields["json_data"] = ujson.dumps(extra_data)
            
            columns = ", ".join(fields.keys())
            placeholders = ", ".join(["?"] * len(fields))
            cursor.execute(f"INSERT INTO users ({columns}) VALUES ({placeholders})", tuple(fields.values()))
            
        db_conn.commit()
        logger.info("✅ Migration completed successfully. You can now delete users.json.")
    except Exception as e:
        logger.error(f"❌ Migration failed: {e}")

def get_user_profile(user_id: int) -> dict:
    """Gets a user profile from the database, initializing it if necessary."""
    if user_id in user_profiles:
        return user_profiles[user_id]
        
    cursor = db_conn.cursor()
    cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    
    if row:
        profile = dict(row)
        # Unpack JSON data
        extra_data = ujson.loads(profile.pop("json_data", "{}"))
        profile.update(extra_data)
        
        # Convert SQLite integers back to Booleans for compatibility
        bool_fields = ["vip", "blocked", "revealed", "rematch_available", "is_guest"]
        for field in bool_fields:
            if field in profile:
                profile[field] = bool(profile[field])
                
        user_profiles[user_id] = profile
        return profile
    else:
        # Create default profile for new user (Guest Mode)
        new_profile = {
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
            "mini_challenges": {"messages_sent": 0, "matches_completed": 0},
            "priority_pack": {"active": False, "expires_at": 0},
            "coin_booster": {"active": False, "expires_at": 0},
            "monthly_streak": 0,
            "mini_events_triggered": [],
            "last_event_time": 0,
            "reaction_history": [],
            "friends": [],
            "daily_challenge": {"matches_completed": 0, "messages_sent": 0, "completed": False},
            "reaction_notifications": [],
            "rematch_available": False,
            "last_partner_id": 0,
            "seasonal_events": {"current_event_id": None, "participation_count": 0, "event_points": 0},
            "coin_shop_purchases": [],
            "dynamic_costs": {"identity_reveal": 15, "priority_match": 5, "peek_stats": 5},
            "is_guest": True # Initial state is Guest
        }
        user_profiles[user_id] = new_profile
        asyncio.create_task(save_profiles(user_id))
        return new_profile

async def save_profiles(user_id: int = None):
    """Saves one or all profiles to SQLite. If user_id is None, saves all cached profiles."""
    async with _db_lock:
        cursor = db_conn.cursor()
        
        # Helper to save a single profile
        def save_one(uid):
            profile = user_profiles[uid].copy()
            
            # Extract top-level fields
            top_level = [
                "user_id", "first_name", "gender", "location", "bio", "profile_photo", 
                "is_guest", "coins", "xp", "level", "vip", "matches", "matches_today", 
                "matches_this_week", "total_chat_time", "daily_streak", "weekly_streak", 
                "monthly_streak", "last_login", "last_active", "blocked", "reports", 
                "revealed", "last_partner_id", "rematch_available"
            ]
            
            fields = {}
            for key in top_level:
                if key in profile:
                    val = profile.pop(key)
                    # Convert bool to int for SQLite
                    if isinstance(val, bool):
                        val = 1 if val else 0
                    fields[key] = val
                elif key == "user_id":
                    fields["user_id"] = uid
            
            # Pack remaining data
            fields["json_data"] = ujson.dumps(profile)
            
            columns = ", ".join(fields.keys())
            placeholders = ", ".join(["?"] * len(fields))
            cursor.execute(f"REPLACE INTO users ({columns}) VALUES ({placeholders})", tuple(fields.values()))

        try:
            if user_id:
                if user_id in user_profiles:
                    save_one(user_id)
            else:
                for uid in list(user_profiles.keys()):
                    save_one(uid)
            
            db_conn.commit()
        except Exception as e:
            logger.error(f"❌ Database save failed: {e}")

async def load_profiles():
    """Initializes the database and triggers migration."""
    # Migration is now part of startup flow
    await migrate_from_json()
