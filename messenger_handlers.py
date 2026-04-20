# ═══════════════════════════════════════════════════════════════════════
# FILE: messenger_handlers.py
# PURPOSE: Facebook Messenger webhook handlers — mirror of Telegram handlers
# STATUS: HARDENED — All payloads standardized, shop/profile/cooldown fixed
# ═══════════════════════════════════════════════════════════════════════

import os
import time
import logging
import asyncio
from typing import Optional

from flask import request
logger = logging.getLogger(__name__)
from messenger_api import (
    send_message, send_quick_replies, send_typing_on, send_typing_off, mark_seen,
    send_generic_template, send_button_template, record_user_interaction
)
from utils.rate_limiter import rate_limiter
from utils.platform_adapter import PlatformAdapter
from utils.content_filter import check_message, get_user_warning, SEVERITY_AUTO_BAN, SEVERITY_BLOCK
from utils.ui_formatters import format_session_summary, get_match_found_text
from utils.behavior_tracker import behavior_tracker
from messenger.ui import *
from messenger.utils import _uid, _raw, _platform, _send_to, _send_menu_to, _get_or_create_messenger_user

# ─────────────────────────────────────────────────────────────────────
# Distributed State & Repositories
# ─────────────────────────────────────────────────────────────────────
from state.match_state import match_state
from services.distributed_state import distributed_state
from database.repositories.user_repository import UserRepository
import app_state


# ─────────────────────────────────────────────────────────────────────
# Bridge: call shared action handlers and render to Messenger
# ─────────────────────────────────────────────────────────────────────

def _map_reply_markup(reply_markup) -> list:
    """Convert Pyrogram InlineKeyboardMarkup to Messenger quick reply 
    buttons. Matches against callback_data values (lowercase with 
    underscores) which are stable, rather than display text which changes.
    """
    from messenger.ui import (
        get_chat_menu_buttons, get_end_menu_buttons,
        get_start_menu_buttons, get_search_pref_buttons,
        get_retry_search_buttons
    )
    from state.match_state import UserState

    if reply_markup is None:
        return None

    # Convert to string and lowercase for matching against callback_data
    str_markup = str(reply_markup).lower()

    # 1. Chat menu — contains stop and next
    if "stop" in str_markup:
        return get_chat_menu_buttons(UserState.CHATTING)

    # 2. Search Preference menu (Anyone, Male, Female)
    elif "search_pref_any" in str_markup or "search_pref_female" in str_markup or "search_pref_male" in str_markup:
        return get_search_pref_buttons(UserState.HOME)

    # 3. Active Search menu (Priority Match, Packs, Cancel)
    elif "priority_packs" in str_markup or "search_pref_priority" in str_markup:
        # This is the search_menu shown while waiting
        return [{"title": "⚡ Priority (5 coins)", "payload": "PREF_PRIORITY:0:SEARCHING"},
                {"title": "❌ Cancel Search", "payload": "CANCEL_SEARCH:0:SEARCHING"}]

    # 4. End menu with voting buttons — extract partner_id
    elif "vote_like" in str_markup or "vote_dislike" in str_markup:
        import re
        match = re.search(r"vote_like:(\d+)", str_markup)
        partner_id = int(match.group(1)) if match else None
        return get_end_menu_buttons(UserState.HOME, partner_id=partner_id)

    # 5. Start/Home menu (Stats)
    elif "stats" in str_markup and "search" in str_markup:
        return get_start_menu_buttons(UserState.HOME)

    # 6. Retry search menu or generic search-related
    elif "try_searching" in str_markup:
        return get_retry_search_buttons(UserState.HOME)

    # 7. Cancel search fallback
    elif "cancel_search" in str_markup:
        return [{"title": "❌ Cancel", "payload": "CANCEL_SEARCH:0:HOME"}]

    # 8. End menu fallback (if it contains search but not stats/priority)
    elif "search" in str_markup or "rematch" in str_markup:
        return get_end_menu_buttons(UserState.HOME)


    # Unknown markup type — return empty list rather than None
    # so the caller sends a plain text message instead of crashing
    return []


