# ═══════════════════════════════════════════════════════════════════════
# FILE: messenger_handlers.py
# PURPOSE: Facebook Messenger webhook handlers — Refactored for Engine Sovereignty
# ═══════════════════════════════════════════════════════════════════════

import os
import time
import logging
import asyncio
from typing import Optional, Any

from flask import request
logger = logging.getLogger(__name__)
from messenger_api import (
    send_message, send_quick_replies, send_typing_on, send_typing_off, mark_seen,
    send_generic_template, send_button_template, record_user_interaction
)
from utils.rate_limiter import rate_limiter
from utils.platform_adapter import PlatformAdapter
from utils.content_filter import check_message, get_user_warning, SEVERITY_AUTO_BAN, SEVERITY_BLOCK
from utils.ui_formatters import get_match_found_text
from utils.behavior_tracker import behavior_tracker
from adapters.messenger.ui_factory import *
from messenger.utils import _uid, _raw, _platform, _send_to, _send_menu_to, _get_or_create_messenger_user

# ─────────────────────────────────────────────────────────────────────
# Distributed State & Repositories
# ─────────────────────────────────────────────────────────────────────
from state.match_state import match_state
from services.distributed_state import distributed_state
from database.repositories.user_repository import UserRepository
from handlers.actions.economy import EconomyHandler
from handlers.actions.matching import MatchingHandler
from handlers.actions.voting import VotingHandler

import app_state

# ─────────────────────────────────────────────────────────────────────
# Bridge: call shared action handlers and render to Messenger
# ─────────────────────────────────────────────────────────────────────

def _map_reply_markup(reply_markup) -> list:
    """Convert Pyrogram InlineKeyboardMarkup to Messenger quick reply buttons."""
    from adapters.messenger.ui_factory import (
        get_chat_menu_buttons, get_end_menu_buttons,
        get_start_menu_buttons, get_search_pref_buttons,
        get_retry_search_buttons
    )
    from state.match_state import UserState

    if reply_markup is None:
        return None

    str_markup = str(reply_markup).lower()

    if "stop" in str_markup:
        return get_chat_menu_buttons(UserState.CHATTING)
    elif "search_pref_any" in str_markup or "search_pref_female" in str_markup or "search_pref_male" in str_markup:
        return get_search_pref_buttons(UserState.HOME)
    elif "priority_packs" in str_markup or "search_pref_priority" in str_markup:
        return [{"title": "⚡ Priority (5 coins)", "payload": "PREF_PRIORITY:0:SEARCHING"},
                {"title": "❌ Cancel Search", "payload": "CANCEL_SEARCH:0:SEARCHING"}]
    elif "vote_like" in str_markup or "vote_dislike" in str_markup:
        import re
        match = re.search(r"vote_like:(\d+)", str_markup)
        partner_id = int(match.group(1)) if match else None
        return get_end_menu_buttons(UserState.HOME, partner_id=partner_id)
    elif "stats" in str_markup and "search" in str_markup:
        return get_start_menu_buttons(UserState.HOME)
    elif "try_searching" in str_markup:
        return get_retry_search_buttons(UserState.HOME)
    elif "cancel_search" in str_markup:
        return [{"title": "❌ Cancel", "payload": "CANCEL_SEARCH:0:HOME"}]
    elif "rematch" in str_markup:
        import re
        match = re.search(r"rematch:(\d+)", str_markup)
        partner_id = int(match.group(1)) if match else None
        return get_end_menu_buttons(UserState.HOME, partner_id=partner_id)
    elif "search" in str_markup:
        return get_end_menu_buttons(UserState.HOME)

    return []

async def _execute_action(psid: str, virtual_id: int, action_coro_fn, *args):
    """Bridge for legacy handlers."""
    import app_state
    client = app_state.telegram_app
    response = await action_coro_fn(client, virtual_id, *args)
    if not response: return
    if "alert" in response and "text" not in response:
        send_message(psid, response["alert"])
    if "text" in response:
        buttons = _map_reply_markup(response.get("reply_markup"))
        if buttons: send_quick_replies(psid, response["text"], buttons)
        else: send_message(psid, response["text"])

from messenger.handlers.profile import (
    show_consent_screen, handle_consent_accept, handle_consent_decline,
    handle_profile_setup, handle_set_gender, handle_set_age, handle_set_goal,
    handle_interests_skip, handle_delete_data, handle_confirm_delete,
    handle_edit_profile, handle_set_photo_prompt
)

# ─────────────────────────────────────────────────────────────────────
# Core logic (mostly migrated to Engine)
# ─────────────────────────────────────────────────────────────────────

async def _handle_start(psid: str, virtual_id: int, user: dict):
    """Handle /start — show the premium Welcome Card."""
    send_generic_template(psid, get_welcome_card())
    if user.get("is_guest", True):
        send_button_template(
            psid,
            "You're in Guest Mode. Set up your profile to unlock XP and Coins!",
            [{"type": "postback", "title": "👤 Set Up Profile", "payload": "CMD_PROFILE:0:HOME"}]
        )

async def _notify_partner_matched(partner_virtual_id: int):
    """Notify a matched partner (Async)."""
    await behavior_tracker.record_session_start(partner_virtual_id)
    if partner_virtual_id >= 10**15:
        partner_user = await UserRepository.get_by_telegram_id(partner_virtual_id)
        if partner_user and partner_user.get("username", "").startswith("msg_"):
            partner_psid = partner_user["username"][4:]
            text = get_match_found_text(is_rematch=False)
            buttons = get_chat_menu_buttons(UserState.CHATTING)
            send_quick_replies(partner_psid, text, buttons)
    else:
        if app_state.telegram_app:
            await app_state.telegram_app.send_message(chat_id=partner_virtual_id, text=get_match_found_text())

