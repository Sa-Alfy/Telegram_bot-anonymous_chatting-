import time
from typing import Dict, Any, Optional, List
from database.connection import db

class ReportRepository:
    @staticmethod
    async def create(reporter_id: int, reported_id: int, reason: str = None) -> int:
        """Create a new user report."""
        query = "INSERT INTO reports_bans (reporter_id, reported_id, reason, timestamp) VALUES ($1, $2, $3, $4) RETURNING report_id"
        params = (reporter_id, reported_id, reason, int(time.time()))
        return await db.fetchval(query, params)

    @staticmethod
    async def get_pending_reports() -> List[Dict[str, Any]]:
        """Fetch all pending reports for admin review."""
        query = "SELECT * FROM reports_bans WHERE status = 'pending' ORDER BY timestamp ASC"
        rows = await db.fetchall(query)
        return [dict(row) for row in rows]

    @staticmethod
    async def update_status(report_id: int, status: str, admin_id: int) -> bool:
        """Update report status after admin review."""
        query = "UPDATE reports_bans SET status = $1, admin_review_id = $2 WHERE report_id = $3"
        params = (status, admin_id, report_id)
        await db.execute(query, params)
        return True

    @staticmethod
    async def create_appeal(user_id: int, reason: str) -> int:
        """Create a user appeal for a ban."""
        query = "INSERT INTO appeals (user_id, reason, timestamp) VALUES ($1, $2, $3) RETURNING appeal_id"
        params = (user_id, reason, int(time.time()))
        return await db.fetchval(query, params)

    @staticmethod
    async def get_pending_appeals() -> List[Dict[str, Any]]:
        """Fetch all pending appeals for admin review."""
        query = "SELECT * FROM appeals WHERE status = 'pending' ORDER BY timestamp ASC"
        rows = await db.fetchall(query)
        return [dict(row) for row in rows]