async def _execute_action(psid: str, virtual_id: int, action_coro_fn, *args):
    """Bridge: call a shared action handler and render response to Messenger (Async).
    M2: Guards against None telegram_app during startup/reconnection.
    """
    import app_state
    client = app_state.telegram_app
    if client is None:
        logger.warning(f"_execute_action: telegram_app is None — cross-platform relay unavailable")
    response = await action_coro_fn(client, virtual_id, *args)
    logger.info(f"TRACE _execute_action: response keys = {list(response.keys()) if response else 'None'}")
    if not response:
        return
    if "alert" in response and "text" not in response:
        send_message(psid, response["alert"])
    if "text" in response:
        buttons = _map_reply_markup(response.get("reply_markup"))
        if buttons:
            send_quick_replies(psid, response["text"], buttons)
        else:
            send_message(psid, response["text"])
    if "set_state" in response:
        await match_state.set_user_state(virtual_id, response["set_state"])
    if "partner_msg" in response:
        p = response["partner_msg"]
        if client:  # Only relay if client is available
            await PlatformAdapter.send_cross_platform(client, p["target_id"], p.get("text", ""), p.get("reply_markup"))
    if "notify_partner" in response:
        p = response["notify_partner"]
        if p and client:  # Only relay if client is available
            await PlatformAdapter.send_cross_platform(client, p["target_id"], p.get("text", ""), p.get("reply_markup"))


from messenger.handlers.profile import (
    show_consent_screen, handle_consent_accept, handle_consent_decline,
    handle_profile_setup, handle_set_gender, handle_set_age, handle_set_goal,
    handle_interests_skip, handle_delete_data, handle_confirm_delete,
    handle_edit_profile, handle_set_photo_prompt
)


# ─────────────────────────────────────────────────────────────────────
# Core command handlers (delegates to shared action handlers)
# ─────────────────────────────────────────────────────────────────────

def _send_hero_start(psid: str, coins: int, is_guest: bool):
    """Send the 'Neonymo' Rich Hero Card with direct actions."""
    # We still use the Hero Card for the main entry as it's the premium 'Look' for Messenger
    # but we ensure the payloads match the standardized statebound system.
    elements = [{
        "title": "Neonymo — Anonymous Chat",
        "subtitle": f"💰 Balance: {coins} coins | Meet Nearby. Stay Unknown.",
        "image_url": LOGO_URL,
        "buttons": [
            {"type": "postback", "title": "🔍 Find Partner", "payload": StateBoundPayload.encode("SEARCH", "0", "HOME")},
            {"type": "postback", "title": "👤 My Profile",   "payload": StateBoundPayload.encode("CMD_PROFILE", "0", "HOME")},
            {"type": "postback", "title": "📊 My Stats",     "payload": StateBoundPayload.encode("STATS", "0", "HOME")}
        ]
    }]
    send_generic_template(psid, elements)
    if is_guest:
        from utils.renderer import Renderer
        response = Renderer.render_profile_menu("messenger", "HOME")
        send_quick_replies(psid, "⚠️ Guest Mode: No rewards earned.", response["quick_replies"])


async def _handle_start(psid: str, virtual_id: int, user: dict):
    """Handle /start — show the premium Welcome Card."""
    send_generic_template(psid, get_welcome_card())
    if user.get("is_guest", True):
        send_button_template(
            psid,
            "You're in Guest Mode. Set up your profile to unlock XP and Coins!",
            [{"type": "postback", "title": "👤 Set Up Profile", "payload": "CMD_PROFILE:0:HOME"}]
        )


from messenger.handlers.matchmaking import (
    handle_search, handle_search_with_pref, handle_stop, handle_next, handle_cancel_search
)
from messenger.handlers.social import (
    handle_add_friend, handle_confirm_friend, handle_report, handle_block_partner
)


