import time
from typing import Dict, Any, Optional, List
from database.connection import db

class AdminRepository:
    @staticmethod
    async def log_action(admin_id: int, action: str, target_user_id: int = None, details: str = None) -> int:
        """Log an administrative action to the audit logs."""
        query = "INSERT INTO audit_logs (admin_id, action, target_user_id, details, timestamp) VALUES ($1, $2, $3, $4, $5) RETURNING log_id"
        params = (admin_id, action, target_user_id, details, int(time.time()))
        return await db.fetchval(query, params)

    @staticmethod
    async def get_audit_logs(limit: int = 50) -> List[Dict[str, Any]]:
        """Fetch historical audit logs for admins."""
        query = "SELECT * FROM audit_logs ORDER BY timestamp DESC LIMIT $1"
        rows = await db.fetchall(query, (limit,))
        return [dict(row) for row in rows]

    @staticmethod
    async def get_banned_users() -> List[Dict[str, Any]]:
        """Fetch all users currently blocked by admins."""
        query = "SELECT telegram_id, username, first_name, is_blocked FROM users WHERE is_blocked = true"
        rows = await db.fetchall(query)
        return [dict(row) for row in rows]

    @staticmethod
    async def get_system_stats() -> Dict[str, Any]:
        """Fetch high-level statistics for the admin dashboard."""
        stats = {}
        
        # Total Users
        row = await db.fetchone("SELECT COUNT(*) as count FROM users")
        stats['total_users'] = row['count']
        
        # Total Active Sessions (last 24h)
        last_24h = int(time.time()) - 86400
        row = await db.fetchone("SELECT COUNT(*) as count FROM sessions WHERE start_time > $1", (last_24h,))
        stats['sessions_24h'] = row['count']
        
        # Pending Reports
        row = await db.fetchone("SELECT COUNT(*) as count FROM reports_bans WHERE status = 'pending'")
        stats['pending_reports'] = row['count']
        
        return stats
