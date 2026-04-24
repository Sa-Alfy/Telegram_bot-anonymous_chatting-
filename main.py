# ═══════════════════════════════════════════════════════════════════════
# FILE: main.py  (FULLY REPLACED - Dual-Platform Entry Point)
# PURPOSE: Application entry point — runs Pyrogram (Telegram) + Flask (Messenger)
# STATUS: MODIFIED FROM ORIGINAL
# DEPENDENCIES: All modules in this project + config.py
# ═══════════════════════════════════════════════════════════════════════

import asyncio
import os
import sys
import logging
import threading
import traceback

# ─────────────────────────────────────────────────────────────────────
# Logging setup (must be first)
# ─────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
    ]
)
logger = logging.getLogger(__name__)

# Ensure data directory exists before ANY complex imports to prevent early DB crashes
os.makedirs(os.path.join(os.path.dirname(__file__), 'data'), exist_ok=True)

# ─────────────────────────────────────────────────────────────────────
# Validate required environment variables
# ─────────────────────────────────────────────────────────────────────
from dotenv import load_dotenv
load_dotenv()

# Patch for Python 3.14+ (ensures an event loop exists before Pyrogram imports)
try:
    asyncio.get_running_loop()
except RuntimeError:
    asyncio.set_event_loop(asyncio.new_event_loop())

from config import API_ID, API_HASH, BOT_TOKEN, ADMIN_ID, MESSENGER_ENABLED, PORT, RENDER_EXTERNAL_URL, DATABASE_URL, USE_NGROK
from utils.ngrok_utils import start_ngrok_tunnel, stop_ngrok_tunnel

def _validate_env():
    missing = []
    if not API_ID:    missing.append("API_ID")
    if not API_HASH:  missing.append("API_HASH")
    if not BOT_TOKEN: missing.append("BOT_TOKEN")
    if not DATABASE_URL: missing.append("DATABASE_URL")
    if missing:
        logger.error(
            f"Missing required environment variables: {', '.join(missing)}\n"
            "   Please set them in your .env file or Render dashboard.\n"
            "   See .env.example for reference."
        )
        sys.exit(1)
    if MESSENGER_ENABLED:
        logger.info("Messenger integration ENABLED (PAGE_ACCESS_TOKEN + VERIFY_TOKEN found).")
    else:
        logger.info("Messenger integration DISABLED (PAGE_ACCESS_TOKEN not set — Telegram-only mode).")

_validate_env()

# ─────────────────────────────────────────────────────────────────────
# Import core modules
# ─────────────────────────────────────────────────────────────────────
from pyrogram import Client
from database.connection import db
from utils.logger import logger as bot_logger
from state.match_state import match_state
import app_state

# ─────────────────────────────────────────────────────────────────────
# Crash reporter (sends errors to admin via Telegram)
# ─────────────────────────────────────────────────────────────────────
def setup_exception_handler(pyrogram_app: Client):
    """Attaches a global async exception handler to the event loop."""
    def handle_exception(loop, context):
        msg = context.get("exception", context["message"])
        exc_info = ""
        if "exception" in context:
            exc_info = "".join(traceback.format_exception(
                type(context["exception"]),
                context["exception"],
                context["exception"].__traceback__
            ))
        logger.error(f"Caught background exception: {msg}\n{exc_info}")

        if pyrogram_app.is_initialized and getattr(pyrogram_app, "is_connected", True):
            async def send_alert():
                try:
                    alert = (
                        f"🚨 **SYSTEM CRASH** 🚨\n\n"
                        f"**Error:** `{str(msg)[:500]}`\n"
                        f"```python\n{exc_info[:3500]}\n```"
                    )
                    await pyrogram_app.send_message(chat_id=int(ADMIN_ID), text=alert)
                except Exception:
                    pass
            try:
                asyncio.create_task(send_alert())
            except RuntimeError:
                pass

    return handle_exception


# ─────────────────────────────────────────────────────────────────────
# Flask thread runner
# ─────────────────────────────────────────────────────────────────────
def run_flask_in_thread():
    """Start the Flask webhook server in a background daemon thread."""
    from webhook_server import run_flask
    flask_thread = threading.Thread(target=run_flask, daemon=True, name="FlaskWebhook")
    flask_thread.start()
    logger.info("Flask webhook thread started.")
    return flask_thread