async def _notify_partner_matched(partner_virtual_id: int):
    """Notify a matched partner (Async)."""
    await behavior_tracker.record_session_start(partner_virtual_id)

    if partner_virtual_id >= 10**15:
        partner_user = await UserRepository.get_by_telegram_id(partner_virtual_id)
        if partner_user:
            username = partner_user.get("username", "")
            if username.startswith("msg_"):
                partner_psid = username[4:]
                if await behavior_tracker.is_new_user(partner_virtual_id):
                    send_typing_on(partner_psid)
                    await asyncio.sleep(await behavior_tracker.get_typing_delay())
                    send_typing_off(partner_psid)
                
                now = time.time()
                last_safety = partner_user.get("safety_last_seen", 0)
                show_safety = (now - last_safety > 86400)
                if show_safety:
                    asyncio.create_task(UserRepository.update(partner_virtual_id, safety_last_seen=int(now)))

                from utils.renderer import Renderer
                response = Renderer.render_match_found("messenger", partner_virtual_id, show_safety=show_safety)
                send_quick_replies(partner_psid, response["text"], response["quick_replies"])
                
                warning = await behavior_tracker.get_match_warning(partner_virtual_id)
                if warning: send_message(partner_psid, warning)
                
                hint = await behavior_tracker.get_contextual_hint(partner_virtual_id, "connected")
                if hint: send_message(partner_psid, hint)
    else:
        try:
            import app_state
            if app_state.telegram_app:
                await app_state.telegram_app.send_message(
                    chat_id=partner_virtual_id,
                    text=get_match_found_text()
                )
        except Exception as e:
            logger.error(f"Async match notify failed for tg: {partner_virtual_id}: {e}")


async def _handle_stats(psid: str, virtual_id: int, user: dict):
    """Show visual profile card (Async)."""
    send_generic_template(psid, get_stats_card(user))

async def handle_seasonal_shop(psid: str, virtual_id: int):
    """Show shop carousel (Async)."""
    send_message(psid, "🛍 **Seasonal Shop**\nUse your coins to buy exclusive badges!")
    send_generic_template(psid, get_shop_carousel())


async def handle_buy_item(psid: str, virtual_id: int, item: str):
    """Process a shop purchase (Async)."""
    from services.user_service import UserService
    
    SHOP_ITEMS = {
        "BUY_VIP":   {"name": "30-Day VIP",       "cost": 500, "field": "vip_status",  "value": True, "duration": 30 * 86400},
        "BUY_OG":    {"name": "'OG User' Badge",   "cost": 300, "field": "badge_og",    "value": True},
        "BUY_WHALE": {"name": "'Whale' Badge",     "cost": 1000, "field": "badge_whale", "value": True},
    }
    
    item_data = SHOP_ITEMS.get(item)
    if not item_data:
        send_message(psid, "❌ Unknown shop item.")
        return
    
    # Deduct coins
    if not await UserService.deduct_coins(virtual_id, item_data["cost"]):
        send_quick_replies(
            psid,
            f"❌ Insufficient coins!\n\nYou need {item_data['cost']} coins for {item_data['name']}.",
            get_start_menu_buttons(UserState.HOME)
        )
        return
    
    # Apply the purchase
    update_data = {item_data["field"]: item_data["value"]}
    if "duration" in item_data:
        update_data["vip_expires_at"] = int(time.time()) + item_data["duration"]
    await UserRepository.update(virtual_id, **update_data)
    
    # Confirm
    user = await UserRepository.get_by_telegram_id(virtual_id)
    coins = user.get("coins", 0) if user else 0
    send_quick_replies(
        psid,
        f"✅ **Purchase Successful!**\n\n"
        f"🎁 {item_data['name']} activated!\n"
        f"💰 Remaining balance: {coins} coins",
        get_start_menu_buttons(UserState.HOME)
    )


def _handle_help(psid: str):
    """Show help — button-driven."""
    text = (
        "ℹ️ How It Works\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "1. Tap 🔍 Find Partner to match with a stranger.\n"
        "2. Chat anonymously — your identity stays hidden.\n"
        "3. Earn coins and XP by chatting!\n\n"
        "Use the buttons below to navigate."
    )
    send_quick_replies(psid, text, START_MENU_BUTTONS)


def _handle_settings_menu(psid: str):
    """Show the settings menu."""
    send_button_template(psid, "⚙️ Settings\n\nManage your profile and account.", SETTINGS_MENU_BUTTONS)


