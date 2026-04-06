import sqlite3
import os
import ujson
from utils.logger import logger

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'users.db')

def get_connection():
    """Returns a SQLite connection with row factory for dictionary access."""
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Initializes the SQLite database with the full schema."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = get_connection()
    cursor = conn.cursor()
    
    # Create users table with all required fields for progression and Guest Mode
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            first_name TEXT,
            gender TEXT,
            location TEXT,
            bio TEXT,
            profile_photo TEXT,
            is_guest INTEGER DEFAULT 1,
            
            coins INTEGER DEFAULT 10,
            xp INTEGER DEFAULT 0,
            level INTEGER DEFAULT 1,
            vip INTEGER DEFAULT 0,
            
            matches INTEGER DEFAULT 0,
            matches_today INTEGER DEFAULT 0,
            matches_this_week INTEGER DEFAULT 0,
            total_chat_time INTEGER DEFAULT 0,
            
            daily_streak INTEGER DEFAULT 0,
            weekly_streak INTEGER DEFAULT 0,
            monthly_streak INTEGER DEFAULT 0,
            last_login INTEGER DEFAULT 0,
            last_active INTEGER DEFAULT 0,
            
            blocked INTEGER DEFAULT 0,
            reports INTEGER DEFAULT 0,
            revealed INTEGER DEFAULT 0,
            last_partner_id INTEGER DEFAULT 0,
            rematch_available INTEGER DEFAULT 0,
            
            json_data TEXT DEFAULT '{}'
        )
    """)
    
    conn.commit()
    conn.close()
    logger.info("📡 SQLite Database initialized successfully.")

# Global connection for reuse in the bot runtime
db_conn = get_connection()
init_db()
