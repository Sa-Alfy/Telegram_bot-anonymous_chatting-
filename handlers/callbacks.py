import time
import asyncio
import random
from typing import Dict, Any, Callable, Coroutine
from pyrogram import Client, filters
from pyrogram.types import CallbackQuery, ReplyKeyboardRemove

from handlers.actions.matching import MatchingHandler
from handlers.actions.economy import EconomyHandler
from handlers.actions.admin import AdminHandler
from handlers.actions.social import SocialHandler
from handlers.actions.stats import StatsHandler
from handlers.actions.onboarding import OnboardingHandler
from handlers.actions.voting import VotingHandler
from handlers.actions.matching import _fire

from state.match_state import match_state
from database.repositories.user_repository import UserRepository
from services.user_service import UserService
from utils.helpers import update_user_ui
from utils.logger import logger
from adapters.telegram.keyboards import search_menu, chat_menu, start_menu, admin_menu
from config import ADMIN_ID
from state.match_state import UserState
from utils.renderer import StateBoundPayload
import app_state


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
    if user_id != ADMIN_ID:
        return {"alert": "🚫 Unauthorized!", "show_alert": True}
    return {"alert": "📢 Use the /broadcast <message> command to send a broadcast.", "show_alert": True}

async def handle_consent_accept(client: Client, user_id: int) -> Dict[str, Any]:
    """Record user consent and show main menu."""
    await UserRepository.update(user_id, consent_given_at=int(time.time()))
    user = await UserRepository.get_by_telegram_id(user_id)
    return {
        "text": "✅ **Terms Accepted!**\nWelcome to Neonymo. You can now search for partners and earn rewards.",
        "reply_markup": start_menu(user.get("is_guest", True))
    }

async def handle_consent_decline(client: Client, user_id: int) -> Dict[str, Any]:
    """Handle consent decline."""
    return {
        "text": "❌ **Terms Declined**\n\nYou must accept the Terms of Service to use Neonymo. If you change your mind, click /start to try again.",
        "reply_markup": None
    }