async def _handle_relay_message(psid: str, virtual_id: int, text: str):
    """Relay Messenger text to match partner (Async)."""
    # 1. Check partner
    _p = await match_state.get_partner(virtual_id)
    partner_id = int(_p) if _p else None
    if not partner_id:
        send_quick_replies(psid, "You're not chatting with anyone yet.", IDLE_MENU_BUTTONS)
        return
        
    # 2. Record behavior
    await behavior_tracker.record_message_sent(virtual_id, text)
    await behavior_tracker.record_message_received(partner_id)

    try:
        is_safe, violation = check_message(text)
        if not is_safe:
            from utils.content_filter import apply_enforcement
            decision = await apply_enforcement(virtual_id, violation)
            final_sev = decision["final_severity"]
            action = decision["action"]
            penalty = decision["penalty"]

            if penalty > 0:
                from services.user_service import UserService
                await UserService.deduct_coins(virtual_id, penalty)
            
            warning = get_user_warning(final_sev, decision["description"], penalty)
            send_message(psid, warning)

            if action in ("terminate_chat", "auto_ban_user"):
                from services.matchmaking import MatchmakingService
                from services.user_service import UserService
                await MatchmakingService.disconnect(virtual_id)
                if partner_id:
                    await UserService.report_user(virtual_id, partner_id, f"Auto-Mod: {decision['description']}")
                    await _notify_user(partner_id, "❌ Chat ended. Your partner was removed by the Auto-Moderator.")
                
                if action == "auto_ban_user":
                    await UserRepository.set_blocked(virtual_id, True)
            return

        from services.user_service import UserService
        await UserService.increment_challenge(virtual_id, "messages_sent")
        await _notify_user(partner_id, f"💬 {text}")
    except Exception as e:
        logger.error(f"Messenger relay failed from {virtual_id} to {partner_id}: {e}", exc_info=True)
        send_quick_replies(psid, "⚠️ **Delivery Error:** Your message could not be delivered.", get_chat_menu_buttons(UserState.CHATTING))


async def _notify_user(partner_virtual_id: int, text: str):
    """Route a notification to a user on their correct platform (Async)."""
    if partner_virtual_id == 1: return
    
    # Defensive casting
    partner_virtual_id = int(partner_virtual_id)

    if partner_virtual_id >= 10**15:
        u = await UserRepository.get_by_telegram_id(partner_virtual_id)
        u = await UserRepository.get_by_telegram_id(partner_virtual_id)
        if u and u.get("username", "").startswith("msg_"):
            psid = u["username"][4:]
            
            # If partner is in CHATTING state, always include the chat buttons
            current_partner_state = await match_state.get_user_state(partner_virtual_id)
            if current_partner_state == UserState.CHATTING:
                buttons = get_chat_menu_buttons(UserState.CHATTING)
                send_quick_replies(psid, text, buttons)
            else:
                send_message(psid, text)
    else:
        try:
            import app_state
            if app_state.telegram_app:
                await app_state.telegram_app.send_message(chat_id=int(partner_virtual_id), text=text)
        except Exception as e:
            logger.error(f"Telegram relay failed for {partner_virtual_id}: {e}")


async def _notify_media(partner_virtual_id: int, media_type: str, url: str, caption: str = None):
    """Send native media (photos, stickers) to any platform (Async)."""
    # Defensive casting
    partner_virtual_id = int(partner_virtual_id)

    if partner_virtual_id >= 10**15:
        u = await UserRepository.get_by_telegram_id(partner_virtual_id)
        if u and u.get("username", "").startswith("msg_"):
            p_psid = u["username"][4:]
            if media_type == "image":
                from messenger_api import send_image
                send_image(p_psid, url)
            else:
                send_message(p_psid, f"📎 [Partner sent a {media_type}]\n{url}")
    else:
        import app_state
        if app_state.telegram_app:
            try:
                if media_type == "image":
                    await app_state.telegram_app.send_photo(chat_id=int(partner_virtual_id), photo=url, caption=caption)
                elif media_type == "video":
                    await app_state.telegram_app.send_video(chat_id=int(partner_virtual_id), video=url, caption=caption)
                elif media_type == "sticker":
                    await app_state.telegram_app.send_sticker(chat_id=int(partner_virtual_id), sticker=url)
                else:
                    await app_state.telegram_app.send_message(chat_id=int(partner_virtual_id), text=f"📎 [Partner sent a {media_type}]\n{url}")
            except Exception as e:
                logger.warning(f"Failed to relay native media to Telegram: {e}")


