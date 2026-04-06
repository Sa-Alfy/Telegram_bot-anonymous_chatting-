import time
import asyncio
import random
from typing import Dict, Any, Callable, Coroutine
from pyrogram import Client, filters
from pyrogram.types import CallbackQuery

from handlers.actions.matching import MatchingHandler
from handlers.actions.economy import EconomyHandler
from handlers.actions.admin import AdminHandler
from handlers.actions.social import SocialHandler
from handlers.actions.stats import StatsHandler
from handlers.actions.onboarding import OnboardingHandler
from state.match_state import match_state
from services.user_service import UserService
from utils.helpers import update_user_ui
from utils.logger import logger
from utils.keyboard import search_menu, chat_menu, start_menu, admin_menu

async def handle_help(client: Client, user_id: int) -> Dict[str, Any]:
    """Displays the help and guide menu."""
    help_text = (
        "ℹ️ **How to use Anonymous Chat Bot**\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "1. **🔍 Find Partner**: Starts searching for a random stranger.\n"
        "2. **👤 Profile**: Set your gender, bio, and location for better matches.\n"
        "3. **💰 Economy**: Earn coins by chatting and spend them on boosters/reveals.\n"
        "4. **🛡 Moderation**: Report offensive users. We have a zero-tolerance policy.\n"
        "━━━━━━━━━━━━━━━━━━"
    )
    return {"text": help_text, "reply_markup": start_menu()}

async def handle_seasonal_shop(client: Client, user_id: int) -> Dict[str, Any]:
    """Routes to the real seasonal shop implementation in EconomyHandler."""
    return await EconomyHandler.handle_seasonal_shop(client, user_id)

async def handle_cancel_reveal(client: Client, user_id: int) -> Dict[str, Any]:
    """Returns to the chat menu from a reveal confirmation."""
    return {
        "text": "💬 **Chatting...**\nSelect an action below:",
        "reply_markup": chat_menu()
    }

async def handle_admin_broadcast(client: Client, user_id: int) -> Dict[str, Any]:
    """Admin broadcast prompt (actual broadcast is via /broadcast command)."""
    from config import ADMIN_ID
    if user_id != ADMIN_ID:
        return {"alert": "🚫 Unauthorized!", "show_alert": True}
    return {"alert": "📢 Use the /broadcast <message> command to send a broadcast.", "show_alert": True}

# Dispatcher Map for Callback Actions
CALLBACK_MAP: Dict[str, Callable[[Client, int, Any], Coroutine[Any, Any, Dict[str, Any]]]] = {
    # Matching
    "search": lambda c, uid, _: MatchingHandler.handle_search(c, uid),
    "cancel_search": lambda c, uid, _: MatchingHandler.handle_cancel(c, uid),
    "stop": lambda c, uid, _: MatchingHandler.handle_stop(c, uid),
    "rematch": lambda c, uid, _: MatchingHandler.handle_rematch(c, uid),
    "next": lambda c, uid, _: MatchingHandler.handle_next(c, uid),
    "icebreaker": lambda c, uid, _: MatchingHandler.handle_icebreaker(c, uid),
    
    # Economy
    "priority_search": lambda c, uid, _: EconomyHandler.handle_priority_search(c, uid),
    "reveal": lambda c, uid, _: EconomyHandler.handle_reveal(c, uid),
    "priority_packs": lambda c, uid, _: EconomyHandler.handle_priority_packs(c, uid),
    "booster_menu": lambda c, uid, _: EconomyHandler.handle_booster_menu(c, uid),
    "seasonal_shop": lambda c, uid, _: handle_seasonal_shop(c, uid),
    "cancel_reveal": lambda c, uid, _: handle_cancel_reveal(c, uid),
    
    # Stats & Leaderboard
    "stats": lambda c, uid, _: StatsHandler.handle_stats(c, uid),
    "leaderboard": lambda c, uid, _: StatsHandler.handle_leaderboard(c, uid),
    "event_leaderboard": lambda c, uid, _: StatsHandler.handle_leaderboard_category(c, uid, "event_leaderboard"),
    
    # Social
    "open_reactions": lambda c, uid, _: SocialHandler.handle_open_reactions(c, uid),
    "back_to_chat": lambda c, uid, _: SocialHandler.handle_back_to_chat(c, uid),
    "cancel_reactions": lambda c, uid, _: SocialHandler.handle_back_to_chat(c, uid),
    "report": lambda c, uid, _: SocialHandler.handle_report(c, uid),
    "report_confirm": lambda c, uid, _: SocialHandler.handle_report_confirm(c, uid),
    "report_with_reason": lambda c, uid, _: SocialHandler.handle_report_with_reason(c, uid),
    "peek": lambda c, uid, _: SocialHandler.handle_peek(c, uid),
    "add_friend": lambda c, uid, _: SocialHandler.handle_add_friend(c, uid),
    "friends_list": lambda c, uid, _: SocialHandler.handle_friends_list(c, uid),
    "view_requests": lambda c, uid, _: SocialHandler.handle_view_requests(c, uid),
    "user_appeal": lambda c, uid, _: SocialHandler.handle_user_appeal(c, uid),
    
    # Onboarding
    "onboarding_start": lambda c, uid, _: OnboardingHandler.handle_start(c, uid),
    "onboarding_skip": lambda c, uid, _: OnboardingHandler.handle_skip(c, uid),
    "set_location_skip": lambda c, uid, _: OnboardingHandler.handle_location_skip(c, uid),
    "set_bio_skip": lambda c, uid, _: OnboardingHandler.handle_bio_skip(c, uid),
    
    # Admin
    "admin_stats": lambda c, uid, _: AdminHandler.handle_stats(c, uid),
    "admin_events": lambda c, uid, _: AdminHandler.handle_admin_events(c, uid),
    "admin_list_banned": lambda c, uid, _: AdminHandler.handle_list_banned_simple(c, uid),
    "admin_health": lambda c, uid, _: AdminHandler.handle_admin_health(c, uid),
    "admin_broadcast_prompt": lambda c, uid, _: AdminHandler.handle_broadcast_prompt(c, uid),
    "admin_gift_prompt": lambda c, uid, _: AdminHandler.handle_gift_prompt(c, uid),
    "admin_deduct_prompt": lambda c, uid, _: AdminHandler.handle_deduct_prompt(c, uid),
    "admin_vip_prompt": lambda c, uid, _: AdminHandler.handle_vip_prompt(c, uid),
    "admin_user_manage_prompt": lambda c, uid, _: AdminHandler.handle_user_manage_prompt(c, uid),
    "admin_debug": lambda c, uid, _: AdminHandler.handle_debug(c, uid),
    "admin_reset_confirm": lambda c, uid, _: AdminHandler.handle_reset_confirm(c, uid),
    "admin_reset_execute": lambda c, uid, _: AdminHandler.handle_reset(c, uid),
    
    # Misc
    "help": lambda c, uid, _: handle_help(c, uid),
}

