import time
from pyrogram import Client
from pyrogram.types import Message, CallbackQuery
from config import ADMIN_ID
from functools import wraps
from state.match_state import match_state
from utils.logger import logger

def is_admin(func):
    @wraps(func)
    async def wrapper(client, message, *args, **kwargs):
        # Determine user_id from Message or CallbackQuery
        if isinstance(message, CallbackQuery):
            user_id = message.from_user.id
        else:
            user_id = message.from_user.id if hasattr(message, "from_user") else None
            
        if user_id != int(ADMIN_ID):
            if isinstance(message, CallbackQuery):
                await message.answer("🔒 Admin only feature.", show_alert=True)
            return
        return await func(client, message, *args, **kwargs)
    return wrapper

async def send_cross_platform(client: Client, target_id: int, text: str, reply_markup=None):
    """Universal sender that routes to Telegram or Messenger dynamically."""
    from utils.platform_adapter import PlatformAdapter
    return await PlatformAdapter.send_cross_platform(client, target_id, text, reply_markup)

async def update_user_ui(client: Client, user_id: int, text: str, reply_markup, force_new: bool = True):
    """Refined UI update helper using MatchState for production tracking."""
    # Virtual Echo Partner check
    if user_id == 1:
        return

    if user_id >= 10**15:
        await send_cross_platform(client, user_id, text, reply_markup)
        return

    # Attempt to edit previous UI message if tracked (skip if force_new)
    prev_msg_id = match_state.user_ui_messages.get(user_id)
    if prev_msg_id and not force_new:
        try:
            await client.edit_message_text(
                chat_id=user_id,
                message_id=prev_msg_id,
                text=text,
                reply_markup=reply_markup
            )
            return
        except Exception as e:
            if "MESSAGE_NOT_MODIFIED" in str(e).upper():
                return
            pass
            
    # Fallback to sending a new message and updating tracker
    try:
        sent = await client.send_message(
            chat_id=user_id,
            text=text,
            reply_markup=reply_markup
        )
        match_state.user_ui_messages[user_id] = sent.id
    except Exception as e:
        logger.debug(f"UI fallback send failed for {user_id}: {e}")
        pass


def is_vip_active(user: dict) -> bool:
    """Returns True only if the user has VIP and it has not expired."""
    if not user or not user.get("vip_status"):
        return False
    expires_at = user.get("vip_expires_at")
    if not expires_at or expires_at < time.time():
        return False
    return True
