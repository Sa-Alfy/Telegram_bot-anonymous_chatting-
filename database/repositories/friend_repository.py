import time
from typing import List, Dict, Any, Optional
from database.connection import db
from utils.logger import logger

class FriendRepository:
    @staticmethod
    async def send_request(user_id: int, friend_id: int) -> bool:
        """Logs a pending friend request."""
        try:
            # Check if relationship already exists
            query = "SELECT status FROM friends WHERE (user_id = ? AND friend_id = ?) OR (user_id = ? AND friend_id = ?)"
            existing = await db.fetchone(query, (user_id, friend_id, friend_id, user_id))
            
            if existing:
                return False # Already friends or request pending
                
            query = "INSERT INTO friends (user_id, friend_id, status, created_at) VALUES (?, ?, 'pending', ?)"
            await db.execute(query, (user_id, friend_id, int(time.time())))
            return True
        except Exception as e:
            logger.error(f"Error sending friend request: {e}")
            return False

    @staticmethod
    async def accept_request(user_id: int, friend_id: int) -> bool:
        """Finalizes a friend request."""
        try:
            query = "UPDATE friends SET status = 'accepted' WHERE (user_id = ? AND friend_id = ?) OR (user_id = ? AND friend_id = ?)"
            await db.execute(query, (friend_id, user_id, user_id, friend_id))
            return True
        except Exception as e:
            logger.error(f"Error accepting friend request: {e}")
            return False

    @staticmethod
    async def get_friends_list(user_id: int) -> List[Dict[str, Any]]:
        """Retrieves all accepted friends for a user."""
        query = """
            SELECT u.* FROM users u
            JOIN friends f ON (f.user_id = u.telegram_id OR f.friend_id = u.telegram_id)
            WHERE (f.user_id = ? OR f.friend_id = ?) AND f.status = 'accepted' AND u.telegram_id != ?
        """
        rows = await db.fetchall(query, (user_id, user_id, user_id))
        return [dict(row) for row in rows]

    @staticmethod
    async def is_friend(user_id: int, friend_id: int) -> bool:
        """Checks if two users are currently friends."""
        query = "SELECT 1 FROM friends WHERE ((user_id = ? AND friend_id = ?) OR (user_id = ? AND friend_id = ?)) AND status = 'accepted'"
        row = await db.fetchone(query, (user_id, friend_id, friend_id, user_id))
        return row is not None

    @staticmethod
    async def has_pending_request(user_id: int, friend_id: int) -> bool:
        """Checks if there is a pending request between two users."""
        query = "SELECT 1 FROM friends WHERE ((user_id = ? AND friend_id = ?) OR (user_id = ? AND friend_id = ?)) AND status = 'pending'"
        row = await db.fetchone(query, (user_id, friend_id, friend_id, user_id))
        return row is not None

    @staticmethod
    async def get_incoming_requests(user_id: int) -> List[Dict[str, Any]]:
        """Retrieves all pending requests sent TO the user."""
        query = """
            SELECT u.* FROM users u
            JOIN friends f ON f.user_id = u.telegram_id
            WHERE f.friend_id = ? AND f.status = 'pending'
        """
        rows = await db.fetchall(query, (user_id,))
        return [dict(row) for row in rows]

    @staticmethod
    async def decline_request(user_id: int, sender_id: int) -> bool:
        """Removes a pending friend request."""
        try:
            query = "DELETE FROM friends WHERE user_id = ? AND friend_id = ? AND status = 'pending'"
            await db.execute(query, (sender_id, user_id))
            return True
        except Exception as e:
            logger.error(f"Error declining friend request: {e}")
            return False
