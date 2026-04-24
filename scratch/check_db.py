import asyncio
from database.connection import db
import os

async def check():
    await db.connect()
    try:
        # Check users table
        row = await db.fetchone("SELECT * FROM users LIMIT 1")
        if row:
            print(f"Columns: {list(row.keys())}")
        else:
            print("Table empty, checking schema directly...")
            res = await db.fetchall("SELECT column_name FROM information_schema.columns WHERE table_name = 'users'")
            print(f"Columns: {[r['column_name'] for r in res]}")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        await db.close()

if __name__ == '__main__':
    asyncio.run(check())