# Dispatcher Map for Callback Actions (Only non-matchmaking/supporting actions)
CALLBACK_MAP: Dict[str, Callable[[Client, int, Any], Coroutine[Any, Any, Dict[str, Any]]]] = {
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
    "peek_streak": lambda c, uid, _: SocialHandler.handle_peek_streak(c, uid),
    "peek_level": lambda c, uid, _: SocialHandler.handle_peek_level(c, uid),
    "add_friend": lambda c, uid, _: SocialHandler.handle_add_friend(c, uid),
    "friends_list": lambda c, uid, _: SocialHandler.handle_friends_list(c, uid),
    "view_requests": lambda c, uid, _: SocialHandler.handle_view_requests(c, uid),
    "user_appeal": lambda c, uid, _: SocialHandler.handle_user_appeal(c, uid),
    "cancel_friend_msg": lambda c, uid, _: SocialHandler.handle_cancel_friend_msg(c, uid),
    
    # Onboarding
    "onboarding_start": lambda c, uid, _: OnboardingHandler.handle_start(c, uid),
    "onboarding_skip": lambda c, uid, _: OnboardingHandler.handle_skip(c, uid),
    "set_interests_skip": lambda c, uid, _: OnboardingHandler.handle_interests_skip(c, uid),
    "set_location_skip": lambda c, uid, _: OnboardingHandler.handle_location_skip(c, uid),
    "set_bio_skip": lambda c, uid, _: OnboardingHandler.handle_bio_skip(c, uid),
    
    # Consent
    "consent_accept": lambda c, uid, _: handle_consent_accept(c, uid),
    "consent_decline": lambda c, uid, _: handle_consent_decline(c, uid),
    
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
    "admin_peek_queue": lambda c, uid, _: AdminHandler.handle_peek_queue(c, uid),
    "admin_view_logs": lambda c, uid, _: AdminHandler.handle_view_logs(c, uid),
    "admin_reset_confirm": lambda c, uid, _: AdminHandler.handle_reset_confirm(c, uid),
    "admin_reset_execute": lambda c, uid, _: AdminHandler.handle_reset(c, uid),
    
    # Misc
    "help": lambda c, uid, _: handle_help(c, uid),
    
    # Matching
    "icebreaker": lambda c, uid, _: MatchingHandler.handle_icebreaker(c, uid),
    "cancel_search": lambda c, uid, _: MatchingHandler.handle_cancel(c, uid),
    
    # Onboarding — gender
    "set_gender_male":   lambda c, uid, _: OnboardingHandler.handle_set_gender(c, uid, "Male"),
    "set_gender_female": lambda c, uid, _: OnboardingHandler.handle_set_gender(c, uid, "Female"),
    "set_gender_other":  lambda c, uid, _: OnboardingHandler.handle_set_gender(c, uid, "Other"),
    
    # Onboarding — age
    "set_age_18-21": lambda c, uid, _: OnboardingHandler.handle_set_age(c, uid, "18-21"),
    "set_age_22-25": lambda c, uid, _: OnboardingHandler.handle_set_age(c, uid, "22-25"),
    "set_age_26-29": lambda c, uid, _: OnboardingHandler.handle_set_age(c, uid, "26-29"),
    "set_age_30+":   lambda c, uid, _: OnboardingHandler.handle_set_age(c, uid, "30+"),
    
    # Onboarding — goal
    "set_goal_chat":    lambda c, uid, _: OnboardingHandler.handle_set_goal(c, uid, "chat"),
    "set_goal_dating":  lambda c, uid, _: OnboardingHandler.handle_set_goal(c, uid, "dating"),
    "set_goal_friends": lambda c, uid, _: OnboardingHandler.handle_set_goal(c, uid, "friends"),
    
    # Economy — shop
    "buy_shop_vip":   lambda c, uid, _: EconomyHandler.handle_buy_shop_badge(c, uid, "vip"),
    "buy_shop_og":    lambda c, uid, _: EconomyHandler.handle_buy_shop_badge(c, uid, "og"),
    "buy_shop_whale": lambda c, uid, _: EconomyHandler.handle_buy_shop_badge(c, uid, "whale"),
    
    # Economy — packs & boosters
    "buy_pack_5":             lambda c, uid, _: EconomyHandler.handle_buy_pack(c, uid, 5),
    "buy_pack_15":            lambda c, uid, _: EconomyHandler.handle_buy_pack(c, uid, 15),
    "buy_timed_priority_1":   lambda c, uid, _: EconomyHandler.handle_buy_timed_priority(c, uid, 1),
    "buy_timed_priority_3":   lambda c, uid, _: EconomyHandler.handle_buy_timed_priority(c, uid, 3),
    "buy_timed_priority_24":  lambda c, uid, _: EconomyHandler.handle_buy_timed_priority(c, uid, 24),
    "buy_booster_1":          lambda c, uid, _: EconomyHandler.handle_buy_booster(c, uid, 1),
    
    # Leaderboard filters
    "lb_event": lambda c, uid, _: StatsHandler.handle_leaderboard_category(c, uid, "event"),
    "lb_all":   lambda c, uid, _: StatsHandler.handle_leaderboard_category(c, uid, "all"),
    
    # Reactions
    "react_heart": lambda c, uid, _: SocialHandler.handle_reaction(c, uid, "heart"),
    "react_joy":   lambda c, uid, _: SocialHandler.handle_reaction(c, uid, "joy"),
    "react_wow":   lambda c, uid, _: SocialHandler.handle_reaction(c, uid, "wow"),
    "react_sad":   lambda c, uid, _: SocialHandler.handle_reaction(c, uid, "sad"),
    "react_up":    lambda c, uid, _: SocialHandler.handle_reaction(c, uid, "up"),
}

async def matching_animation(client: Client, user_id: int):
    """Updates searching message with animations while user is in queue.
    H6: Uses Redis-backed dedup instead of in-process set for cross-worker correctness.
    """
    from services.distributed_state import distributed_state
    from state.match_state import UserState
    # Guard against multiple animation tasks per user (works across workers)
    if await distributed_state.is_duplicate_interaction(user_id, "search_anim", ttl=8):
        return
    
    msgs = [
        "☀️ Finding someone for you...",
        "☕ Matching soon...",
        "🔎 Sifting through the crowd...",
        "📡 Scanning for active users...",
        "🤝 Connecting you soon..."
    ]
    
    try:
        # Initial wait
        await asyncio.sleep(2.5)
        
        # Double check: Is user actually still searching?
        # Check both the chat pairing and the explicit user state
        if not await match_state.is_in_chat(user_id):
            current_state = await match_state.get_user_state(user_id)
            if current_state == UserState.SEARCHING:
                await update_user_ui(client, user_id, random.choice(msgs), search_menu())
    except Exception as e:
        logger.debug(f"Matching animation failed for {user_id}: {e}")


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
        await update_user_ui(client, p_data["target_id"], p_data["text"], p_data.get("reply_markup"), force_new=True)

    if "notify_partner" in response:
        n_data = response["notify_partner"]
        try:
            from utils.helpers import send_cross_platform
            await send_cross_platform(client, n_data["target_id"], n_data["text"], n_data.get("reply_markup"))
        except Exception as e:
            logger.error(f"notify_partner failed: {e}")

    # 4. Handle Specialized Actions
    if response.get("start_animation"):
        asyncio.create_task(matching_animation(client, user_id))

    if response.get("special_action") == "send_photo":
        if response.get("photo"):
            sent = await client.send_photo(chat_id=user_id, photo=response["photo"], caption=response.get("caption"))
            await match_state.track_ui_message(user_id, sent.id)
        else:
            sent = await client.send_message(chat_id=user_id, text=response.get("caption"))
            await match_state.track_ui_message(user_id, sent.id)

    if response.get("special_action") == "remove_keyboard":
        # Removes Telegram persistent keyboard and cleans up history when returning home/ending chat
        history = await match_state.get_ui_history(user_id)
        if history:
            try:
                await client.delete_messages(user_id, history[:100])
            except: pass
        await match_state.clear_ui_history(user_id)
        _fire(client.send_message(user_id, "🏠 **Returning to Dashboard...**", reply_markup=ReplyKeyboardRemove()))

    if "set_state" in response:
        await match_state.set_user_state(user_id, response["set_state"])

