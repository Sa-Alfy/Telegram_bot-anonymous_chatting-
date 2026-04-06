from pyrogram import Client, filters
from pyrogram.types import Message
from utils.helpers import is_admin, update_user_ui
from state.memory import active_chats, waiting_queue
from utils.keyboard import chat_menu
from utils.logger import logger

@Client.on_message(filters.command("debug") & filters.private)
@is_admin
async def debug_match(client: Client, message: Message):
    user_id = message.from_user.id
    
    # Force match with virtual ID 1 (Echo Partner)
    active_chats[user_id] = 1
    
    await update_user_ui(
        client, user_id,
        "🛠 **DEBUG MODE ACTIVATED**\n\nYou are now matched with an **Echo Partner**. Everything you send will be echoed back to you.",
        chat_menu()
    )
    logger.info(f"Admin {user_id} activated debug mode.")

@Client.on_message(filters.command("stats") & filters.private)
@is_admin
async def stats_command(client: Client, message: Message):
    stats_text = (
        "📊 **Bot Statistics**\n\n"
        f"👥 Active Chats: {len(active_chats) // 2}\n"
        f"⏳ Users in Queue: {len(waiting_queue)}\n"
    )
    await message.reply_text(stats_text)
