from pyrogram import Client
from pyrogram.types import Message, CallbackQuery
from state.memory import user_ui_messages
from config import ADMIN_ID
from functools import wraps

def is_admin(func):
    @wraps(func)
    async def wrapper(client, message, *args, **kwargs):
        user_id = message.from_user.id if hasattr(message, "from_user") else None
        if user_id != ADMIN_ID:
            if isinstance(message, CallbackQuery):
                await message.answer("🔒 Admin only feature.", show_alert=True)
            return
        return await func(client, message, *args, **kwargs)
    return wrapper

async def update_user_ui(client: Client, user_id: int, text: str, reply_markup):
    # Phase 11 Debug: Don't send messages to the virtual echo partner
    if user_id == 1:
        return

    if user_id in user_ui_messages:
        try:
            await client.edit_message_text(
                chat_id=user_id,
                message_id=user_ui_messages[user_id],
                text=text,
                reply_markup=reply_markup
            )
            return
        except Exception as e:
            # If the content is exactly the same, Telegram raises an error.
            # We don't want to send a new message in this case.
            if "MESSAGE_NOT_MODIFIED" in str(e).upper():
                return
            pass
            
    # Fallback if we don't have message id or couldn't edit
    try:
        sent = await client.send_message(
            chat_id=user_id,
            text=text,
            reply_markup=reply_markup
        )
        user_ui_messages[user_id] = sent.id
    except Exception:
        pass

