import asyncio
import time
from pyrogram import Client, filters
from pyrogram.types import Message

from state.match_state import match_state
from database.repositories.user_repository import UserRepository
from database.repositories.admin_repository import AdminRepository
from database.connection import db
from utils.helpers import is_admin, update_user_ui
from utils.keyboard import chat_menu, admin_menu
from utils.logger import logger
from config import ADMIN_ID

@Client.on_message(filters.command("debug") & filters.private)
@is_admin
async def debug_match(client: Client, message: Message):
    """Force matches an admin with a virtual echo partner."""
    user_id = message.from_user.id
    await match_state.add_to_chat(user_id, 1)
    
    await update_user_ui(
        client, user_id,
        "🛠 **DEBUG MODE ACTIVATED**\n\nYou are now matched with an **Echo Partner**. Everything you send will be echoed back to you.",
        chat_menu()
    )
    logger.info(f"Admin {user_id} activated debug mode.")

@Client.on_message(filters.command("admin") & filters.private)
@is_admin
async def admin_dashboard(client: Client, message: Message):
    """🏠 Central Administrative Dashboard entry point."""
    await message.reply_text(
        "🛠 **Admin Master Console**\n\nChoose an action below to manage the system:",
        reply_markup=admin_menu()
    )

@Client.on_message(filters.command("broadcast") & filters.private)
@is_admin
async def broadcast_command(client: Client, message: Message):
    """📢 Broadcasts a message or copied custom media to all registered users."""
    is_reply = bool(message.reply_to_message)
    
    if not is_reply and len(message.command) < 2:
        return await message.reply_text("❌ Usage: `/broadcast <message>` OR reply to any message/media with `/broadcast`.")
    
    broadcast_msg = message.text.split(None, 1)[1] if len(message.command) > 1 else ""
    # Fetch all user IDs from UserRepository
    users = await db.fetchall("SELECT telegram_id FROM users")
    
    count = 0
    await message.reply_text(f"🚀 Starting broadcast to {len(users)} users...")
    
    for user in users:
        uid = user['telegram_id']
        try:
            if is_reply:
                # Media copy only works for Telegram users (uid < 10^15)
                if uid < 10**15:
                    await message.reply_to_message.copy(chat_id=uid)
                    count += 1
            else:
                from utils.helpers import send_cross_platform
                success = await send_cross_platform(client, uid, f"📢 **SYSTEM ANNOUNCEMENT**\n━━━━━━━━━━━━━━━━━━\n\n{broadcast_msg}")
                if success:
                    count += 1
            
            if count % 20 == 0: await asyncio.sleep(1) # Rate limiting
        except Exception as e:
            # Prevent log flooding, only log critical errors
            if "PEER_ID_INVALID" not in str(e):
                logger.debug(f"Broadcast delivery issue for {uid}: {e}")
            pass
            
    await message.reply_text(f"✅ **Broadcast Complete!** Successfully delivered to {count} users.")

@Client.on_message(filters.command(["ban", "unban"]) & filters.private)
@is_admin
async def user_management(client: Client, message: Message):
    """🚫 Manage user access (Banning/Unbanning) via commands."""
    if len(message.command) < 2:
        return await message.reply_text(f"❌ Usage: `/{message.command[0]} <user_id>`")
    
    try:
        target_id = int(message.command[1])
    except Exception as e:
        logger.warning(f"Ban/unban parse error: {e}")
        return await message.reply_text("❌ Invalid User ID format!")
        
    block_status = message.command[0] == "ban"
    await UserRepository.update(target_id, is_blocked=bool(block_status))
    
    icon = "🚫" if block_status else "✅"
    await message.reply_text(f"{icon} User `{target_id}` is now **{'Blocked' if block_status else 'Unblocked'}**.")
    
    if not block_status:
        try:
            await client.send_message(target_id, "✅ **Your account has been unblocked!** You can now find a partner again.")
        except Exception as e:
            logger.debug(f"Unban notify failed for {target_id}: {e}")
            pass

@Client.on_message(filters.command("gift") & filters.private)
@is_admin
async def gift_coins_command(client: Client, message: Message):
    """💰 Gifts coins to a specific user."""
    if len(message.command) < 3:
        return await message.reply_text("❌ Usage: `/gift <user_id> <amount>`")
        
    try:
        target_id = int(message.command[1])
        amount = int(message.command[2])
    except Exception as e:
        logger.warning(f"Gift command parse error: {e}")
        return await message.reply_text("❌ Invalid parameters!")
        
    await UserRepository.increment_coins(target_id, amount)
    await message.reply_text(f"💰 Gifted **{amount} coins** to User `{target_id}`.")
    try:
        await client.send_message(target_id, f"🎁 **You received a gift!**\nThe admin gave you **{amount} coins**.")
    except Exception as e:
        logger.debug(f"Gift notify failed for {target_id}: {e}")
        pass

@Client.on_message(filters.command("set_vip") & filters.private)
@is_admin
async def set_vip_command(client: Client, message: Message):
    """✨ Manually toggle VIP status for a user."""
    if len(message.command) < 3:
        return await message.reply_text("❌ Usage: `/set_vip <user_id> <true/false>`")
        
    try:
        target_id = int(message.command[1])
        status = True if message.command[2].lower() == "true" else False
    except Exception as e:
        logger.warning(f"VIP command parse error: {e}")
        return await message.reply_text("❌ Invalid status! Use true/false.")
        
    await UserRepository.update(target_id, vip_status=status)
    await message.reply_text(f"✨ User `{target_id}` VIP status set to **{bool(status)}**.")
    if status:
        try:
            await client.send_message(target_id, "✨ **Congratulations!** You have been granted **VIP Status** by an admin.")
        except Exception as e:
            logger.debug(f"VIP notify failed for {target_id}: {e}")
            pass

@Client.on_message(filters.command("health") & filters.private)
@is_admin
async def health_check(client: Client, message: Message):
    """🏥 Comprehensive system health check."""
    uptime_seconds = int(time.time() - match_state.bot_start_time)
    hours, remainder = divmod(uptime_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    
    stats = await match_state.get_stats()
    db_stats = await AdminRepository.get_system_stats()
    
    health_text = (
        "🏥 **System Health Check**\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"✅ **Status:** Running\n"
        f"⏱ **Uptime:** {hours}h {minutes}m {seconds}s\n"
        f"👥 **Total Users:** {db_stats['total_users']}\n"
        f"💬 **Active Chats:** {stats['active_chats']}\n"
        f"⏳ **Waiting Queue:** {stats['queue_length']}\n"
        "━━━━━━━━━━━━━━━━━━"
    )
    await message.reply_text(health_text)

@Client.on_message(filters.command("reset") & filters.private)
@is_admin
async def reset_system(client: Client, message: Message):
    """🔄 Performs a full system reset of active chats and queues."""
    await match_state.clear_all()
    logger.warning(f"Admin {message.from_user.id} performed a FULL SYSTEM RESET.")
    await message.reply_text("🔄 **System Reset Complete.** All active chats and queues cleared.")