async def matching_animation(client: Client, user_id: int):
    """Updates searching message with animations while user is in queue."""
    if user_id in match_state.searching_users:
        return
    
    match_state.searching_users.add(user_id)
    msgs = [
        "☀️ Finding someone for you...",
        "☕ Matching soon...",
        "🔎 Sifting through the crowd...",
        "📡 Scanning for active users...",
        "🤝 Connecting you soon..."
    ]
    
    while user_id in match_state.waiting_queue and not match_state.is_in_chat(user_id):
        try:
            await asyncio.sleep(4)
            if user_id not in match_state.waiting_queue or match_state.is_in_chat(user_id):
                break
            await update_user_ui(client, user_id, random.choice(msgs), search_menu())
        except Exception:
            break
            
    match_state.searching_users.discard(user_id)

async def process_response(client: Client, query: CallbackQuery, response: Dict[str, Any]):
    """Unified UI processor for handler responses."""
    user_id = query.from_user.id
    
    # 1. Handle Alert
    if "alert" in response:
        await query.answer(response["alert"], show_alert=response.get("show_alert", False))
        
    # 2. Handle Main UI Update
    if "text" in response:
        try:
            await query.edit_message_text(
                text=response["text"],
                reply_markup=response.get("reply_markup")
            )
        except Exception as e:
            logger.debug(f"UI Update suppressed (no change or message deleted): {e}")

    # 3. Handle External Messages (Partner Notifications)
    if "partner_msg" in response:
        p_data = response["partner_msg"]
        await update_user_ui(client, p_data["target_id"], p_data["text"], p_data.get("reply_markup"))

    if "notify_partner" in response:
        n_data = response["notify_partner"]
        try:
            await client.send_message(
                chat_id=n_data["target_id"],
                text=n_data["text"],
                reply_markup=n_data.get("reply_markup")
            )
        except:
            pass

    # 4. Handle Specialized Actions
    if response.get("start_animation"):
        asyncio.create_task(matching_animation(client, user_id))

    if response.get("special_action") == "send_photo":
        if response.get("photo"):
            await client.send_photo(chat_id=user_id, photo=response["photo"], caption=response.get("caption"))
        else:
            await client.send_message(chat_id=user_id, text=response.get("caption"))

    if "set_state" in response:
        match_state.set_user_state(user_id, response["set_state"])

