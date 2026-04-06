import time
from typing import Dict, Any, Optional, List
from database.connection import db

class SessionRepository:
    @staticmethod
    async def create(user1_id: int, user2_id: int) -> int:
        """Create a new chat session."""
        query = "INSERT INTO sessions (user1_id, user2_id, start_time) VALUES (?, ?, ?)"
        params = (user1_id, user2_id, int(time.time()))
        cursor = await db.execute(query, params)
        return cursor.lastrowid

    @staticmethod
    async def end_session(session_id: int, duration: int, coins1: int, coins2: int, xp1: int, xp2: int) -> bool:
        """Close a chat session with final stats."""
        query = """
        UPDATE sessions 
        SET end_time = ?, duration_seconds = ?, 
            coins_earned1 = ?, coins_earned2 = ?, 
            xp_earned1 = ?, xp_earned2 = ?
        WHERE session_id = ?
        """
        params = (int(time.time()), duration, coins1, coins2, xp1, xp2, session_id)
        await db.execute(query, params)
        return True

    @staticmethod
    async def get_user_sessions(telegram_id: int, limit: int = 10) -> List[Dict[str, Any]]:
        """Fetch historical sessions for a user."""
        query = """
        SELECT * FROM sessions 
        WHERE user1_id = ? OR user2_id = ? 
        ORDER BY start_time DESC LIMIT ?
        """
        rows = await db.fetchall(query, (telegram_id, telegram_id, limit))
        return [dict(row) for row in rows]