async def handle_messenger_text(psid: str, virtual_id: int, user: dict, text: str):
    """Route text messages (Async)."""
    # 1. Invariant Recovery Hook — re-render CURRENT state, never force HOME
    if not await distributed_state.validate_session(virtual_id, repair=True):
        current_state = await match_state.get_user_state(virtual_id) or UserState.HOME
        logger.warning(f"TRACE: validate_session failed for {virtual_id}, re-rendering state={current_state}")
        send_quick_replies(psid, "⚠️ **Session sync issue detected. Re-syncing your UI...**",
                           get_start_menu_buttons(current_state))
        return

    if not await rate_limiter.can_send_message(virtual_id):
        remaining = await rate_limiter.get_cooldown_remaining(virtual_id, "message") or 0
        send_message(psid, f"⏳ Please wait {remaining:.0f}s.")
        return

    text_stripped = text.strip()
    state = await match_state.get_user_state(virtual_id)
    
    if state:
        if state == "awaiting_photo":
            # User typed text instead of sending a photo
            send_message(psid, "📷 Please send an image, not text. Just tap the 📎 icon and pick a photo!")
            return
        elif state == "awaiting_interests":
            await UserRepository.update(virtual_id, interests=text_stripped[:100])
            await match_state.set_user_state(virtual_id, "awaiting_location")
            send_message(psid, "✅ Interests saved!\n\n📍 Where are you from?")
            return
        elif state == "awaiting_location":
            await UserRepository.update(virtual_id, location=text_stripped[:50])
            await match_state.set_user_state(virtual_id, "awaiting_bio")
            send_message(psid, "✅ Location saved.\n\n📝 Tell us a bit about yourself!")
            return
        elif state == "awaiting_bio":
            from services.user_service import UserService
            await UserService.update_profile(virtual_id, gender=user.get("gender", "Other"), location=user.get("location", "Secret"), bio=text_stripped[:200])
            await match_state.set_user_state(virtual_id, None)
            send_quick_replies(psid, "✅ Profile Complete!", START_MENU_BUTTONS)
            return

    if text_stripped.startswith("/"):
        cmd = text_stripped.split()[0].lower()
        if cmd in ("/start", "/menu"): await _handle_start(psid, virtual_id, user)
        elif cmd in ("/search", "/find"): await handle_search(psid, virtual_id, user)
        elif cmd == "/stop": await handle_stop(psid, virtual_id)
        elif cmd in ("/next", "/skip"): await handle_next(psid, virtual_id, user)
        elif cmd in ("/stats", "/me"): await _handle_stats(psid, virtual_id, user)
        elif cmd == "/shop": await handle_seasonal_shop(psid, virtual_id)
        elif cmd == "/help": _handle_help(psid)
        elif cmd == "/profile": await handle_profile_setup(psid, virtual_id)
        elif cmd == "/report": await handle_report(psid, virtual_id)
        elif cmd == "/block": await handle_block_partner(psid, virtual_id)
        elif cmd == "/delete": await handle_delete_data(psid, virtual_id)
        else: send_quick_replies(psid, "Unknown command.", IDLE_MENU_BUTTONS)
    else:
        await _handle_relay_message(psid, virtual_id, text_stripped)


async def handle_messenger_quick_reply(psid: str, virtual_id: int, user: dict, payload: str):
    """Refactored: Handle quick reply buttons via Unified Engine (Phase 5: Auth Rehydration)."""
    uid = f"msg_{psid}"
    
    # 1. Translate to Event
    event = await app_state.msg_adapter.translate_event({"sender": {"id": psid}, "message": {"quick_reply": {"payload": payload}}})
    if not event:
        # Legacy/Other routing fallback
        return await _handle_legacy_messenger_action(psid, virtual_id, user, payload)

    # 2. Process via Engine
    # ActionRouter.process_event handles all state transitions, symmetric partner notifications,
    # and UI rehydration internally.
    result = await app_state.engine.process_event(event)
    
    if not result.get("success") and "error" in result:
        # Handle failures (e.g. Hard Gate)
        error = result["error"]
        await app_state.msg_adapter.send_error(uid, error)
        # Attempt recovery re-render
        await app_state.engine.process_event({"event_type": "RECOVER", "user_id": uid})



