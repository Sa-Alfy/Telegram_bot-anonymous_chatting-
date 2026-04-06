from pyrogram import Client
from pyrogram.types import Message, CallbackQuery
from config import ADMIN_ID
from functools import wraps
from state.match_state import match_state

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

async def update_user_ui(client: Client, user_id: int, text: str, reply_markup):
    """Refined UI update helper using MatchState for production tracking."""
    # Virtual Echo Partner check
    if user_id == 1:
        return

    # Attempt to edit previous UI message if tracked
    prev_msg_id = match_state.user_ui_messages.get(user_id)
    if prev_msg_id:
        try:
            await client.edit_message_text(
                chat_id=user_id,
                message_id=prev_msg_id,
                text=text,
                reply_markup=reply_markup
            )
            return
        except Exception as e:
            # Silently handle 'message not modified' or 'message deleted'
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
    except Exception:
        pass
