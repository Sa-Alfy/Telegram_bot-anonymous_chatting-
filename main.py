from pyrogram import Client
from config import API_ID, API_HASH, BOT_TOKEN
from services.user_service import load_profiles
from utils.logger import logger
import asyncio

async def main():
    if not all([API_ID, API_HASH, BOT_TOKEN]):
        logger.error("Missing API_ID, API_HASH, or BOT_TOKEN in .env")
        return

    # Load persistent data
    await load_profiles()

    # Determine script and parent paths for robust plugin loading
    import os, sys
    script_dir = os.path.dirname(os.path.abspath(__file__))
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
        plugins=dict(root="anonymous_chat_bot.handlers"),
        workdir=script_dir
    )

    # Start session manager background task
    from services.session_manager import start_session_manager
    from services.event_manager import start_event_manager
    asyncio.create_task(start_session_manager(app))
    asyncio.create_task(start_event_manager(app))

    # DEBUG: Test manual import
    try:
        import anonymous_chat_bot.handlers.stats
        logger.info("✅ Manual import of anonymous_chat_bot.handlers.stats successful!")
    except Exception as e:
        logger.error(f"❌ Manual import of anonymous_chat_bot.handlers.stats failed: {e}")

    logger.info("🤖 Anonymous Dating Bot started successfully!")
    await app.start()
    
    # Keep the bot running
    try:
        await asyncio.Event().wait()
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        await app.stop()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
