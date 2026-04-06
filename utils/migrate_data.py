import sqlite3
import os
import json

old_db = "f:/Code/Python Code/telegrame dating/anonymous_chat_bot/data/users.db"
new_db = "f:/Code/Python Code/telegrame dating/anonymous_chat_bot/data/bot_database.db"

def migrate():
    if not os.path.exists(old_db):
        print(f"Error: {old_db} not found. Nothing to migrate.")
        return

    # Connect to both databases
    conn_old = sqlite3.connect(old_db)
    conn_old.row_factory = sqlite3.Row
    cursor_old = conn_old.cursor()
    
    conn_new = sqlite3.connect(new_db)
    cursor_new = conn_new.cursor()
    
    # 1. Fetch all users from old database
    cursor_old.execute("SELECT * FROM users")
    old_users = cursor_old.fetchall()
    print(f"Found {len(old_users)} users to migrate.")
    
    migrated_count = 0
    for user_row in old_users:
        user = dict(user_row)
        try:
            # Map columns
            # Old: user_id, first_name, gender, location, bio, profile_photo, is_guest, coins, xp, level, vip, matches, total_chat_time, daily_streak, weekly_streak, monthly_streak, last_active, blocked, reports, last_partner_id, json_data
            
            # New: telegram_id, username, first_name, gender, location, bio, profile_photo, coins, xp, level, vip_status, total_matches, total_chat_time, daily_streak, weekly_streak, monthly_streak, last_login, last_active, is_blocked, is_guest, json_data
            
            data = (
                user['user_id'],
                user.get('username', f"stranger_{user['user_id']}"),
                user['first_name'],
                user['gender'],
                user['location'],
                user['bio'],
                user['profile_photo'],
                user['coins'],
                user['xp'],
                user['level'],
                user['vip'],
                user['matches'],
                user['total_chat_time'],
                user['daily_streak'],
                user['weekly_streak'],
                user['monthly_streak'],
                user.get('last_login', user['last_active']),
                user['last_active'],
                user['blocked'],
                user['is_guest'],
                user['json_data']
            )
            
            # Use 'id' for the unique constraint check if id was telegram_id previously
            # But here telegram_id is the unique one.
            
            query = """
            INSERT OR REPLACE INTO users (
                telegram_id, username, first_name, gender, location, bio, profile_photo,
                coins, xp, level, vip_status, total_matches, total_chat_time,
                daily_streak, weekly_streak, monthly_streak, last_login, last_active,
                is_blocked, is_guest, json_data
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """
            
            cursor_new.execute(query, data)
            migrated_count += 1
        except Exception as e:
            print(f"Failed to migrate user {user['user_id']}: {e}")
            
    conn_new.commit()
    print(f"Successfully migrated {migrated_count} users to the new database.")
    
    conn_old.close()
    conn_new.close()

if __name__ == "__main__":
    migrate()
