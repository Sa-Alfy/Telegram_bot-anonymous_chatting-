import time
from typing import Dict, Any, List
from database.connection import db

class RevealRepository:
    @staticmethod
    async def log_reveal(revealer_id: int, revealed_id: int, reveal_type: str, cost: int) -> int:
        """Logs a profile reveal event."""
        query = """
        INSERT INTO reveal_history (revealer_id, revealed_id, reveal_type, cost, timestamp)
        VALUES (?, ?, ?, ?, ?)
        """
        params = (revealer_id, revealed_id, reveal_type, cost, int(time.time()))
        cursor = await db.execute(query, params)
        return cursor.lastrowid

    @staticmethod
    async def get_user_reveal_history(user_id: int) -> List[Dict[str, Any]]:
        """Fetch all identities revealed BY this user."""
        query = "SELECT * FROM reveal_history WHERE revealer_id = ? ORDER BY timestamp DESC"
        rows = await db.fetchall(query, (user_id,))
        return [dict(row) for row in rows]

    @staticmethod
    async def get_user_unmasked_by(user_id: int) -> List[Dict[str, Any]]:
        """Fetch who unmasked THIS user."""
        query = "SELECT * FROM reveal_history WHERE revealed_id = ? ORDER BY timestamp DESC"
        rows = await db.fetchall(query, (user_id,))
        return [dict(row) for row in rows]
