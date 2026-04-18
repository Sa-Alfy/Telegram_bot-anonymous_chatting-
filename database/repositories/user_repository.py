import time
import orjson
from typing import Dict, Any, Optional, List
from database.connection import db

class UserRepository:
    @staticmethod
    async def get_by_telegram_id(telegram_id: int) -> Optional[Dict[str, Any]]:
        """Fetch a user profile by Telegram ID with NULL-safety sanitisation."""
        row = await db.fetchone("SELECT * FROM users WHERE telegram_id = $1", (telegram_id,))
        if not row:
            return None
        
        user_data = dict(row)
        
        # Skip soft-deleted users
        if user_data.get("data_deleted_at"):
            return None
        
        # --- NULL-Safety Sanitisation ---
        # Ensure numeric fields are never None
        numeric_fields = {
            "coins": 10, "xp": 0, "level": 1, "vip_status": False,
            "total_matches": 0, "total_chat_time": 0, "daily_streak": 0,
            "weekly_streak": 0, "monthly_streak": 0, "last_login": 0,
            "last_active": 0, "is_blocked": False, "is_guest": True, "reports": 0,
            "consent_given_at": 0, "data_deleted_at": 0,
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
            except Exception as e:
                import logging
                logging.getLogger(__name__).warning(f"Corrupt json_data for user {telegram_id}: {e}")
                pass
        return user_data

    @staticmethod
    async def create(telegram_id: int, username: str = None, first_name: str = None) -> Dict[str, Any]:
        """Create a new user with default settings."""
        default_profile = {
            "coins": 10,
            "xp": 0,
            "level": 1,
            "vip_status": False,
            "total_matches": 0,
            "total_chat_time": 0,
            "is_blocked": False,
            "is_guest": True,
            "gender": "Not specified",
            "location": "Secret",
            "bio": "No bio provided."
        }
        
        query = """
        INSERT INTO users (telegram_id, username, first_name, coins, xp, level, vip_status, total_matches, total_chat_time, is_blocked, is_guest, gender, location, bio)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14)
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
        """Update user profile fields.
        H3: JSON fields are merged atomically at DB level (no read-modify-write race).
        """
        if not kwargs:
            return False
            
        # Separate top-level DB columns from extra JSON data
        db_columns = [
            'username', 'first_name', 'gender', 'location', 'bio', 'profile_photo',
            'coins', 'xp', 'level', 'vip_status', 'total_matches', 'total_chat_time',
            'daily_streak', 'weekly_streak', 'monthly_streak', 'last_login', 
            'last_active', 'is_blocked', 'is_guest', 'reports', 'last_partner_id',
            'consent_given_at', 'data_deleted_at',
        ]
        
        updates = []
        params = []
        extra_data = {}
        
        for key, value in kwargs.items():
            if key in db_columns:
                params.append(value)
                updates.append(f"{key} = ${len(params)}")
            else:
                extra_data[key] = value
                
        if extra_data:
            # H3: Atomic DB-side merge — no Python read required, no race condition.
            # COALESCE ensures an empty object if json_data is NULL.
            params.append(orjson.dumps(extra_data).decode())
            updates.append(
                f"json_data = COALESCE(json_data::jsonb, '{{}}'::jsonb) || ${len(params)}::jsonb"
            )
        
        if not updates:
            return False
            
        params.append(telegram_id)
        query = f"UPDATE users SET {', '.join(updates)} WHERE telegram_id = ${len(params)}"
        await db.execute(query, tuple(params))
        return True

    @staticmethod
    async def increment_coins(telegram_id: int, amount: int) -> int:
        """Atomically increment user coins and return new value."""
        row = await db.fetchone(
            "UPDATE users SET coins = coins + $1 WHERE telegram_id = $2 RETURNING coins",
            (amount, telegram_id)
        )
        return row["coins"] if row else 0

    @staticmethod
    async def increment_xp(telegram_id: int, amount: int) -> int:
        """Atomically increment user XP and return new value."""
        row = await db.fetchone(
            "UPDATE users SET xp = xp + $1 WHERE telegram_id = $2 RETURNING xp",
            (amount, telegram_id)
        )
        return row["xp"] if row else 0

    @staticmethod
    async def set_blocked(telegram_id: int, status: bool) -> bool:
        """Set user blocked status."""
        query = "UPDATE users SET is_blocked = $1 WHERE telegram_id = $2"
        await db.execute(query, (bool(status), telegram_id))
        return True

    # ─────────────────────────────────────────────────────────────────
    # Consent Management (Meta compliance)
    # ─────────────────────────────────────────────────────────────────

    @staticmethod
    async def set_consent(telegram_id: int) -> bool:
        """Record that user has accepted privacy policy and ToS."""
        query = "UPDATE users SET consent_given_at = $1 WHERE telegram_id = $2"
        await db.execute(query, (int(time.time()), telegram_id))
        return True

    @staticmethod
    async def has_consent(telegram_id: int) -> bool:
        """Check if user has given consent."""
        row = await db.fetchone(
            "SELECT consent_given_at FROM users WHERE telegram_id = $1", (telegram_id,)
        )
        if not row:
            return False
        return bool(row.get("consent_given_at"))

    # ─────────────────────────────────────────────────────────────────
    # Soft Data Deletion (GDPR / Meta compliance)
    # ─────────────────────────────────────────────────────────────────

    @staticmethod
    async def soft_delete_user_data(telegram_id: int) -> bool:
        """Anonymize user data — soft deletion per GDPR right to erasure.
        
        Nullifies all PII fields but retains the row for abuse-tracking purposes.
        """
        now = int(time.time())
        query = """
        UPDATE users SET
            username = NULL,
            first_name = NULL,
            gender = 'Deleted',
            location = 'Deleted',
            bio = 'Deleted',
            profile_photo = NULL,
            coins = 0,
            xp = 0,
            level = 0,
            vip_status = false,
            total_matches = 0,
            total_chat_time = 0,
            daily_streak = 0,
            weekly_streak = 0,
            monthly_streak = 0,
            last_login = 0,
            last_active = 0,
            is_guest = true,
            last_partner_id = NULL,
            json_data = '{}',
            data_deleted_at = $1
        WHERE telegram_id = $2
        """
        await db.execute(query, (now, telegram_id))
        
        # Also clean up related tables
        await db.execute("DELETE FROM friends WHERE user_id = $1 OR friend_id = $1", (telegram_id,))
        await db.execute("DELETE FROM blocked_users WHERE blocker_id = $1 OR blocked_id = $1", (telegram_id,))
        await db.execute("DELETE FROM reveal_history WHERE revealer_id = $1 OR revealed_id = $1", (telegram_id,))
        
        # H4: Clean up Redis state so deleted user doesn't linger in active queues/sessions
        try:
            from services.distributed_state import distributed_state
            await distributed_state.remove_from_queue(telegram_id)
            await distributed_state.clear_partner(telegram_id)
            await distributed_state.set_user_state(telegram_id, None)
            if distributed_state.redis:
                # Remove all interaction dedup keys for this user
                interact_keys = await distributed_state.redis.keys(f"interact:{telegram_id}:*")
                if interact_keys:
                    await distributed_state.redis.delete(*interact_keys)
                # Remove session timing
                await distributed_state.redis.delete(f"chat_start:{telegram_id}")
        except Exception as e:
            import logging as _log
            _log.getLogger(__name__).warning(f"Redis cleanup in soft_delete failed for {telegram_id}: {e}")
        
        import logging
        logging.getLogger(__name__).info(f"Soft-deleted user data for ID ending ...{str(telegram_id)[-4:]}")
        return True

    # ─────────────────────────────────────────────────────────────────
    # Grandfathering migration (run once)
    # ─────────────────────────────────────────────────────────────────

    @staticmethod
    async def grandfather_existing_users() -> int:
        """Mark all existing users as consented (grandfathering).
        
        Only updates users who have no consent_given_at value set.
        Returns the number of users updated.
        """
        now = int(time.time())
        cursor = await db.execute(
            "UPDATE users SET consent_given_at = $1 WHERE consent_given_at IS NULL AND data_deleted_at IS NULL",
            (now,)
        )
        return cursor.rowcount
