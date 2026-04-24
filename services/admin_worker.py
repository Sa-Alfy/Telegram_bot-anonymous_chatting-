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
                        
                        elif action == "GIFT_COINS":
                            uid = payload.get("user_id")
                            amount = payload.get("amount", 0)
                            if uid and amount:
                                from database.repositories.user_repository import UserRepository
                                await UserRepository.increment_coins(uid, amount)
                                await send_cross_platform(app, uid, f"🎁 **Gift Received!**\nAn admin has gifted you **{amount} coins**. Enjoy!")
                        
                        elif action == "BAN_USER":
                            uid = payload.get("user_id")
                            banned = payload.get("banned", True)
                            if uid:
                                from database.repositories.user_repository import UserRepository
                                await UserRepository.set_blocked(uid, banned)
                                if banned:
                                    await send_cross_platform(app, uid, "🚫 **Account Banned**\nYour account has been restricted by an administrator.")
                                else:
                                    await send_cross_platform(app, uid, "✅ **Account Unbanned**\nYour account restrictions have been lifted.")

                        elif action == "SET_VIP":
                            uid = payload.get("user_id")
                            is_vip = payload.get("vip", True)
                            if uid:
                                from database.repositories.user_repository import UserRepository
                                await UserRepository.update(uid, vip_status=is_vip)
                                status_str = "ENABLED" if is_vip else "DISABLED"
                                await send_cross_platform(app, uid, f"💎 **VIP Status Update**\nYour VIP status has been **{status_str}** by an administrator.")
                        
                        elif action == "NOTIFY_USER":
                            uid = payload.get("user_id")
                            text = payload.get("text")
                            if uid and text:
                                await send_cross_platform(app, uid, text)

                        # Acknowledge
                        await distributed_state.redis.xack("admin:commands", "bot_worker", message_id)

        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Error in admin worker loop: {e}")
            await asyncio.sleep(5)

async def handle_broadcast(app, text):
    try:
        users = await db.fetchall("SELECT telegram_id FROM users")
        logger.info(f"📢 Starting broadcast to {len(users)} users.")
        
        # Parallelize with a semaphore to avoid hitting platform rate limits too hard
        # and to keep the loop responsive.
        sem = asyncio.Semaphore(20) 
        
        async def safe_send(uid):
            async with sem:
                try:
                    await send_cross_platform(app, uid, text)
                except Exception:
                    pass

        tasks = [safe_send(user['telegram_id']) for user in users]
        await asyncio.gather(*tasks)
        logger.info(f"✅ Broadcast complete for {len(users)} users.")
    except Exception as e:
        logger.error(f"❌ Broadcast handler failed: {e}")
