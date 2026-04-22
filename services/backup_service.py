import os
import asyncio
import aiosqlite
from utils.logger import logger
from datetime import datetime
from database.connection import db

async def start_backup_service():
    """Runs a background task to backup the SQLite database automatically using safe SQLite native backup."""
    data_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data"))
    backup_dir = os.path.join(data_dir, "backups")
    
    os.makedirs(backup_dir, exist_ok=True)
    logger.info("💾 Backup service initialized. Next backup in 12 hours.")
    
    while True:
        try:
            # Wait 12 hours between backups (43200 seconds)
            await asyncio.sleep(43200) 
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_file = os.path.join(backup_dir, f"bot_database_{timestamp}.db")
            
            # Use native SQLite safe-backup via aiosqlite
            if db._connection:
                async with aiosqlite.connect(backup_file) as dest_db:
                    await db._connection.backup(dest_db)
            
                logger.info(f"💾 Automated Database Backup created: {backup_file}")
            
            # Keep only the last 14 backups (1 week worth if 12h)
            backups = sorted([f for f in os.listdir(backup_dir) if f.startswith("bot_database_")])
            if len(backups) > 14:
                oldest = os.path.join(backup_dir, backups[0])
                os.remove(oldest)
                logger.info(f"🗑️ Deleted old backup: {backups[0]}")
                
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"❌ Backup failed: {e}")
            await asyncio.sleep(60) # Prevent tight crash loops