async def _handle_stats(psid: str, virtual_id: int, user: dict):
    send_generic_template(psid, get_stats_card(user))

async def _notify_user(partner_virtual_id: Any, text: str):
    """Simplified relay notification."""
    is_messenger = str(partner_virtual_id).startswith("msg_") or (isinstance(partner_virtual_id, int) and partner_virtual_id >= 10**15)
    if is_messenger:
        u = await UserRepository.get_by_telegram_id(partner_virtual_id)
        if u and u.get("username", "").startswith("msg_"):
            send_message(u["username"][4:], text)
    else:
        if app_state.telegram_app:
            await app_state.telegram_app.send_message(chat_id=int(partner_virtual_id), text=text)

# ─────────────────────────────────────────────────────────────────────
# Main Webhook Entry Points
# ─────────────────────────────────────────────────────────────────────

async def handle_messenger_text(psid: str, virtual_id: int, user: dict, text: str):
    """Route text messages (Async). Refactored for Engine."""
    if not await distributed_state.validate_session(virtual_id, repair=True):
        await app_state.engine.process_event({"event_type": "RECOVER", "user_id": str(virtual_id)})
        return

    text_stripped = text.strip()
    uid = f"msg_{psid}"
    
    # 1. Engine Translation Hook
    event = await app_state.msg_adapter.translate_event({"sender": {"id": psid}, "message": {"text": text_stripped}})
    if event:
        event["user_id"] = str(virtual_id)
        result = await app_state.engine.process_event(event)
        if result.get("success"): return
        logger.warning(f"Engine failed to process {event['event_type']} for {virtual_id}: {result.get('error', 'Unknown Error')}")
    
    # 2. Legacy Command Fallback
    if text_stripped.startswith("/"):
        pass # Migrated commands handled by Engine hook above
    else:
        # Fallback for unhandled text
        pass

async def handle_messenger_quick_reply(psid: str, virtual_id: int, user: dict, payload: str):
    """Handle buttons via Engine."""
    uid = f"msg_{psid}"
    event = await app_state.msg_adapter.translate_event({"sender": {"id": psid}, "message": {"quick_reply": {"payload": payload}}})
    if not event:
        return await _handle_legacy_messenger_action(psid, virtual_id, user, payload)

    event["user_id"] = str(virtual_id)
    result = await app_state.engine.process_event(event)
    if not result.get("success"):
        if "error" in result:
            await app_state.msg_adapter.send_error(str(virtual_id), result["error"])
        await app_state.engine.process_event({"event_type": "RECOVER", "user_id": str(virtual_id)})

async def _handle_legacy_messenger_action(psid: str, virtual_id: int, user: dict, payload: str):
    """Legacy action routing."""
    from utils.renderer import StateBoundPayload
    from state.match_state import UserState
    action, target_id, parsed_state = StateBoundPayload.decode(payload)
    current_state = await match_state.get_user_state(virtual_id) or UserState.HOME

    if action == "SET_PHOTO": await handle_set_photo_prompt(psid, virtual_id)
    elif action == "SETTINGS_MENU": _handle_settings_menu(psid)
    elif action in ("ADD_FRIEND",): await handle_add_friend(psid, virtual_id)
    elif action == "CONFIRM_FRIEND": await handle_confirm_friend(psid, virtual_id)
    elif action == "STOP_SEARCH":
        await app_state.engine.process_event({"event_type": "CANCEL_SEARCH", "user_id": str(virtual_id)})
    else:
        # Unknown or legacy action -> Force Engine to re-evaluate state
        logger.info(f"Unknown legacy action {action} for {virtual_id}. Triggering Engine recovery.")
        from app_state import engine
        await engine.process_event({
            "event_type": "RECOVER",
            "user_id": str(virtual_id),
            "payload": {}
        })

async def handle_messenger_postback(psid: str, virtual_id: int, user: dict, payload: str):
    """Unified postback handling."""
    return await handle_messenger_quick_reply(psid, virtual_id, user, payload)

async def handle_messenger_attachment(psid: str, virtual_id: int, attachments: list):
    """Handle attachments via Engine."""
    uid = f"msg_{psid}"
    event = await app_state.msg_adapter.translate_event({"sender": {"id": psid}, "message": {"attachments": attachments}})
    if event:
        event["user_id"] = str(virtual_id)
        await app_state.engine.process_event(event)
    else:
        # Fallback for profile photo
        for att in attachments:
            if att.get("type") == "image":
                url = att.get("payload", {}).get("url")
                await UserRepository.update(virtual_id, profile_photo=url)
                send_quick_replies(psid, "📸 **Profile Photo Updated!**", get_start_menu_buttons(UserState.HOME))
                return

async def handle_messenger_call(psid: str, virtual_id: int, user: dict, call_data: dict):
    """Handle incoming Jitsi calls."""
    partner_id = await match_state.get_partner(virtual_id)
    if not partner_id: return
    room_name = f"neonymo-{min(virtual_id, partner_id)}-{max(virtual_id, partner_id)}"
    meet_link = f"https://meet.jit.si/{room_name}"
    await PlatformAdapter.send_cross_platform(app_state.telegram_app, partner_id, f"📞 **Incoming Call!**\n👉 {meet_link}", None)
    send_message(psid, f"✅ Partner notified!\n👉 {meet_link}")

def _handle_settings_menu(psid: str):
    send_button_template(psid, "⚙️ Settings", SETTINGS_MENU_BUTTONS)