async def _handle_legacy_messenger_action(psid: str, virtual_id: int, user: dict, payload: str):
    """Old handlers for non-matchmaking actions (Profile, Shop, etc)."""
    from utils.renderer import StateBoundPayload
    from state.match_state import UserState
    action, target_id, parsed_state = StateBoundPayload.decode(payload)
    current_state = await match_state.get_user_state(virtual_id) or UserState.HOME
    logger.info(f"TRACE _handle_legacy: action={action} parsed_state={parsed_state} current_state={current_state}")

    # ── Matchmaking actions (all live-session payloads must be handled here) ────
    if action in ("SEARCH", "CMD_START"):
        # Safe to call even while SEARCHING/CHATTING — guarded internally
        await handle_search(psid, virtual_id, user)
    elif action in ("PREF_ANY", "SEARCH_PREF_ANY"):
        await handle_search_with_pref(psid, virtual_id, user, "Any")
    elif action == "CMD_STATS":
        await _handle_stats(psid, virtual_id, user)
    elif action in ("PREF_MALE", "SEARCH_PREF_MALE"):
        await handle_search_with_pref(psid, virtual_id, user, "Male")
    elif action in ("PREF_FEMALE", "SEARCH_PREF_FEMALE"):
        await handle_search_with_pref(psid, virtual_id, user, "Female")
    elif action in ("PREF_PRIORITY",):
        await handle_search_with_pref(psid, virtual_id, user, "Priority")
    elif action in ("CANCEL_SEARCH", "STOP_SEARCH"):
        await handle_cancel_search(psid, virtual_id)
    elif action in ("NEXT", "CMD_NEXT"):
        await handle_next(psid, virtual_id, user)
    elif action in ("STOP", "CMD_STOP"):
        await handle_stop(psid, virtual_id)
    # ── Profile / Account actions ────────────────────────────────────────────────
    elif action == "CMD_PROFILE": await handle_profile_setup(psid, virtual_id)
    elif action == "EDIT_PROFILE": await handle_edit_profile(psid, virtual_id)
    elif action == "SET_PHOTO": await handle_set_photo_prompt(psid, virtual_id)
    elif action == "STATS": await _handle_stats(psid, virtual_id, user)
    elif action == "SEASONAL_SHOP": await handle_seasonal_shop(psid, virtual_id)
    elif action == "HELP": _handle_help(psid)
    elif action == "SETTINGS_MENU": _handle_settings_menu(psid)
    elif action == "DELETE_DATA": await handle_delete_data(psid, virtual_id)
    elif action in ("ADD_FRIEND",): await handle_add_friend(psid, virtual_id)
    elif action == "REPORT": await handle_report(psid, virtual_id)
    elif action == "BLOCK_PARTNER": await handle_block_partner(psid, virtual_id)
    elif action in ("BACK_HOME",):
        send_quick_replies(psid, "🏠 Main Menu", get_start_menu_buttons(current_state))
    # ── Unknown action: re-render current state instead of forcing HOME ──────────
    else:
        logger.warning(f"TRACE _handle_legacy: Unknown action '{action}'. Re-rendering current_state={current_state} (not HOME).")
        if current_state == UserState.CHATTING:
            send_quick_replies(psid, "💬 You are in a chat. Use the buttons below.",
                               get_chat_menu_buttons(UserState.CHATTING))
        elif current_state == UserState.SEARCHING:
            send_quick_replies(psid, "🔍 Still searching...",
                               [{"title": "❌ Cancel Search", "payload": "CANCEL_SEARCH:0:SEARCHING"}])
        else:
            send_quick_replies(psid, "🏠 Main Menu", get_start_menu_buttons(current_state))



async def handle_messenger_postback(psid: str, virtual_id: int, user: dict, payload: str):
    """Handle postback events (Async)."""
    from utils.renderer import StateBoundPayload
    from state.match_state import UserState

    # 1. Invariant Recovery Hook — re-render CURRENT state, never force HOME
    if not await distributed_state.validate_session(virtual_id, repair=True):
        current_state = await match_state.get_user_state(virtual_id) or UserState.HOME
        logger.warning(f"TRACE: validate_session failed for {virtual_id}, re-rendering state={current_state}")
        send_quick_replies(psid, "🔄 Refreshing your session...", get_start_menu_buttons(current_state))
        return

    action, target_id, parsed_state = StateBoundPayload.decode(payload)

    if action == "GET_STARTED":
        if user and user.get("consent_given_at"): await _handle_start(psid, virtual_id, user)
        else: await show_consent_screen(psid)
    elif action == "CMD_START": await _handle_start(psid, virtual_id, user)
    elif action == "SEARCH": await handle_search(psid, virtual_id, user)
    elif action == "STATS": await _handle_stats(psid, virtual_id, user)
    elif action == "SEASONAL_SHOP" or action == "SHOP_MENU": await handle_seasonal_shop(psid, virtual_id)
    elif action in ("BUY_VIP", "BUY_OG", "BUY_WHALE"): await handle_buy_item(psid, virtual_id, action)
    elif action == "CMD_NEXT": await handle_next(psid, virtual_id, user)
    elif action == "CMD_STOP": await handle_stop(psid, virtual_id)
    elif action == "SETTINGS_MENU": _handle_settings_menu(psid)
    elif action == "CMD_PROFILE": await handle_profile_setup(psid, virtual_id)
    elif action == "EDIT_PROFILE": await handle_edit_profile(psid, virtual_id)
    elif action == "SET_PHOTO": await handle_set_photo_prompt(psid, virtual_id)
    elif action == "DELETE_DATA": await handle_delete_data(psid, virtual_id)
    elif action == "HELP": _handle_help(psid)
    elif action == "CONSENT_ACCEPT": await handle_consent_accept(psid, virtual_id, user)
    elif action == "CONSENT_DECLINE": handle_consent_decline(psid)
    else:
        # Delegate to quick_reply handler for any other encoded payloads
        await handle_messenger_quick_reply(psid, virtual_id, user, payload)


