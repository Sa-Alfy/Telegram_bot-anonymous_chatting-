import time
from typing import Dict, Any, Optional
from pyrogram import Client, types
from database.repositories.admin_repository import AdminRepository
from database.repositories.user_repository import UserRepository
from database.repositories.report_repository import ReportRepository
from adapters.telegram.keyboards import admin_menu, banned_list_menu, appeal_menu
from config import ADMIN_ID
from state.match_state import match_state
from utils.logger import logger

class AdminHandler:
    @staticmethod
    async def handle_stats(client: Client, user_id: int) -> Dict[str, Any]:
        """Fetches and displays administrative statistics."""
        if user_id != ADMIN_ID:
            return {"alert": "🚫 Unauthorized access!", "show_alert": True}
            
        stats = await AdminRepository.get_system_stats()
        text = (
            "📊 **Admin Dashboard**\n"
            f"👤 Total Users: {stats['total_users']}\n"
            f"💬 Sessions (24h): {stats['sessions_24h']}\n"
            f"🚩 Pending Reports: {stats['pending_reports']}\n"
            f"\n🕒 *Last Update: {time.strftime('%H:%M:%S')}*"
        )
        return {"text": text, "reply_markup": admin_menu()}

    @staticmethod
    async def handle_list_banned(client: Client, user_id: int) -> Dict[str, Any]:
        """Lists all banned users for administration."""
        if user_id != ADMIN_ID:
            return {"alert": "🚫 Unauthorized access!", "show_alert": True}
            
        banned = await AdminRepository.get_banned_users()
        if not banned:
            return {"alert": "✅ No users are currently banned.", "show_alert": True}
            
        text = f"🚫 **Banned Users ({len(banned)})**\n\nChoose a user to manage:\n"
        buttons = []
        for b in banned[:10]:
            uid = b['telegram_id']
            name = b.get('first_name', 'Unknown')
            buttons.append([types.InlineKeyboardButton(f"👤 {name} ({uid})", callback_data=f"admin_manage_ban_{uid}")])
        buttons.append([types.InlineKeyboardButton("🔙 Back to Dashboard", callback_data="admin_stats")])
        
        return {"text": text, "reply_markup": types.InlineKeyboardMarkup(buttons)}

    @staticmethod
    async def handle_manage_ban(client: Client, user_id: int, target_uid: int) -> Dict[str, Any]:
        """Displays management options for a specific banned user."""
        if user_id != ADMIN_ID:
            return {"alert": "🚫 Unauthorized access!", "show_alert": True}
            
        user = await UserRepository.get_by_telegram_id(target_uid)
        if not user:
            return {"alert": "❌ User not found!", "show_alert": True}
            
        # Implementation details for ban history would go here
        text = (
            f"👤 **Managing User:** {user.get('first_name')} (`{target_uid}`)\n"
            f"🚩 Reports: {user.get('reports', 0)}\n"
            f"🧐 Reason: {user.get('ban_reason', 'Manual Ban')}\n"
        )
        return {"text": text, "reply_markup": banned_list_menu(target_uid)}

    @staticmethod
    async def handle_unban_request(client: Client, admin_id: int, target_uid: int) -> Dict[str, Any]:
        """Initiates the unban flow."""
        if admin_id != ADMIN_ID:
            return {"alert": "🚫 Unauthorized!", "show_alert": True}
        await AdminRepository.log_action(admin_id, "unban_attempt", target_uid)
        return {
            "alert": "Please send the unban message in the chat.",
            "show_alert": True,
            "set_state": f"awaiting_unban_msg:{target_uid}",
            "text": f"🔓 **Unbanning {target_uid}**\n\nPlease type a message to send to the user explaining why they are being unbanned.",
            "reply_markup": types.InlineKeyboardMarkup([[types.InlineKeyboardButton("🔙 Cancel", callback_data="admin_list_banned")]])
        }

    @staticmethod
    async def handle_list_banned_simple(client: Client, user_id: int) -> Dict[str, Any]:
        """Displays the list of currently banned users."""
        if user_id != ADMIN_ID:
            return {"alert": "🚫 Unauthorized!", "show_alert": True}
        banned = await AdminRepository.get_banned_users()
        if not banned:
            return {"alert": "✅ No users are currently banned.", "show_alert": True}
        
        text = "**🚫 Banned Users**\n━━━━━━━━━━━━━━━━━━\n\n"
        for u in banned:
            text += f"👤 **{u['first_name']}** (`{u['telegram_id']}`)\n"
            
        return {"text": text, "reply_markup": admin_menu()}

    @staticmethod
    async def handle_admin_events(client: Client, user_id: int) -> Dict[str, Any]:
        """Displays the tournament and event management dashboard."""
        if user_id != ADMIN_ID:
            return {"alert": "🚫 Unauthorized!", "show_alert": True}
        from services.event_manager import get_active_event
        import time
        event = get_active_event()
        
        mins_left = max(0, int((event['ends_at'] - time.time()) / 60))
        text = (
            "📅 **Global Event Dashboard**\n"
            "━━━━━━━━━━━━━━━━━━\n"
            f"🏷 **Active:** {event['name']}\n"
            f"⚡ **Multiplier:** {event['multiplier']}x\n"
            f"⌛ **Ends in:** {mins_left} min\n"
            "━━━━━━━━━━━━━━━━━━"
        )
        return {"text": text, "reply_markup": admin_menu()}

    @staticmethod
    async def handle_admin_health(client: Client, user_id: int) -> Dict[str, Any]:
        """Checks system health and uptime."""
        if user_id != ADMIN_ID:
            return {"alert": "🚫 Unauthorized!", "show_alert": True}
        from state.match_state import match_state
        uptime_seconds = int(time.time() - match_state.bot_start_time)
        hours, remainder = divmod(uptime_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        stats = await match_state.get_stats()
        
        text = (
            "🏥 **System Health Check**\n"
            "━━━━━━━━━━━━━━━━━━\n"
            f"✅ **Status:** Running\n"
            f"⏱ **Uptime:** {hours}h {minutes}m {seconds}s\n"
            f"💬 **Active Chats:** {stats['active_chats']}\n"
            f"⏳ **Waiting Queue:** {stats['queue_length']}\n"
            "━━━━━━━━━━━━━━━━━━\n"
            f"🕒 *Check Time: {time.strftime('%H:%M:%S')}*"
        )
        return {"text": text, "reply_markup": admin_menu()}

    @staticmethod
    async def handle_reset_confirm(client: Client, user_id: int) -> Dict[str, Any]:
        """Confirmation prompt before system reset."""
        if user_id != ADMIN_ID:
            return {"alert": "🚫 Unauthorized!", "show_alert": True}
        return {
            "text": "⚠️ **CRITICAL ACTION** ⚠️\n\nAre you sure you want to clear **ALL** active chats and queues? This cannot be undone.",
            "reply_markup": types.InlineKeyboardMarkup([
                [types.InlineKeyboardButton("🔥 YES, RESET ALL", callback_data="admin_reset_execute")],
                [types.InlineKeyboardButton("🔙 Cancel", callback_data="admin_stats")]
            ])
        }

    @staticmethod
    async def handle_reset(client: Client, user_id: int) -> Dict[str, Any]:
        """Performs a full system reset of active chats and queues."""
        if user_id != ADMIN_ID:
            return {"alert": "🚫 Unauthorized access!", "show_alert": True}
        
        from state.match_state import match_state
        from utils.logger import logger
        await match_state.clear_all()
        logger.warning(f"Admin {user_id} performed a FULL SYSTEM RESET via button.")
        
        return {
            "text": "🔄 **System Reset Complete.**\n\nAll active chats and queues have been cleared.",
            "reply_markup": admin_menu()
        }

    @staticmethod
    async def handle_debug(client: Client, user_id: int) -> Dict[str, Any]:
        """Activates debug mode (Matching with Echo)."""
        if user_id != ADMIN_ID:
            return {"alert": "🚫 Unauthorized!", "show_alert": True}
        from state.match_state import match_state
        from adapters.telegram.keyboards import chat_menu
        await match_state.add_to_chat(user_id, 1) # Match with Echo Partner
        return {
            "text": "🛠 **DEBUG MODE ACTIVATED**\n\nYou are matched with an **Echo Partner**.",
            "reply_markup": chat_menu(),
            "alert": "Debug Mode ON", "show_alert": True
        }

    @staticmethod
    async def handle_broadcast_prompt(client: Client, user_id: int) -> Dict[str, Any]:
        """Prompts for broadcast message."""
        if user_id != ADMIN_ID:
            return {"alert": "🚫 Unauthorized!", "show_alert": True}
        from state.match_state import match_state
        await match_state.set_user_state(user_id, "awaiting_admin_broadcast")
        return {
            "text": "📢 **Broadcast Manager**\n\nPlease send the message (Text/Photo/Video) you want to broadcast to **ALL** users.\n\nType 'cancel' to abort.",
            "reply_markup": types.InlineKeyboardMarkup([[types.InlineKeyboardButton("🔙 Cancel", callback_data="admin_stats")]])
        }

    @staticmethod
    async def handle_gift_prompt(client: Client, user_id: int) -> Dict[str, Any]:
        """Prompts for user ID to gift coins."""
        if user_id != ADMIN_ID:
            return {"alert": "🚫 Unauthorized!", "show_alert": True}
        from state.match_state import match_state
        await match_state.set_user_state(user_id, "awaiting_gift_target")
        return {
            "text": "💰 **Gift Coins**\n\nPlease enter the **User ID** of the recipient:",
            "reply_markup": types.InlineKeyboardMarkup([[types.InlineKeyboardButton("🔙 Cancel", callback_data="admin_stats")]])
        }

    @staticmethod
    async def handle_vip_prompt(client: Client, user_id: int) -> Dict[str, Any]:
        """Prompts for user ID to set VIP."""
        if user_id != ADMIN_ID:
            return {"alert": "🚫 Unauthorized!", "show_alert": True}
        from state.match_state import match_state
        await match_state.set_user_state(user_id, "awaiting_vip_target")
        return {
            "text": "✨ **VIP Manager**\n\nPlease enter the **User ID** to manage VIP status:",
            "reply_markup": types.InlineKeyboardMarkup([[types.InlineKeyboardButton("🔙 Cancel", callback_data="admin_stats")]])
        }

    @staticmethod
    async def handle_user_manage_prompt(client: Client, user_id: int) -> Dict[str, Any]:
        """Prompts for user ID to manage (Ban/Unban)."""
        if user_id != ADMIN_ID:
            return {"alert": "🚫 Unauthorized!", "show_alert": True}
        from state.match_state import match_state
        await match_state.set_user_state(user_id, "awaiting_manage_target")
        return {
            "text": "👤 **User Manager**\n\nPlease enter the **User ID** to manage:",
            "reply_markup": types.InlineKeyboardMarkup([[types.InlineKeyboardButton("🔙 Cancel", callback_data="admin_stats")]])
        }

    @staticmethod
    async def handle_set_vip_button(client: Client, user_id: int, target_id: int, status_str: str) -> Dict[str, Any]:
        """Processes the VIP toggle button."""
        if user_id != ADMIN_ID:
            return {"alert": "🚫 Unauthorized!", "show_alert": True}
        status = True if status_str.lower() == "true" else False
        await UserRepository.update(target_id, vip_status=status)
        if status:
            try: await client.send_message(target_id, "✨ **Congratulations!** Admin granted you **VIP Status**.")
            except Exception as e:
                logger.debug(f"VIP notify failed for {target_id}: {e}")
        return {"alert": f"✅ User {target_id} VIP set to {status_str}", "show_alert": True, "text": "✅ Action Complete.", "reply_markup": admin_menu()}

    @staticmethod
    async def handle_quick_gift(client: Client, user_id: int, target_id: int, amount: int) -> Dict[str, Any]:
        """Processes quick coin gifts."""
        if user_id != ADMIN_ID:
            return {"alert": "🚫 Unauthorized!", "show_alert": True}
        await UserRepository.increment_coins(target_id, amount)
        try: await client.send_message(target_id, f"🎁 **Admin gifted you {amount} coins!**")
        except Exception as e:
            logger.debug(f"Gift notify failed for {target_id}: {e}")
        return {"alert": f"💰 Gifted {amount} coins to {target_id}", "show_alert": True, "text": "✅ Gift Sent.", "reply_markup": admin_menu()}

    @staticmethod
    async def handle_deduct_prompt(client: Client, user_id: int) -> Dict[str, Any]:
        """Prompts for user ID to deduct coins."""
        if user_id != ADMIN_ID:
            return {"alert": "🚫 Unauthorized!", "show_alert": True}
        from state.match_state import match_state
        await match_state.set_user_state(user_id, "awaiting_deduct_target")
        return {
            "text": "💸 **Take Coins**\n\nPlease enter the **User ID** to deduct from:",
            "reply_markup": types.InlineKeyboardMarkup([[types.InlineKeyboardButton("🔙 Cancel", callback_data="admin_stats")]])
        }

    @staticmethod
    async def handle_quick_deduct(client: Client, user_id: int, target_id: int, amount: int) -> Dict[str, Any]:
        """Processes quick coin deductions."""
        if user_id != ADMIN_ID:
            return {"alert": "🚫 Unauthorized!", "show_alert": True}
        # Use negative amount with increment_coins to deduct
        await UserRepository.increment_coins(target_id, -amount)
        try: await client.send_message(target_id, f"💸 **Admin deducted {amount} coins from your balance.**")
        except Exception as e:
            logger.debug(f"Deduct notify failed for {target_id}: {e}")
        return {"alert": f"💸 Deducted {amount} coins from {target_id}", "show_alert": True, "text": "✅ Coins Deducted.", "reply_markup": admin_menu()}
