# ═══════════════════════════════════════════════════════════════════════
# FILE: messenger/utils.py
# PURPOSE: Messenger utility functions and async bridge
# ═══════════════════════════════════════════════════════════════════════

import logging
import asyncio
from messenger_api import send_message, send_quick_replies
from database.repositories.user_repository import UserRepository

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────
# Prefix helpers (mirrors platform_abstraction convention)
# ─────────────────────────────────────────────────────────────────────

def _uid(psid: str) -> str:
    """Convert raw PSID to a namespaced messenger user key."""
    return f"msg_{psid}"


def _raw(uid: str) -> str:
    """Strip prefix to get raw PSID or telegram_id."""
    if uid.startswith("msg_"):
        return uid[4:]
    if uid.startswith("tg_"):
        return uid[3:]
    return uid


def _platform(uid: str) -> str:
    return "messenger" if uid.startswith("msg_") else "telegram"


# ─────────────────────────────────────────────────────────────────────
# Helper: send to any platform user by prefixed uid (now async)
# ─────────────────────────────────────────────────────────────────────

async def _send_to(uid: str, text: str):
    """Send a text message to any user (Telegram or Messenger) by prefixed uid."""
    if uid.startswith("msg_"):
        send_message(_raw(uid), text)
    elif uid.startswith("tg_"):
        raw_id = int(_raw(uid))
        try:
            import app_state
            if app_state.bot_loop and app_state.bot_loop.is_running() and app_state.telegram_app:
                await app_state.telegram_app.send_message(chat_id=raw_id, text=text)
        except Exception as e:
            logger.error(f"Failed to send Telegram msg to {uid}: {e}")


async def _send_menu_to(uid: str, text: str, buttons: list):
    """Send message + buttons. On Messenger: quick_replies. On Telegram: best effort text."""
    if uid.startswith("msg_"):
        if buttons:
            send_quick_replies(_raw(uid), text, buttons)
        else:
            send_message(_raw(uid), text)
    else:
        await _send_to(uid, text)


# ─────────────────────────────────────────────────────────────────────
# Messenger user management (creates DB records for Messenger users)
# ─────────────────────────────────────────────────────────────────────

async def _get_or_create_messenger_user(psid: str) -> dict:
    """Get or create a DB record for a Messenger user using a virtual telegram_id."""
    import hashlib
    psid_hash = int(hashlib.sha256(psid.encode()).hexdigest(), 16)
    virtual_id = (psid_hash % (10**15)) + 10**15
    user = await UserRepository.get_by_telegram_id(virtual_id)
    if not user:
        user = await UserRepository.create(virtual_id, username=f"msg_{psid}", first_name=f"Messenger User {psid[-4:]}")
        logger.info(f"New Messenger user registered: virtual_id ...{str(virtual_id)[-4:]}")
    return user, virtual_id