# ─────────────────────────────────────────────────────────────────────
# Keep-alive thread
# ─────────────────────────────────────────────────────────────────────
def run_keep_alive():
    """Start keep-alive pinger if running on Render."""
    if RENDER_EXTERNAL_URL:
        from keep_alive import start_keep_alive
        start_keep_alive()
    else:
        logger.info("Not on Render - keep-alive not started.")


# ─────────────────────────────────────────────────────────────────────
async def start_reconciler_loop():
    """Background task that force-heals desynced states using the Reconciler engine."""
    from core.engine.reconciler import Reconciler
    from state.match_state import match_state
    from services.distributed_state import distributed_state
    import app_state
    
    logger.info("🛠 Reconciler loop started.")
    while True:
        try:
            await asyncio.sleep(60) # Run every minute
            
            # Reconcile waiting queue users
            waiting = await distributed_state.get_queue_candidates()
            for uid in waiting:
                await app_state.reconciler.reconcile_user(uid)

            # Reconcile active chat users
            active_uids = list(match_state.active_chats.keys())
            for uid in active_uids:
                await app_state.reconciler.reconcile_user(uid)
                
        except Exception as e:
            logger.error(f"Reconciler loop error: {e}")
            await asyncio.sleep(10)


# ─────────────────────────────────────────────────────────────────────
# Main async entry point (Pyrogram + background tasks)
# ─────────────────────────────────────────────────────────────────────
async def main():
    """Primary async routine — initialises DB, bot, and background tasks."""

    # Validate
    if not all([API_ID, API_HASH, BOT_TOKEN]):
        logger.error("❌ Missing API_ID, API_HASH, or BOT_TOKEN. Cannot start.")
        return

    # Init databases
    logger.info("Connecting to database...")
    await db.connect()

    # Connect Redis for distributed state
    from services.distributed_state import distributed_state
    await distributed_state.connect()

    # Configure Behavioral Intelligence Engine with Redis
    from core.behavior_engine import behavior_engine
    from core.telemetry import EventLogger
    if distributed_state.redis:
        behavior_engine.collector.configure(distributed_state.redis)
        EventLogger.set_redis(distributed_state.redis)
        logger.info("Behavioral Engine & Telemetry initialized with Redis storage.")
    else:
        logger.info("Behavioral Engine running with InMemory storage (shared state disabled).")

    # ── Initialize Unified Matchmaking Engine (Phase 3) ──────────────
    from core.engine.actions import ActionRouter
    from core.engine.reconciler import Reconciler
    from adapters.telegram.adapter import TelegramAdapter
    from adapters.messenger.adapter import MessengerAdapter
    
    app_state.engine = ActionRouter()
    app_state.reconciler = Reconciler()
    app_state.msg_adapter = MessengerAdapter()
    # Note: tg_adapter needs pyrogram_app, so set it later


    # ── Schema migration for new compliance columns ─────────────────
    try:
        async with db._pool.acquire() as conn:
            # Add consent_given_at if not exists
            await conn.execute("""
                DO $$ BEGIN
                    ALTER TABLE users ADD COLUMN IF NOT EXISTS consent_given_at BIGINT;
                    ALTER TABLE users ADD COLUMN IF NOT EXISTS data_deleted_at BIGINT;
                EXCEPTION WHEN duplicate_column THEN NULL;
                END $$;
            """)
            # Create blocked_users table if not exists
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS blocked_users (
                    id SERIAL PRIMARY KEY,
                    blocker_id BIGINT NOT NULL,
                    blocked_id BIGINT NOT NULL,
                    created_at BIGINT NOT NULL,
                    FOREIGN KEY (blocker_id) REFERENCES users(telegram_id),
                    FOREIGN KEY (blocked_id) REFERENCES users(telegram_id),
                    UNIQUE(blocker_id, blocked_id)
                );
                CREATE INDEX IF NOT EXISTS idx_blocked_users ON blocked_users(blocker_id, blocked_id);
            """)
        logger.info("Compliance schema migration complete.")
    except Exception as e:
        logger.warning(f"Schema migration note: {e}")

    # ── Grandfather existing users (mark as consented) ──────────────
    try:
        from database.repositories.user_repository import UserRepository
        count = await UserRepository.grandfather_existing_users()
        if count > 0:
            logger.info(f"Grandfathered {count} existing users (consent marked).")
    except Exception as e:
        logger.warning(f"Grandfathering note: {e}")

    # Resolve directories for Pyrogram plugin loading
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(script_dir)
    parent_dir = os.path.dirname(script_dir)
    if parent_dir not in sys.path:
        sys.path.insert(0, parent_dir)
    if script_dir not in sys.path:
        sys.path.insert(0, script_dir)

    # ── Pyrogram Client ───────────────────────────────────────────────
    pyrogram_app = Client(
        "anonymous_bot",
        api_id=int(API_ID),
        api_hash=API_HASH,
        bot_token=BOT_TOKEN,
        plugins=dict(root="handlers"),
        workdir=script_dir
    )

    # Store in shared state so messenger_handlers can send cross-platform TG messages
    app_state.telegram_app = pyrogram_app
    app_state.tg_adapter = TelegramAdapter(pyrogram_app)


    # ── Exception handler ─────────────────────────────────────────────
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.get_event_loop()
    app_state.bot_loop = loop
    loop.set_exception_handler(setup_exception_handler(pyrogram_app))

    # ── Background services ───────────────────────────────────────────
    from services.session_manager import start_session_manager
    from services.event_manager  import start_event_manager
    from services.admin_worker   import start_admin_worker
    # from services.backup_service import start_backup_service # SQLite backup obsolete

    asyncio.create_task(start_session_manager(pyrogram_app))
    asyncio.create_task(start_event_manager(pyrogram_app))
    asyncio.create_task(start_admin_worker(pyrogram_app))

    # Cross-platform match poller — pairs Telegram & Messenger users
    from services.matchmaker_loop import start_matchmaker_loop
    asyncio.create_task(start_matchmaker_loop(pyrogram_app))
    
    # Engine Reconciler Loop (Phase 3 Integration)
    asyncio.create_task(start_reconciler_loop())

    # ── Keep-alive pinger (in thread) ─────────────────────────────────
    run_keep_alive()

    # ── Ngrok Tunnel (Development Only) ───────────────────────────────
    base_url = RENDER_EXTERNAL_URL
    if USE_NGROK:
        ngrok_url = start_ngrok_tunnel()
        if ngrok_url:
            base_url = ngrok_url
            
    # ── Start Pyrogram ────────────────────────────────────────────────
    logger.info("Production-Grade Anonymous Bot (Telegram + Messenger) starting...")
    await pyrogram_app.start()

    # ── Flask webhook server (in thread) ──────────────────────────────
    # IMPORTANT: must start AFTER pyrogram_app.start() so that
    # app_state.telegram_app is fully connected before Messenger
    # webhooks arrive and try to use it.
    run_flask_in_thread()
    logger.info("Pyrogram bot started successfully!")

    if MESSENGER_ENABLED:
        webhook_path = "/messenger-webhook"
        full_webhook_url = f"{base_url}{webhook_path}" if base_url else f"http://localhost:{PORT}{webhook_path}"
        logger.info(f"Messenger webhook ready at {full_webhook_url}")
        if USE_NGROK:
            logger.info("PRO TIP: Don't forget to update your Webhook URL in the Meta Developer Dashboard!")

    # ── Keep running ──────────────────────────────────────────────────
    try:
        await asyncio.Event().wait()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Shutdown signal received. Initiating graceful shutdown...")
    finally:
        # Notify all active users about restart
        active_users = set(match_state.active_chats.keys()) | set(match_state.waiting_queue)
        if active_users:
            logger.info(f"📢 Notifying {len(active_users)} active users of restart...")

        for uid in active_users:
            try:
                await pyrogram_app.send_message(
                    chat_id=uid,
                    text=(
                        "🔄 **Bot Restarting!**\n\n"
                        "The bot is restarting for maintenance.\n"
                        "Your active chat has been disconnected. Rejoin in a few seconds!"
                    )
                )
            except Exception:
                pass

        # Disconnect all active sessions
        from services.matchmaking import MatchmakingService
        for uid in list(match_state.active_chats.keys()):
            try:
                await MatchmakingService.disconnect(uid)
            except Exception:
                pass

        logger.info("🔌 Closing database and stopping bot...")
        await db.close()
        await pyrogram_app.stop()
        if USE_NGROK:
            stop_ngrok_tunnel()
        logger.info("✅ Graceful shutdown complete.")


# ─────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
    except Exception as e:
        logger.critical(f"💥 Fatal startup error: {e}")
        traceback.print_exc()
        sys.exit(1)

# ═══════════════════════════════════════════════════════════════════════
# END OF main.py
# ═══════════════════════════════════════════════════════════════════════
