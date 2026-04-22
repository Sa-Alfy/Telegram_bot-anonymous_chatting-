import time
from typing import Dict, Any, Optional, List
from database.connection import db

class SessionRepository:
    @staticmethod
    async def create(user1_id: int, user2_id: int) -> int:
        """Create a new chat session."""
        query = "INSERT INTO sessions (user1_id, user2_id, start_time) VALUES ($1, $2, $3) RETURNING session_id"
        params = (user1_id, user2_id, int(time.time()))
        return await db.fetchval(query, params)

    @staticmethod
    async def end_session(session_id: int, duration: int, coins1: int, coins2: int, xp1: int, xp2: int) -> bool:
        """Close a chat session with final stats."""
        query = """
        UPDATE sessions 
        SET end_time = $1, duration_seconds = $2, 
            coins_earned1 = $3, coins_earned2 = $4, 
            xp_earned1 = $5, xp_earned2 = $6
        WHERE session_id = $7
        """
        params = (int(time.time()), duration, coins1, coins2, xp1, xp2, session_id)
        await db.execute(query, params)
        return True

    @staticmethod
    async def create_and_end(user1_id: int, user2_id: int, duration: int,
                             coins1: int, coins2: int, xp1: int, xp2: int) -> int:
        """C11: Atomically create and close a session in one transaction.
        Prevents orphaned open sessions if the process crashes between create and end_session.
        """
        now = int(time.time())
        async with db.transaction() as conn:
            session_id = await conn.fetchval(
                "INSERT INTO sessions (user1_id, user2_id, start_time) VALUES ($1, $2, $3) RETURNING session_id",
                user1_id, user2_id, now
            )
            await conn.execute(
                """
                UPDATE sessions
                SET end_time = $1, duration_seconds = $2,
                    coins_earned1 = $3, coins_earned2 = $4,
                    xp_earned1 = $5, xp_earned2 = $6
                WHERE session_id = $7
                """,
                now + duration, duration, coins1, coins2, xp1, xp2, session_id
            )
            return session_id

    @staticmethod
    async def get_user_sessions(telegram_id: int, limit: int = 10) -> List[Dict[str, Any]]:
        """Fetch historical sessions for a user."""
        query = """
        SELECT * FROM sessions 
        WHERE user1_id = $1 OR user2_id = $2 
        ORDER BY start_time DESC LIMIT $3
        """
        rows = await db.fetchall(query, (telegram_id, telegram_id, limit))
        return [dict(row) for row in rows]
