import sqlite3
import json
import os

db_path = "f:/Code/Python Code/telegrame dating/anonymous_chat_bot/data/users.db"

def inspect_db():
    if not os.path.exists(db_path):
        print(f"Error: {db_path} not found.")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # List tables
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = cursor.fetchall()
    print(f"Tables in old database: {tables}")
    
    for table in tables:
        table_name = table[0]
        cursor.execute(f"PRAGMA table_info({table_name});")
        columns = cursor.fetchall()
        print(f"\nSchema for {table_name}:")
        for col in columns:
            print(f"  {col[1]} ({col[2]})")
            
        cursor.execute(f"SELECT COUNT(*) FROM {table_name};")
        count = cursor.fetchone()[0]
        print(f"Total Rows: {count}")
    
    conn.close()

if __name__ == "__main__":
    inspect_db()