@Client.on_callback_query()
async def on_callback(client: Client, query: CallbackQuery):
    user_id_int = query.from_user.id
    user_id = str(user_id_int)
    data = query.data
    
    # 1. Lockout Protection (Telegram UI)
    now = time.time()
    last_click = match_state.last_button_time.get(user_id_int, 0)
    if now - last_click < 1.5:
        return await query.answer("Please wait...", show_alert=False)
    match_state.last_button_time[user_id_int] = now

    # 2. Translate to Event via Adapter
    event = await app_state.tg_adapter.translate_event(query)
    if not event:
        # LEGACY FALLBACK: Direct routing for non-engine buttons (search, stats, etc)
        if data == "search":
            from handlers.actions.matching import MatchingHandler
            await MatchingHandler.handle_search(client, user_id_int)
            return await query.answer()
        elif data == "stats":
            from handlers.actions.stats import StatsHandler
            await StatsHandler.handle_stats(client, user_id_int)
            return await query.answer()
        return await query.answer()
        
    if event["event_type"] == "LEGACY_DISPATCH":
        raw = event["payload"]["raw_data"]
        action_key = raw.split(":")[0].lower()
        handler = CALLBACK_MAP.get(action_key)
        if handler:
            response = await handler(client, int(event["user_id"]), event)
            if response:
                await process_response(client, query, response)
            return await query.answer()

        # Dynamic prefix callbacks — handle before giving up
        uid_int = int(event["user_id"])
        try:
            if action_key.startswith("friend_action_"):
                friend_id = raw.replace("friend_action_", "")
                response = await SocialHandler.handle_friend_action(client, uid_int, friend_id)
            elif action_key.startswith("msg_friend_"):
                friend_id = raw.replace("msg_friend_", "")
                response = await SocialHandler.handle_msg_friend(client, uid_int, friend_id)
            elif action_key.startswith("remove_friend_"):
                friend_id = raw.replace("remove_friend_", "")
                response = await SocialHandler.handle_remove_friend(client, uid_int, friend_id)
            elif action_key.startswith("accept_friend_"):
                sender_id = raw.replace("accept_friend_", "")
                response = await SocialHandler.handle_accept_friend(client, uid_int, sender_id)
            elif action_key.startswith("decline_friend_"):
                sender_id = raw.replace("decline_friend_", "")
                response = await SocialHandler.handle_decline_friend(client, uid_int, sender_id)
            elif action_key.startswith("confirm_reveal_"):
                cost = int(raw.split("_")[-1])
                response = await EconomyHandler.handle_confirm_reveal(client, uid_int, cost)
            else:
                logger.warning(f"Unhandled callback: {raw}")
                return await query.answer("This button isn't available right now.", show_alert=True)
            if response:
                await process_response(client, query, response)
            return await query.answer()
        except (ValueError, IndexError) as e:
            logger.error(f"Dynamic callback parse failed for '{raw}': {e}")
            return await query.answer("Something went wrong.", show_alert=True)

    # 3. Concurrency check & Process via Engine
    result = await app_state.engine.process_event(event)

    if not result.get("success") and "error" in result:
        # Handle failures (e.g. Hard Gate)
        error = result["error"]
        await app_state.tg_adapter.send_error(user_id, error)
        await query.answer(error, show_alert=True)
        # Attempt recovery re-render
        await app_state.engine.process_event({"event_type": "RECOVER", "user_id": user_id})
    
    await query.answer()
