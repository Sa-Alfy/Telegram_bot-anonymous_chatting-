import asyncio
import time
import json
import os
from pyrogram import Client
from utils.logger import logger
from services.distributed_state import distributed_state
from state.match_state import match_state
from utils.helpers import send_cross_platform
from database.connection import db

async def start_admin_worker(app: Client):
    """Listens for commands from the Web Admin API via Redis."""
    if not distributed_state.redis:
        logger.warning("Admin Worker: Redis not connected. Skipping command listener.")
        return

    logger.info("🛠 Admin Worker started - Listening for Web API commands.")
    
    # Create consumer group if not exists
    try:
        await distributed_state.redis.xgroup_create("admin:commands", "bot_worker", id="0", mkstream=True)
    except Exception as e:
        if "BUSYGROUP" not in str(e):
            logger.debug(f"Admin Worker group creation info: {e}")

    consumer_name = f"bot_{os.getpid()}"

    while True:
        try:
            # Block for new commands
            streams = await distributed_state.redis.xreadgroup(
                "bot_worker", consumer_name, {"admin:commands": ">"}, count=1, block=5000
            )

            if streams:
                for stream, events in streams:
                    for message_id, payload in events:
                        action = payload.get("action")
                        logger.info(f"Admin Worker: Received action {action}")
                        
                        if action == "BROADCAST":
                            text = payload.get("text")
                            if text:
                                await handle_broadcast(app, text)
                        
                        elif action == "NOTIFY_USER":
                            uid = payload.get("user_id")
                            text = payload.get("text")
                            if uid and text:
                                await send_cross_platform(app, uid, text)
                        
                        elif action == "RESET_SYSTEM":
                            await match_state.clear_all()
                            logger.warning("Admin Worker: FULL SYSTEM RESET executed via Web API.")

                        # Acknowledge
                        await distributed_state.redis.xack("admin:commands", "bot_worker", message_id)

        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Error in admin worker loop: {e}")
            await asyncio.sleep(5)

async def handle_broadcast(app: Client, text: str):
    """Executes a global broadcast."""
    users = await db.fetchall("SELECT telegram_id FROM users")
    logger.info(f"Admin Worker: Starting broadcast to {len(users)} users...")
    
    count = 0
    for user in users:
        uid = user['telegram_id']
        try:
            success = await send_cross_platform(app, uid, text)
            if success:
                count += 1
            if count % 30 == 0:
                await asyncio.sleep(1) # Simple rate limit
        except Exception:
            pass
            
    logger.info(f"Admin Worker: Broadcast complete. Delivered to {count}/{len(users)} users.")
