import time
from typing import Dict, Any, List
from database.connection import db

class GiftRepository:
    @staticmethod
    async def log_gift(sender_id: int, receiver_id: int, gift_type: str, cost: int) -> int:
        """Logs a gift sent between users."""
        query = """
        INSERT INTO user_gifts (sender_id, receiver_id, gift_type, cost, timestamp)
        VALUES ($1, $2, $3, $4, $5) RETURNING id
        """
        params = (sender_id, receiver_id, gift_type, cost, int(time.time()))
        return await db.fetchval(query, params)

    @staticmethod
    async def get_user_gifts_received(user_id: int) -> List[Dict[str, Any]]:
        """Fetch all gifts received by this user."""
        query = "SELECT * FROM user_gifts WHERE receiver_id = $1 ORDER BY timestamp DESC"
        rows = await db.fetchall(query, (user_id,))
        return [dict(row) for row in rows]

    @staticmethod
    async def get_user_gifts_sent(user_id: int) -> List[Dict[str, Any]]:
        """Fetch all gifts sent by this user."""
        query = "SELECT * FROM user_gifts WHERE sender_id = $1 ORDER BY timestamp DESC"
        rows = await db.fetchall(query, (user_id,))
        return [dict(row) for row in rows]

    @staticmethod
    async def get_top_receivers(limit: int = 10) -> List[Dict[str, Any]]:
        """Gets the top gift receivers for leaderboards."""
        query = """
        SELECT receiver_id, COUNT(*) as gift_count, SUM(cost) as total_value
        FROM user_gifts
        GROUP BY receiver_id
        ORDER BY total_value DESC
        LIMIT $1
        """
        rows = await db.fetchall(query, (limit,))
        return [dict(row) for row in rows]
