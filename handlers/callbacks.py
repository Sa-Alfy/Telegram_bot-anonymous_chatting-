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
from state.match_state import match_state
from database.repositories.user_repository import UserRepository
from services.user_service import UserService
from utils.helpers import update_user_ui
from utils.logger import logger
from utils.keyboard import search_menu, chat_menu, start_menu, admin_menu
from config import ADMIN_ID
from state.match_state import UserState
from utils.renderer import StateBoundPayload

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
    "admin_reset_confirm": lambda c, uid, _: AdminHandler.handle_reset_confirm(c, uid),
    "admin_reset_execute": lambda c, uid, _: AdminHandler.handle_reset(c, uid),
    
    # Misc
    "help": lambda c, uid, _: handle_help(c, uid),
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
    user_id = query.from_user.id
    raw_data = query.data

    # 1. Decode payload (action, target, state-hint)
    action, target_str, parsed_state = StateBoundPayload.decode(raw_data)
    target_id = int(target_str) if target_str.isdigit() else 0
    
    # Normalize action for matching
    data = action.lower()

    # 2. Global rate limit (UI-layer debounce, not the concurrency lock)
    now = time.time()
    last_time = match_state.last_button_time.get(user_id, 0)
    if now - last_time < 1.0:
        return await query.answer("Please wait...", show_alert=False)
    match_state.last_button_time[user_id] = now

    # 3. Concurrency lock — prevents double-click / race conditions.
    #    Uses Redis SET NX EX (atomic) in production; memory fallback locally.
    from services.distributed_state import distributed_state
    acquired = await distributed_state.acquire_action_lock(user_id, ttl=3)
    if not acquired:
        return await query.answer("⏳ Processing your previous action...", show_alert=False)

    try:
        # 4. STATE AUTHORITY: Always read from server. payload.state is HINT only.
        current_state = await match_state.get_user_state(user_id) or UserState.HOME

        # 5. Stale UI Detection: Reject interactions from old menus (C15 fix).
        #    If payload.state exists and does not match server state, the menu is expired.
        #    EXCEPTION: Some actions are state-agnostic (can be done anywhere).
        state_agnostic_actions = {"stats", "leaderboard", "terms", "privacy", "help"}
        
        is_stale = False
        
        # Session Binding Logic: Check if the state contains a partner ID (e.g., CHATTING_12345)
        parsed_session_id = 0
        canonical_parsed_state = parsed_state
        if parsed_state and "_" in parsed_state:
            parts = parsed_state.split("_")
            canonical_parsed_state = parts[0]
            try: parsed_session_id = int(parts[1])
            except: pass

        if parsed_state and canonical_parsed_state != current_state:
            # HOME state buttons are allowed as long as the user isn't in a critical locking state
            if canonical_parsed_state == UserState.HOME and current_state not in {UserState.CONTENT_REVIEW, UserState.MATCHED_PENDING}:
                is_stale = False
            # During transition from HOME to SEARCHING or CHATTING, stay lenient
            elif canonical_parsed_state in {UserState.HOME, UserState.SEARCHING} and current_state == UserState.CHATTING:
                is_stale = False
            elif action not in state_agnostic_actions:
                is_stale = True
        
        # Critical Session Check: Even if State matches (CHATTING), Partner must match!
        if current_state == UserState.CHATTING and parsed_session_id > 0:
            current_partner = await match_state.get_partner(user_id)
            if current_partner != parsed_session_id:
                logger.warning(f"Session Mismatch! User {user_id} clicked button for {parsed_session_id} but is chatting with {current_partner}")
                is_stale = True

        if is_stale:
            # Determine if this was a legitimate state change or a retry
            logger.info(f"Stale UI rejected: {user_id} tried {action} (from {parsed_state}) while in {current_state}")
            await query.answer("❌ This menu has expired.", show_alert=True)
            from utils.renderer import Renderer
            return await process_response(client, query, Renderer.render_profile_menu("telegram", current_state))

        # 6. Client-initiated transition map (server-only states are NOT in this map)
        intent_to_state = {
            "search":          UserState.SEARCHING,
            "cancel_search":   UserState.HOME,
            "back_home":       UserState.HOME,
            "onboarding_start": UserState.PROFILE_EDIT,
            "onboarding_skip": UserState.HOME,
        }

        if action in intent_to_state:
            target_state = intent_to_state[action]

            # AUTHORITY: Reject client attempt to set a system-only state
            if not UserState.is_client_settable(target_state):
                await query.answer("❌ Invalid action.", show_alert=True)
                return

            # Transition validity check
            if not UserState.is_valid_transition(current_state, target_state):
                await query.answer("❌ You cannot do that right now.", show_alert=True)
                from utils.renderer import Renderer
                return await process_response(client, query, Renderer.render_profile_menu("telegram", current_state))

            # TARGET INTEGRITY: Validate target exists before transitioning
            if target_id:
                is_valid, reason = await match_state.validate_target(target_id)
                if not is_valid:
                    await query.answer(f"❌ {reason}", show_alert=True)
                    from utils.renderer import Renderer
                    return await process_response(client, query, Renderer.render_profile_menu("telegram", current_state))

            # Server sets the new state (not from payload)
            await match_state.set_user_state(user_id, target_state)

        # Use action for routing (not raw payload)
        data = action

        # Dispatch to Modular Handlers
        handler = None
        # Precise match
        if data in CALLBACK_MAP:
            handler = CALLBACK_MAP[data]
        # Prefix match (e.g. buy_pack_5)
        else:
            prefixes = [
                "buy_pack_", "admin_manage_ban_", "confirm_reveal_", "react_",
                "lb_", "buy_booster_", "buy_timed_priority_", "set_gender_", "set_age_", "set_goal_",
                "peek_detail_", "accept_friend_", "decline_friend_", "admin_unban_",
                "buy_shop_", "friend_action_", "msg_friend_", "remove_friend_",
                "search_pref_", "admin_set_vip_", "admin_quick_gift_", "admin_ban_",
                "admin_quick_deduct_", "vote_"
            ]
            for prefix in prefixes:
                if data.startswith(prefix):
                    try:
                        param = target_id
                        if prefix == "buy_pack_":
                            handler = lambda c, uid, p: EconomyHandler.handle_buy_pack(c, uid, int(p))
                        elif prefix == "vote_":
                            parts = action.split("_")
                            # Robust ID extraction: use target_id if provided, else last part of action
                            tid = target_id if target_id != 0 else (int(parts[-1]) if parts[-1].isdigit() else 0)
                            # Robust vote_type: everything between 'vote_' and the ID
                            v_type = "_".join(parts[1:-1]) if target_id == 0 else "_".join(parts[1:])
                            handler = lambda c, uid, _, t=tid, vt=v_type: VotingHandler.handle_vote(c, uid, t, vt)
                        elif prefix == "admin_set_vip_":
                            parts = action.split("_")
                            try:
                                tid = int(parts[3])
                                status = parts[4]
                            except (IndexError, ValueError):
                                continue
                            handler = lambda c, uid, p: AdminHandler.handle_set_vip_button(c, uid, tid, status)
                        elif prefix == "admin_quick_gift_":
                            parts = action.split("_")
                            try:
                                tid = int(parts[3])
                                amount = int(parts[4])
                            except (IndexError, ValueError):
                                continue
                            handler = lambda c, uid, p: AdminHandler.handle_quick_gift(c, uid, tid, amount)
                        elif prefix == "admin_quick_deduct_":
                            parts = action.split("_")
                            try:
                                tid = int(parts[3])
                                amount = int(parts[4])
                            except (IndexError, ValueError):
                                continue
                            handler = lambda c, uid, p: AdminHandler.handle_quick_deduct(c, uid, tid, amount)
                        elif prefix == "buy_shop_":
                            handler = lambda c, uid, p, val=action[len(prefix):]: EconomyHandler.handle_buy_shop_badge(c, uid, val)
                        elif prefix == "react_":
                            handler = lambda c, uid, p, val=action[len(prefix):]: SocialHandler.handle_reaction(c, uid, val)
                        elif prefix == "lb_":
                            handler = lambda c, uid, p, val=action[len(prefix):]: StatsHandler.handle_leaderboard_category(c, uid, val)
                        elif prefix == "buy_booster_":
                            handler = lambda c, uid, p, val=action[len(prefix):]: EconomyHandler.handle_buy_booster(c, uid, int(val))
                        elif prefix == "buy_timed_priority_":
                            handler = lambda c, uid, p, val=action[len(prefix):]: EconomyHandler.handle_buy_timed_priority(c, uid, int(val))
                        elif prefix == "set_gender_":
                            handler = lambda c, uid, p, val=action[len(prefix):]: OnboardingHandler.handle_set_gender(c, uid, val)
                        elif prefix == "set_age_":
                            handler = lambda c, uid, p, val=action[len(prefix):]: OnboardingHandler.handle_set_age(c, uid, val)
                        elif prefix == "set_goal_":
                            handler = lambda c, uid, p, val=action[len(prefix):]: OnboardingHandler.handle_set_goal(c, uid, val.capitalize())
                        elif prefix == "peek_detail_":
                            handler = lambda c, uid, p, val=action[len(prefix):]: SocialHandler.handle_peek_detail(c, uid, val)
                        elif prefix == "search_pref_":
                            handler = lambda c, uid, p, val=action[len(prefix):]: MatchingHandler.handle_search_with_pref(c, uid, val)
                        elif prefix == "admin_ban_":
                            tid = target_id if target_id != 0 else (int(action.split("_")[-1]) if action.split("_")[-1].isdigit() else 0)
                            handler = lambda c, uid, p, t=tid: AdminHandler.handle_manage_ban(c, uid, t)
                        elif prefix == "admin_manage_ban_":
                            tid = target_id if target_id != 0 else (int(action.split("_")[-1]) if action.split("_")[-1].isdigit() else 0)
                            handler = lambda c, uid, p, t=tid: AdminHandler.handle_manage_ban(c, uid, t)
                        elif prefix == "confirm_reveal_":
                            handler = lambda c, uid, p: EconomyHandler.handle_confirm_reveal(c, uid, int(p))
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
                            tid = target_id if target_id != 0 else (int(action.split("_")[-1]) if action.split("_")[-1].isdigit() else 0)
                            handler = lambda c, uid, p, t=tid: AdminHandler.handle_unban_request(c, uid, t)

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

    finally:
        # Always release the action lock — prevents deadlocks on any exception path
        await distributed_state.release_action_lock(user_id)

