import sqlite3
import os

db_path = "f:/Code/Python Code/telegrame dating/anonymous_chat_bot/data/bot_database.db"

def inspect_new_db():
    if not os.path.exists(db_path):
        print(f"Error: {db_path} not found.")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # List tables
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = cursor.fetchall()
    print(f"Tables in NEW database: {tables}")
    
    if ('users',) in tables:
        cursor.execute(f"PRAGMA table_info(users);")
        columns = cursor.fetchall()
        print(f"\nSchema for users:")
        for col in columns:
            print(f"  {col[1]} ({col[2]})")
            
    conn.close()

if __name__ == "__main__":
    inspect_new_db()
