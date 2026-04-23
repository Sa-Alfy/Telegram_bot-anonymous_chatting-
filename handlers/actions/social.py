from typing import Dict, Any
from utils.rate_limiter import rate_limiter
from pyrogram import Client
from state.match_state import match_state
from adapters.telegram.keyboards import chat_menu, reaction_menu
from utils.helpers import update_user_ui

class SocialHandler:
    @staticmethod
    async def handle_open_reactions(client: Client, user_id: int) -> Dict[str, Any]:
        """Shows the reaction menu during a chat."""
        if not await match_state.is_in_chat(user_id):
            return {"alert": "❌ You are not in a chat!", "show_alert": True}
            
        return {
            "text": "🎭 **Select a Reaction**\nYour partner will see a popup with your reaction.",
            "reply_markup": reaction_menu()
        }

    @staticmethod
    async def handle_reaction(client: Client, user_id: int, reaction_type: str) -> Dict[str, Any]:
        """Sends a reaction to the partner."""
        partner_id = await match_state.get_partner(user_id)
        if not partner_id:
            return {"alert": "❌ Partner disconnected.", "show_alert": True}

        reactions = {
            "heart": "❤️",
            "joy": "😂",
            "wow": "😮",
            "sad": "😢",
            "up": "👍"
        }
        emoji = reactions.get(reaction_type, "✨")
        
        return {
            "alert": "✅ Reaction sent!",
            "text": "💬 **Chatting...**\nSelect an action below:",
            "reply_markup": chat_menu(),
            "notify_partner": {
                "target_id": partner_id,
                "text": f"🎭 **Partner reacted:** {emoji}"
            }
        }

    @staticmethod
    async def handle_back_to_chat(client: Client, user_id: int) -> Dict[str, Any]:
        """Returns to the main chat menu, or home menu if user is not in a chat.
        Guards against Admin 'Close Console' button returning a chat menu to a non-chat user.
        """
        from services.distributed_state import distributed_state
        from core.engine.state_machine import UnifiedState
        from adapters.telegram.keyboards import get_home_keyboard, get_chat_keyboard
        state = await distributed_state.get_user_state(str(user_id))
        if state == UnifiedState.CHAT_ACTIVE:
            partner_id = await match_state.get_partner(user_id) or 0
            return {
                "text": "💬 **Chatting...**\nSelect an action below:",
                "reply_markup": get_chat_keyboard(str(partner_id))
            }
        # Not in chat — return home instead of showing a stale chat menu
        return {
            "text": "🏠 **Main Menu**\nWelcome back!",
            "reply_markup": get_home_keyboard()
        }
    
    @staticmethod
    async def handle_report(client: Client, user_id: int) -> Dict[str, Any]:
        """Triggered when a user clicks Report during chat — shows the report confirm menu."""
        if not await match_state.is_in_chat(user_id):
            return {"alert": "❌ You are not in a chat!", "show_alert": True}
        if not await rate_limiter.can_report(user_id):
            return {"alert": "⏳ Please wait 5 seconds between reports.", "show_alert": True}
        
        from adapters.telegram.keyboards import report_confirm_menu
        return {
            "text": "🚨 **Report Partner**\n\nAre you sure you want to report this user?\nThis will end the chat and flag their account.",
            "reply_markup": report_confirm_menu()
        }

    @staticmethod
    async def handle_report_confirm(client: Client, user_id: int) -> Dict[str, Any]:
        """Immediately reports the partner and disconnects."""
        from services.matchmaking import MatchmakingService
        from services.user_service import UserService
        from database.repositories.user_repository import UserRepository
        from adapters.telegram.keyboards import end_menu
        
        partner_id = await match_state.get_partner(user_id)
        if not partner_id:
            return {"alert": "❌ No active partner to report.", "show_alert": True}

        stats = await MatchmakingService.disconnect(user_id)
        if not stats:
            return {"alert": "❌ Could not disconnect.", "show_alert": True}
        is_blocked = await UserService.report_user(user_id, partner_id, "Reported via button (no reason given)")
        
        user = await UserRepository.get_by_telegram_id(user_id)
        coins = user.get("coins", 0) if user else 0
        
        # Notify partner
        partner_text = "❌ **Chat ended.**\nYour partner has left the conversation."
        await update_user_ui(client, partner_id, partner_text, end_menu())
        
        return {
            "text": f"🚨 **Report Submitted.**\nThe user has been flagged for review.\n\n💰 **Your Balance:** {coins} coins",
            "reply_markup": end_menu()
        }

    @staticmethod
    async def handle_report_with_reason(client: Client, user_id: int) -> Dict[str, Any]:
        """Prompts the user to type a reason for the report."""
        partner_id = await match_state.get_partner(user_id)
        if not partner_id:
            return {"alert": "❌ No partner to report.", "show_alert": True}
        
        return {
            "text": "📝 **Type your report reason below:**\n\nDescribe why you are reporting this user. Your message will be sent as the report.",
            "reply_markup": None,
            "set_state": f"awaiting_report_reason:{partner_id}"
        }

    @staticmethod
    async def handle_peek(client: Client, user_id: int) -> Dict[str, Any]:
        """Peeks at partner's statistics. Opens sub-menu for specific details."""
        if not await match_state.is_in_chat(user_id):
            return {"alert": "❌ You are not in a chat!", "show_alert": True}
            
        from adapters.telegram.keyboards import peek_menu
        return {
            "text": "🕵️ **Partner Statistics (Peek)**\n\nWhat would you like to reveal for 10 coins?",
            "reply_markup": peek_menu()
        }

    @staticmethod
    async def _execute_peek_detail(user_id: int, stat_name: str, display_label: str) -> Dict[str, Any]:
        """Base logic for specific stat reveals."""
        from database.repositories.user_repository import UserRepository
        from services.user_service import UserService
        
        partner_id = await match_state.get_partner(user_id)
        if not partner_id:
            return {"alert": "❌ Partner disconnected.", "show_alert": True}

        # Echo AI check
        if partner_id == 1:
            val = "🔥 999+" if stat_name == "daily_streak" else "💎 Master"
            return {"alert": f"🕵️ **Echo AI {display_label}:** {val}", "show_alert": True}

        cost = 10
        user = await UserRepository.get_by_telegram_id(user_id)
        if user['coins'] < cost:
            return {"alert": f"❌ You need {cost} coins for this!", "show_alert": True}

        if await UserService.deduct_coins(user_id, cost):
            partner = await UserRepository.get_by_telegram_id(partner_id)
            if not partner:
                return {"alert": "❌ Partner profile not found.", "show_alert": True}
            
            value = partner.get(stat_name, 0)
            return {
                "alert": f"🕵️ **Partner {display_label}:** {value}",
                "show_alert": True,
                "text": "💬 **Chatting...**\nSelect an action below:",
                "reply_markup": chat_menu()
            }
        return {"alert": "❌ Transaction failed.", "show_alert": True}

    @staticmethod
    async def handle_peek_streak(client: Client, user_id: int) -> Dict[str, Any]:
        return await SocialHandler._execute_peek_detail(user_id, "daily_streak", "Chat Streak")

    @staticmethod
    async def handle_peek_level(client: Client, user_id: int) -> Dict[str, Any]:
        return await SocialHandler._execute_peek_detail(user_id, "level", "Global Level")

    @staticmethod
    async def handle_add_friend(client: Client, user_id: int) -> Dict[str, Any]:
        """Sends a friend request to the partner."""
        from database.repositories.friend_repository import FriendRepository
        partner_id = await match_state.get_partner(user_id)
        if partner_id == 1:
            return {"alert": "🤖 You cannot add the System AI as a friend!", "show_alert": True}
        if not partner_id:
            return {"alert": "❌ Partner disconnected.", "show_alert": True}

        if await FriendRepository.is_friend(user_id, partner_id):
            return {"alert": "✨ You are already friends!", "show_alert": True}

        if await FriendRepository.has_pending_request(user_id, partner_id):
            return {"alert": "⏳ A friend request is already pending.", "show_alert": True}

        if await FriendRepository.send_request(user_id, partner_id):
            from adapters.telegram.keyboards import accept_friend_menu
            return {
                "alert": "💌 Friend request sent! Waiting for partner to accept.",
                "show_alert": True,
                "partner_msg": {
                    "target_id": partner_id,
                    "text": "💌 **Your partner just sent you a friend request!**\nWould you like to stay in touch?",
                    "reply_markup": accept_friend_menu(user_id)
                }
            }
        return {"alert": "❌ Could not send request.", "show_alert": True}

    @staticmethod
    async def handle_accept_friend(client: Client, user_id: int, sender_id: int) -> Dict[str, Any]:
        """Accepts a friend request from a partner."""
        from database.repositories.friend_repository import FriendRepository
        if await FriendRepository.accept_request(user_id, sender_id):
            # Notify sender
            await update_user_ui(client, sender_id, "❤️ **Friend Request Accepted!**\nYou can now see each other in your friend list (Coming soon).", None)
            
            return {
                "alert": "✅ Friend request accepted!",
                "show_alert": True,
                "text": "❤️ **New Friendship Established!**",
                "reply_markup": chat_menu()
            }
        return {"alert": "❌ Failed to accept request.", "show_alert": True}

    @staticmethod
    async def handle_decline_friend(client: Client, user_id: int, sender_id: int) -> Dict[str, Any]:
        """Declines a friend request."""
        from database.repositories.friend_repository import FriendRepository
        if await FriendRepository.decline_request(user_id, sender_id):
            return await SocialHandler.handle_view_requests(client, user_id)
        return {"alert": "❌ Failed to decline request.", "show_alert": True}

    @staticmethod
    async def handle_view_requests(client: Client, user_id: int) -> Dict[str, Any]:
        """Shows the pending friend requests menu."""
        from database.repositories.friend_repository import FriendRepository
        from adapters.telegram.keyboards import pending_requests_menu
        
        requests = await FriendRepository.get_incoming_requests(user_id)
        if not requests:
            return {"alert": "📬 No pending requests!", "show_alert": True}
            
        count = len(requests)
        return {
            "text": f"📬 **Pending Friend Requests ({count})**\n━━━━━━━━━━━━━━━━━━\nSelect a user to accept or decline:",
            "reply_markup": pending_requests_menu(requests)
        }

    @staticmethod
    async def handle_peek_detail(client: Client, user_id: int, detail_type: str) -> Dict[str, Any]:
        """Provides specific partner insights for a small fee."""
        return {"alert": f"🕵️ Peek detail: {detail_type} is locked behind higher level!", "show_alert": True}

    @staticmethod
    async def handle_user_appeal(client: Client, user_id: int) -> Dict[str, Any]:
        """Initiates the appeal process for banned users."""
        return {
            "text": "📝 **Submit Your Appeal**\n\nPlease type your appeal message below. Explain why you believe the ban was a mistake.",
            "reply_markup": None,
            "set_state": "awaiting_appeal"
        }

    @staticmethod
    async def handle_friends_list(client: Client, user_id: int) -> Dict[str, Any]:
        from database.repositories.friend_repository import FriendRepository
        from adapters.telegram.keyboards import friends_list_menu
        
        friends = await FriendRepository.get_friends_list(user_id)
        if not friends:
            return {"alert": "👥 Your friends list is empty right now.", "show_alert": True}
            
        return {
            "text": f"👥 **Friends List ({len(friends)})**\n\nSelect a friend to message or remove them:",
            "reply_markup": friends_list_menu(friends)
        }

    @staticmethod
    async def handle_friend_action(client: Client, user_id: int, friend_id: int) -> Dict[str, Any]:
        from adapters.telegram.keyboards import friend_action_menu
        from database.repositories.user_repository import UserRepository
        
        friend = await UserRepository.get_by_telegram_id(friend_id)
        name = friend.get("first_name", "Unknown") if friend else "Unknown"
        
        return {
            "text": f"👤 **Friend: {name}**\n\nWhat would you like to do?",
            "reply_markup": friend_action_menu(friend_id)
        }

    @staticmethod
    async def handle_remove_friend(client: Client, user_id: int, friend_id: int) -> Dict[str, Any]:
        """Permanently removes a friendship relationship."""
        from database.repositories.friend_repository import FriendRepository
        await FriendRepository.remove_friend(user_id, friend_id)
        return await SocialHandler.handle_friends_list(client, user_id)

    @staticmethod
    async def handle_msg_friend(client: Client, user_id: int, friend_id: int) -> Dict[str, Any]:
        """Initiates a private messaging session (Relay Mode)."""
        from database.repositories.user_repository import UserRepository
        from database.repositories.friend_repository import FriendRepository
        from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
        
        if not await FriendRepository.is_friend(user_id, friend_id):
            return {"alert": "❌ Not a friend!", "show_alert": True}
            
        friend = await UserRepository.get_by_telegram_id(friend_id)
        name = friend.get("first_name", "Unknown") if friend else "Unknown"
        
        return {
            "text": f"💬 **Private Relay Mode: {name}**\n━━━━━━━━━━━━━━━━━━\n"
                    f"You are now messaging your friend directly. Every message you type will be relayed to them.\n\n"
                    f"Type your message below. Click the button to stop relaying.",
            "reply_markup": InlineKeyboardMarkup([[InlineKeyboardButton("🛑 Stop Relaying", callback_data="cancel_friend_msg")]]),
            "set_state": f"awaiting_friend_msg:{friend_id}"
        }

    @staticmethod
    async def handle_cancel_friend_msg(client: Client, user_id: int) -> Dict[str, Any]:
        """Exits the friend messaging relay mode."""
        from database.repositories.user_repository import UserRepository
        from adapters.telegram.keyboards import start_menu
        await match_state.set_user_state(user_id, None)
        user = await UserRepository.get_by_telegram_id(user_id)
        return {
            "text": "🏠 **Relay session ended.**\nReturning to your dashboard.",
            "reply_markup": start_menu(user.get("is_guest", True))
        }
