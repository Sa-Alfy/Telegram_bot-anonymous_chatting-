import time
from typing import List
from database.connection import db


class BlockedRepository:
    """Repository for the blocked_users table — per-user block lists."""

    @staticmethod
    async def block_user(blocker_id: int, blocked_id: int) -> bool:
        """Add a user to the blocker's block list."""
        query = """
        INSERT INTO blocked_users (blocker_id, blocked_id, created_at)
        VALUES ($1, $2, $3)
        ON CONFLICT (blocker_id, blocked_id) DO NOTHING
        """
        await db.execute(query, (blocker_id, blocked_id, int(time.time())))
        return True

    @staticmethod
    async def unblock_user(blocker_id: int, blocked_id: int) -> bool:
        """Remove a user from the blocker's block list."""
        cursor = await db.execute(
            "DELETE FROM blocked_users WHERE blocker_id = $1 AND blocked_id = $2",
            (blocker_id, blocked_id)
        )
        return cursor.rowcount > 0

    @staticmethod
    async def is_blocked(blocker_id: int, blocked_id: int) -> bool:
        """Check if blocker_id has blocked blocked_id."""
        row = await db.fetchone(
            "SELECT 1 FROM blocked_users WHERE blocker_id = $1 AND blocked_id = $2",
            (blocker_id, blocked_id)
        )
        return row is not None

    @staticmethod
    async def is_mutually_blocked(user1: int, user2: int) -> bool:
        """Check if either user has blocked the other (used in matchmaking)."""
        row = await db.fetchone(
            """SELECT 1 FROM blocked_users 
               WHERE (blocker_id = $1 AND blocked_id = $2)
                  OR (blocker_id = $2 AND blocked_id = $1)""",
            (user1, user2)
        )
        return row is not None

    @staticmethod
    async def get_blocked_list(blocker_id: int) -> List[int]:
        """Get all user IDs blocked by this user."""
        rows = await db.fetchall(
            "SELECT blocked_id FROM blocked_users WHERE blocker_id = $1",
            (blocker_id,)
        )
        return [row["blocked_id"] for row in rows]

    @staticmethod
    async def get_blocked_by_list(blocked_id: int) -> List[int]:
        """Get all user IDs who have blocked this user."""
        rows = await db.fetchall(
            "SELECT blocker_id FROM blocked_users WHERE blocked_id = $1",
            (blocked_id,)
        )
        return [row["blocker_id"] for row in rows]
