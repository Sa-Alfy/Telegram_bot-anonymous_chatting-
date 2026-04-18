import time
from typing import Dict, Any, List
from database.connection import db

class StatsRepository:
    @staticmethod
    async def get_user_stats(telegram_id: int) -> Dict[str, Any]:
        """Fetch all stats for a specific user for the stats screen."""
        query = "SELECT * FROM users WHERE telegram_id = $1"
        row = await db.fetchone(query, (telegram_id,))
        return dict(row) if row else {}

    @staticmethod
    async def get_leaderboard(category: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Fetch the top users for a specific leaderboard category."""
        order_by = {
            "all": "xp DESC",
            "weekly": "xp DESC", # Simplification for now
            "daily": "xp DESC",
            "hourly": "xp DESC",
            "vip": "xp DESC"
        }
        
        # Filter logic
        where_clause = ""
        if category == "vip":
            where_clause = "WHERE vip_status = true"
        
        sort_field = order_by.get(category, "xp DESC")
        query = f"SELECT telegram_id, first_name, xp, level, vip_status FROM users {where_clause} ORDER BY {sort_field} LIMIT $1"
        rows = await db.fetchall(query, (limit,))
        return [dict(row) for row in rows]

    @staticmethod
    async def get_top_event_participants(event_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Fetch top participants for a specific seasonal event."""
        # PostgreSQL jsonb extraction
        query = "SELECT telegram_id, first_name, (json_data::jsonb->>'event_points')::int as points FROM users WHERE json_data::jsonb->>'current_event_id' = $1 ORDER BY points DESC LIMIT $2"
        rows = await db.fetchall(query, (event_id, limit))
        return [dict(row) for row in rows]
