import asyncio
import os
import sys
import traceback
from pyrogram import Client
from config import API_ID, API_HASH, BOT_TOKEN, ADMIN_ID
from database.connection import db
from utils.logger import logger
from state.match_state import match_state

def setup_exception_handler(app: Client):
    def handle_exception(loop, context):
        msg = context.get("exception", context["message"])
        logger.error(f"Caught background exception: {msg}")
        exc_info = ""
        if "exception" in context:
            exc_info = "".join(traceback.format_exception(type(context["exception"]), context["exception"], context["exception"].__traceback__))
            logger.error(exc_info)
            
        if app.is_initialized and getattr(app, "is_connected", True):
            async def send_alert():
                try:
                    alert = f"🚨 **SYSTEM CRASH** 🚨\n\n**Error:** `{msg}`\n```python\n{exc_info[:3800]}\n```"
                    await app.send_message(chat_id=int(ADMIN_ID), text=alert)
                except Exception:
                    pass
            try:
                asyncio.create_task(send_alert())
            except RuntimeError:
                pass

    return handle_exception

async def main():
    if not all([API_ID, API_HASH, BOT_TOKEN]):
        logger.error("Missing API_ID, API_HASH, or BOT_TOKEN in .env")
        return

    # Initialize async database
    await db.connect()

    # Determine script and parent paths for robust plugin loading
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(script_dir) # Change working directory to ensure plugin root "handlers" is found
    
    parent_dir = os.path.dirname(script_dir)
    if parent_dir not in sys.path:
        sys.path.insert(0, parent_dir)
    if script_dir not in sys.path:
        sys.path.insert(0, script_dir)

    # Initialize bot client
    app = Client(
        "anonymous_bot",
        api_id=int(API_ID),
        api_hash=API_HASH,
        bot_token=BOT_TOKEN,
        plugins=dict(root="handlers"),
        workdir=script_dir
    )

    # Start session manager background tasks
    from services.session_manager import start_session_manager
    from services.event_manager import start_event_manager
    from services.backup_service import start_backup_service
    
    # Run background tasks with exception handling
    loop = asyncio.get_event_loop()
    loop.set_exception_handler(setup_exception_handler(app))
    
    asyncio.create_task(start_session_manager(app))
    asyncio.create_task(start_event_manager(app))
    asyncio.create_task(start_backup_service())

    logger.info("🤖 **Production-Grade Anonymous Bot** started successfully!")
    await app.start()
    
    # Keep the bot running
    try:
        await asyncio.Event().wait()
    except (KeyboardInterrupt, SystemExit):
        logger.info("🛑 Received shutdown signal. Initiating graceful shutdown...")
    finally:
        # Graceful Shutdown Sequence: Notify active users
        active_users = set(match_state.active_chats.keys()) | set(match_state.waiting_queue)
        if active_users:
            logger.info(f"Notifying {len(active_users)} active users of restart...")
        
        for uid in active_users:
            try:
                await app.send_message(
                    chat_id=uid,
                    text="🔄 **Bot Restarting!**\n\nThe bot is restarting for an update or maintenance. Your active chat has been disconnected automatically. Rejoin in a few seconds!"
                )
            except Exception:
                pass
                
        # End all session records
        from services.matchmaking import MatchmakingService
        # Avoid async modification during iteration
        for uid in list(match_state.active_chats.keys()):
            await MatchmakingService.disconnect(uid)

        logger.info("🔌 Closing connections...")
        await db.close()
        await app.stop()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