@Client.on_callback_query()
async def on_callback(client: Client, query: CallbackQuery):
    user_id = query.from_user.id
    data = query.data
    
    # Global Rate Limiting
    now = time.time()
    last_time = match_state.last_button_time.get(user_id, 0)
    if now - last_time < 0.5:
        return await query.answer("Please wait...", show_alert=False)
    match_state.last_button_time[user_id] = now

    # Dispatch to Modular Handlers
    handler = None
    # Precise match
    if data in CALLBACK_MAP:
        handler = CALLBACK_MAP[data]
    # Prefix match (e.g. buy_pack_5)
    else:
        prefixes = [
            "buy_pack_", "admin_manage_ban_", "confirm_reveal_", "react_", 
            "lb_", "buy_booster_", "buy_timed_priority_", "set_gender_",
            "peek_detail_", "accept_friend_", "decline_friend_", "admin_unban_",
            "buy_shop_", "friend_action_", "msg_friend_", "remove_friend_",
            "search_pref_", "admin_set_vip_", "admin_quick_gift_", "admin_ban_",
            "admin_quick_deduct_"
        ]
        for prefix in prefixes:
            if data.startswith(prefix):
                try:
                    param = data.split("_")[-1]
                    if prefix == "buy_pack_":
                        handler = lambda c, uid, p: EconomyHandler.handle_buy_pack(c, uid, int(p))
                    elif prefix == "admin_set_vip_":
                        # Format: admin_set_vip_{target_id}_{true/false}
                        parts = data.split("_")
                        target_id = int(parts[3])
                        status = parts[4]
                        handler = lambda c, uid, p: AdminHandler.handle_set_vip_button(c, uid, target_id, status)
                    elif prefix == "admin_quick_gift_":
                        # Format: admin_quick_gift_{target_id}_{amount}
                        parts = data.split("_")
                        target_id = int(parts[3])
                        amount = int(parts[4])
                        handler = lambda c, uid, p: AdminHandler.handle_quick_gift(c, uid, target_id, amount)
                    elif prefix == "admin_quick_deduct_":
                        # Format: admin_quick_deduct_{target_id}_{amount}
                        parts = data.split("_")
                        target_id = int(parts[3])
                        amount = int(parts[4])
                        handler = lambda c, uid, p: AdminHandler.handle_quick_deduct(c, uid, target_id, amount)
                    elif prefix == "admin_ban_":
                        handler = lambda c, uid, p: AdminHandler.handle_manage_ban(c, uid, int(p))
                    elif prefix == "buy_shop_":
                        handler = lambda c, uid, p: EconomyHandler.handle_buy_shop_badge(c, uid, p)
                    elif prefix == "admin_manage_ban_":
                        handler = lambda c, uid, p: AdminHandler.handle_manage_ban(c, uid, int(p))
                    elif prefix == "confirm_reveal_":
                        handler = lambda c, uid, p: EconomyHandler.handle_confirm_reveal(c, uid, int(p))
                    elif prefix == "react_":
                        handler = lambda c, uid, p: SocialHandler.handle_reaction(c, uid, p)
                    elif prefix == "lb_":
                        handler = lambda c, uid, p: StatsHandler.handle_leaderboard_category(c, uid, p)
                    elif prefix == "buy_booster_":
                        handler = lambda c, uid, p: EconomyHandler.handle_buy_booster(c, uid, int(p))
                    elif prefix == "buy_timed_priority_":
                        handler = lambda c, uid, p: EconomyHandler.handle_buy_timed_priority(c, uid, int(p))
                    elif prefix == "set_gender_":
                        handler = lambda c, uid, p: OnboardingHandler.handle_set_gender(c, uid, p)
                    elif prefix == "peek_detail_":
                        handler = lambda c, uid, p: SocialHandler.handle_peek_detail(c, uid, p)
                    elif prefix == "accept_friend_":
                        handler = lambda c, uid, p: SocialHandler.handle_accept_friend(c, uid, int(p))
                    elif prefix == "decline_friend_":
                        handler = lambda c, uid, p: SocialHandler.handle_decline_friend(c, uid, int(p))
                    elif prefix == "friend_action_":
                        handler = lambda c, uid, p: SocialHandler.handle_friend_action(c, uid, int(p))
                    elif prefix == "msg_friend_":
                        handler = lambda c, uid, p: SocialHandler.handle_msg_friend(c, uid, int(p))
                    elif prefix == "remove_friend_":
                        handler = lambda c, uid, p: SocialHandler.handle_remove_friend(c, uid, int(p))
                    elif prefix == "admin_unban_":
                        handler = lambda c, uid, p: AdminHandler.handle_unban_request(c, uid, int(p))
                    elif prefix == "search_pref_":
                        handler = lambda c, uid, p: MatchingHandler.handle_search_with_pref(c, uid, str(p))
                    
                    if handler:
                        response = await handler(client, user_id, param)
                        return await process_response(client, query, response)
                except Exception as e:
                    logger.error(f"Error parsing prefixed callback {data}: {e}")

    if handler:
        try:
            response = await handler(client, user_id, None)
            if response:
                await process_response(client, query, response)
        except Exception as e:
            logger.exception(f"Error in modular handler for {data}: {e}")
            await query.answer("❌ An internal error occurred.", show_alert=True)
    else:
        await query.answer(f"Action {data} not yet refactored.")
