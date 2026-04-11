import orjson
from typing import Dict, Any, Optional, List
from database.connection import db

class UserRepository:
    @staticmethod
    async def get_by_telegram_id(telegram_id: int) -> Optional[Dict[str, Any]]:
        """Fetch a user profile by Telegram ID with NULL-safety sanitisation."""
        row = await db.fetchone("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,))
        if not row:
            return None
        
        user_data = dict(row)
        
        # --- NULL-Safety Sanitisation ---
        # Ensure numeric fields are never None
        numeric_fields = {
            "coins": 10, "xp": 0, "level": 1, "vip_status": 0,
            "total_matches": 0, "total_chat_time": 0, "daily_streak": 0,
            "weekly_streak": 0, "monthly_streak": 0, "last_login": 0,
            "last_active": 0, "is_blocked": 0, "is_guest": 1, "reports": 0
        }
        for field, default in numeric_fields.items():
            if user_data.get(field) is None:
                user_data[field] = default
        
        # Ensure text fields are never None
        text_fields = ["gender", "location", "bio"]
        for field in text_fields:
            if user_data.get(field) is None:
                user_data[field] = "None" if field == "bio" else "Secret"

        # Unpack JSON data if available
        if user_data.get('json_data'):
            try:
                extra = orjson.loads(user_data.pop('json_data'))
                user_data.update(extra)
            except:
                pass
        return user_data

    @staticmethod
    async def create(telegram_id: int, username: str = None, first_name: str = None) -> Dict[str, Any]:
        """Create a new user with default settings."""
        default_profile = {
            "coins": 10,
            "xp": 0,
            "level": 1,
            "vip_status": 0,
            "total_matches": 0,
            "total_chat_time": 0,
            "is_blocked": 0,
            "is_guest": 1,
            "gender": "Not specified",
            "location": "Secret",
            "bio": "No bio provided."
        }
        
        query = """
        INSERT INTO users (telegram_id, username, first_name, coins, xp, level, vip_status, total_matches, total_chat_time, is_blocked, is_guest, gender, location, bio)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        params = (
            telegram_id, username, first_name,
            default_profile["coins"], default_profile["xp"], default_profile["level"],
            default_profile["vip_status"], default_profile["total_matches"],
            default_profile["total_chat_time"], default_profile["is_blocked"],
            default_profile["is_guest"], default_profile["gender"],
            default_profile["location"], default_profile["bio"]
        )
        
        await db.execute(query, params)
        return await UserRepository.get_by_telegram_id(telegram_id)

    @staticmethod
    async def update(telegram_id: int, **kwargs) -> bool:
        """Update user profile fields."""
        if not kwargs:
            return False
            
        # Separate top-level DB columns from extra JSON data
        db_columns = [
            'username', 'first_name', 'gender', 'location', 'bio', 'profile_photo',
            'coins', 'xp', 'level', 'vip_status', 'total_matches', 'total_chat_time',
            'daily_streak', 'weekly_streak', 'monthly_streak', 'last_login', 
            'last_active', 'is_blocked', 'is_guest'
        ]
        
        updates = []
        params = []
        extra_data = {}
        
        for key, value in kwargs.items():
            if key in db_columns:
                updates.append(f"{key} = ?")
                params.append(value)
            else:
                extra_data[key] = value
                
        if extra_data:
            # Fetch current JSON data to merge
            current = await UserRepository.get_by_telegram_id(telegram_id)
            if current:
                # Filter out top-level columns from current to get only existing JSON data
                existing_extra = {k: v for k, v in current.items() if k not in db_columns and k != 'id' and k != 'telegram_id'}
                existing_extra.update(extra_data)
                updates.append("json_data = ?")
                params.append(orjson.dumps(existing_extra).decode())
        
        if not updates:
            return False
            
        params.append(telegram_id)
        query = f"UPDATE users SET {', '.join(updates)} WHERE telegram_id = ?"
        await db.execute(query, tuple(params))
        return True

    @staticmethod
    async def increment_coins(telegram_id: int, amount: int) -> bool:
        """Atomically increment user coins."""
        query = "UPDATE users SET coins = coins + ? WHERE telegram_id = ?"
        await db.execute(query, (amount, telegram_id))
        return True

    @staticmethod
    async def increment_xp(telegram_id: int, amount: int) -> bool:
        """Atomically increment user XP."""
        query = "UPDATE users SET xp = xp + ? WHERE telegram_id = ?"
        await db.execute(query, (amount, telegram_id))
        return True

    @staticmethod
    async def set_blocked(telegram_id: int, status: bool) -> bool:
        """Set user blocked status."""
        query = "UPDATE users SET is_blocked = ? WHERE telegram_id = ?"
        await db.execute(query, (1 if status else 0, telegram_id))
        return True