async def handle_messenger_attachment(psid: str, virtual_id: int, attachments: list):
    """Handle media attachments (Async)."""
    from state.match_state import UserState
    # 1. Invariant Recovery Hook — re-render CURRENT state, never force HOME
    if not await distributed_state.validate_session(virtual_id, repair=True):
        current_state = await match_state.get_user_state(virtual_id) or UserState.HOME
        logger.warning(f"TRACE: validate_session failed for {virtual_id}, re-rendering state={current_state}")
        send_quick_replies(psid, "⚠️ Session sync issue.", get_start_menu_buttons(current_state))
        return

    state = await match_state.get_user_state(virtual_id)
    partner_id = await match_state.get_partner(virtual_id)
    
    # Check if user is in "awaiting_photo" state for profile photo
    if state == "awaiting_photo":
        for att in attachments:
            if att.get("type") == "image":
                url = att.get("payload", {}).get("url")
                if url:
                    await UserRepository.update(virtual_id, profile_photo=url)
                    await match_state.set_user_state(virtual_id, None)
                    send_quick_replies(
                        psid,
                        "📸 **Profile Photo Updated!**\n\nYour photo has been saved. It will be shown if you reveal your identity.",
                        get_start_menu_buttons(UserState.HOME)
                    )
                    return
        send_message(psid, "⚠️ Please send a photo (not a file or sticker).")
        return
    
    if not partner_id:
        # Not in chat — try to save as profile photo
        for att in attachments:
            if att.get("type") == "image":
                url = att.get("payload", {}).get("url")
                if url:
                    await UserRepository.update(virtual_id, profile_photo=url)
                    send_quick_replies(
                        psid,
                        "📸 **Profile Photo Updated!**\n\nThis photo will be shown if you choose to reveal your identity.",
                        get_start_menu_buttons(UserState.HOME)
                    )
                    return
        send_quick_replies(psid, "⚠️ No active chat. Send a photo to set it as your profile picture!", IDLE_MENU_BUTTONS)
        return

    for att in attachments:
        url = att.get("payload", {}).get("url")
        if url: await _notify_media(partner_id, att.get("type", "file"), url, caption="💬")


async def handle_messenger_call(psid: str, virtual_id: int, user: dict, call_data: dict):
    """Handle incoming calls (Async)."""
    partner_id = await match_state.get_partner(virtual_id)
    if not partner_id:
        send_quick_replies(psid, "Start a chat first.", IDLE_MENU_BUTTONS)
        return

    try:
        room_name = f"neonymo-{min(virtual_id, partner_id)}-{max(virtual_id, partner_id)}"
        meet_link = f"https://meet.jit.si/{room_name}"
        import app_state
        await PlatformAdapter.send_cross_platform(app_state.telegram_app, partner_id, f"📞 **Incoming Call!**\n👉 {meet_link}", None)
        send_message(psid, f"✅ Partner notified!\n👉 {meet_link}")
    except Exception as e:
        logger.error(f"Messenger call failed for {partner_id}: {e}", exc_info=True)
        send_quick_replies(psid, "⚠️ **Delivery Error:** Call could not be initiated.", get_chat_menu_buttons(UserState.CHATTING))
