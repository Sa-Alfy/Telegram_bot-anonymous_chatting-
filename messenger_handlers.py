# ═══════════════════════════════════════════════════════════════════════
# FILE: messenger_handlers.py
# PURPOSE: Facebook Messenger webhook handlers — mirror of Telegram handlers
# STATUS: NEW FILE
# DEPENDENCIES: messenger_api.py, state/match_state.py, database/*, services/*
# ═══════════════════════════════════════════════════════════════════════

import os
import logging
import asyncio
from typing import Optional

from flask import request
from messenger_api import (
    send_message, send_quick_replies, send_typing_on, send_typing_off, mark_seen
)

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────
# Prefix helpers (mirrors platform_abstraction convention)
# ─────────────────────────────────────────────────────────────────────

def _uid(psid: str) -> str:
    """Convert raw PSID to a namespaced messenger user key."""
    return f"msg_{psid}"


def _raw(uid: str) -> str:
    """Strip prefix to get raw PSID or telegram_id."""
    if uid.startswith("msg_"):
        return uid[4:]
    if uid.startswith("tg_"):
        return uid[3:]
    return uid


def _platform(uid: str) -> str:
    return "messenger" if uid.startswith("msg_") else "telegram"


# ─────────────────────────────────────────────────────────────────────
# In-memory state for Messenger users (mirrors MatchState for cross-platform)
# ─────────────────────────────────────────────────────────────────────
# We import the SAME match_state singleton used by Pyrogram handlers.
# This gives us a shared queue across both platforms.
from state.match_state import match_state
from database.connection import db
from database.repositories.user_repository import UserRepository

# ─────────────────────────────────────────────────────────────────────
# Helper: send to any platform user by prefixed uid
# ─────────────────────────────────────────────────────────────────────

def _send_to(uid: str, text: str):
    """Send a text message to any user (Telegram or Messenger) by prefixed uid."""
    if uid.startswith("msg_"):
        send_message(_raw(uid), text)
    elif uid.startswith("tg_"):
        # Telegram sends are async — schedule via the running event loop
        raw_id = int(_raw(uid))
        try:
            import app_state
            if app_state.bot_loop and app_state.bot_loop.is_running() and app_state.telegram_app:
                asyncio.run_coroutine_threadsafe(
                    app_state.telegram_app.send_message(chat_id=raw_id, text=text),
                    app_state.bot_loop
                )
        except Exception as e:
            logger.error(f"❌ Failed to send Telegram message to {uid}: {e}")


def _send_menu_to(uid: str, text: str, buttons: list):
    """Send message + buttons. On Messenger: quick_replies. On Telegram: best effort text."""
    if uid.startswith("msg_"):
        if buttons:
            send_quick_replies(_raw(uid), text, buttons)
        else:
            send_message(_raw(uid), text)
    else:
        _send_to(uid, text)


# ─────────────────────────────────────────────────────────────────────
# Messenger user management (creates DB records for Messenger users)
# ─────────────────────────────────────────────────────────────────────

async def _get_or_create_messenger_user(psid: str) -> dict:
    """Get or create a DB record for a Messenger user using a virtual telegram_id."""
    # Use a deterministic hash of PSID into a large integer to avoid collision with real TG ids
    import hashlib
    psid_hash = int(hashlib.md5(psid.encode()).hexdigest(), 16)
    virtual_id = (psid_hash % (10**15)) + 10**15
    user = await UserRepository.get_by_telegram_id(virtual_id)
    if not user:
        user = await UserRepository.create(virtual_id, username=f"msg_{psid}", first_name=f"Messenger User {psid[-4:]}")
        logger.info(f"🆕 New Messenger user registered: PSID {psid} → virtual_id {virtual_id}")
    return user, virtual_id


def _run_async(coro):
    """Run a coroutine from a sync Flask handler context by passing it to the main bot loop."""
    try:
        import app_state
        loop = app_state.bot_loop
        if loop and loop.is_running():
            future = asyncio.run_coroutine_threadsafe(coro, loop)
            return future.result(timeout=15)
        else:
            logger.error("❌ Main event loop is not running.")
            return None
    except Exception as e:
        logger.error(f"❌ Async execution error: {e}")
        return None


# ─────────────────────────────────────────────────────────────────────
# Quick reply menus (Messenger equivalents to Telegram keyboards)
# ─────────────────────────────────────────────────────────────────────

START_MENU_BUTTONS = [
    {"title": "🔍 Find Partner", "payload": "SEARCH"},
    {"title": "📊 My Stats",     "payload": "STATS"},
    {"title": "🏆 Leaderboard",  "payload": "LEADERBOARD"},
    {"title": "ℹ️ Help",         "payload": "HELP"},
]

SEARCH_PREF_BUTTONS = [
    {"title": "👫 Anyone",  "payload": "PREF_ANY"},
    {"title": "👩 Female",  "payload": "PREF_FEMALE"},
    {"title": "👨 Male",    "payload": "PREF_MALE"},
    {"title": "❌ Cancel",  "payload": "CANCEL_SEARCH"},
]

CHAT_MENU_BUTTONS = [
    {"title": "⏭ Next",     "payload": "NEXT"},
    {"title": "🛑 Stop",     "payload": "STOP"},
    {"title": "⚠️ Report",  "payload": "REPORT"},
    {"title": "💌 Friend",  "payload": "ADD_FRIEND"},
]

END_MENU_BUTTONS = [
    {"title": "🔍 Find New",    "payload": "SEARCH"},
    {"title": "📊 My Stats",    "payload": "STATS"},
]

GENDER_BUTTONS = [
    {"title": "👨 Male",   "payload": "SET_GENDER_male"},
    {"title": "👩 Female", "payload": "SET_GENDER_female"},
    {"title": "🌈 Other",  "payload": "SET_GENDER_other"},
]

# ─────────────────────────────────────────────────────────────────────
# Core command handlers (same logic as Telegram handlers)
# ─────────────────────────────────────────────────────────────────────

def _handle_start(psid: str, virtual_id: int, user: dict):
    """Handle /start or GET_STARTED — show welcome + main menu."""
    is_guest = user.get("is_guest", 1)
    coins = user.get("coins", 0)
    guest_note = "\n\n⚠️ Guest Mode: Type /profile to earn XP & Coins!" if is_guest else ""
    text = (
        f"🤖 Anonymous Chat\n\n"
        f"Connect with a random stranger.\n\n"
        f"💰 Your Balance: {coins} coins"
        f"{guest_note}"
    )
    send_quick_replies(psid, text, START_MENU_BUTTONS)


def _handle_search(psid: str, virtual_id: int, user: dict):
    """Show gender-preference menu to start searching."""
    send_quick_replies(
        psid,
        "🔍 Matchmaking Preferences\n\nWho are you looking for today?",
        SEARCH_PREF_BUTTONS
    )


def _handle_search_with_pref(psid: str, virtual_id: int, user: dict, pref: str):
    """Add user to queue and attempt to match."""
    uid = _uid(psid)

    if match_state.is_in_chat(virtual_id):
        send_message(psid, "⚠️ You are already in a chat! Type /stop to end it first.")
        return

    # Charge for gender filter (non-VIP)
    if pref in ["Male", "Female"]:
        if not user.get("vip_status") and user.get("coins", 0) < 15:
            send_message(psid, "❌ Gender filters cost 15 coins for non-VIPs!")
            return

    async def _do_search():
        from services.matchmaking import MatchmakingService
        success = await MatchmakingService.add_to_queue(virtual_id, gender_pref=pref)
        if not success:
            send_message(psid, "⚠️ You are already in a chat or queue!")
            return

        partner_virt_id = await MatchmakingService.find_partner(None, virtual_id)
        if partner_virt_id:
            # Match found — notify both
            partner_uid = match_state.active_chats.get(virtual_id)
            _send_menu_to(
                _uid(psid),
                "💬 Match Found!\nYou are now chatting with a stranger...\n\nSend messages freely. Use the buttons below:",
                CHAT_MENU_BUTTONS
            )
            # Notify partner too (could be Telegram or Messenger)
            if partner_virt_id != virtual_id:
                partner_psid = str(partner_virt_id)  # raw virtual id for lookup
                # Determine how to notify partner
                _notify_partner_matched(partner_virt_id)
        else:
            send_quick_replies(
                psid,
                f"⏳ Searching for a partner...\nFilter: {pref}\n\nUse the buttons below to cancel or wait.",
                [{"title": "❌ Cancel", "payload": "CANCEL_SEARCH"}]
            )

    _run_async(_do_search())


def _notify_partner_matched(partner_virtual_id: int):
    """Notify a matched partner. Detects if they are Messenger or Telegram."""
    # Check if this is a Messenger virtual user (id >= 10^15)
    if partner_virtual_id >= 10**15:
        # It's a Messenger user — look up PSID via username field
        async def _get_and_notify():
            partner_user = await UserRepository.get_by_telegram_id(partner_virtual_id)
            if partner_user:
                username = partner_user.get("username", "")  # "msg_{psid}"
                if username.startswith("msg_"):
                    partner_psid = username[4:]
                    send_quick_replies(
                        partner_psid,
                        "💬 Match Found!\nYou are now chatting with a stranger...",
                        CHAT_MENU_BUTTONS
                    )
        _run_async(_get_and_notify())
    else:
        # Telegram user — send notification via the shared Pyrogram client
        try:
            import app_state
            if app_state.bot_loop and app_state.bot_loop.is_running() and app_state.telegram_app:
                asyncio.run_coroutine_threadsafe(
                    app_state.telegram_app.send_message(
                        chat_id=partner_virtual_id,
                        text="💬 Match Found!\nYou are now chatting with a stranger from Messenger..."
                    ),
                    app_state.bot_loop
                )
        except Exception as e:
            logger.error(f"❌ Cross-platform match notify failed for tg:{partner_virtual_id}: {e}")


def _handle_stop(psid: str, virtual_id: int):
    """Disconnect from current chat."""
    async def _do_stop():
        from services.matchmaking import MatchmakingService
        stats = await MatchmakingService.disconnect(virtual_id)
        if not stats:
            send_quick_replies(psid, "❌ You are not in a chat.", END_MENU_BUTTONS)
            return

        partner_id = stats["partner_id"]
        duration = stats.get("duration_minutes", 0)
        coins_earned = stats.get("coins_earned", 0)
        xp_earned = stats.get("xp_earned", 0)

        summary = (
            f"✨ Chat Session Summary ✨\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"⌛ Duration: {duration} min\n"
            f"💰 Coins: +{coins_earned}\n"
            f"📈 XP Gained: +{xp_earned}\n"
            f"━━━━━━━━━━━━━━━━━━"
        )
        send_quick_replies(psid, summary, END_MENU_BUTTONS)

        # Notify partner
        partner_summary = "❌ Chat ended by stranger.\n\n" + summary
        _notify_user(partner_id, partner_summary)

    _run_async(_do_stop())


def _handle_next(psid: str, virtual_id: int, user: dict):
    """Skip to next partner — disconnect and auto-search."""
    async def _do_next():
        from services.matchmaking import MatchmakingService
        stats = await MatchmakingService.disconnect(virtual_id)
        if stats:
            partner_id = stats["partner_id"]
            _notify_user(partner_id, "⏭ Partner skipped to the next chat.")

        # Auto re-queue
        success = await MatchmakingService.add_to_queue(virtual_id, gender_pref="Any")
        if not success:
            send_quick_replies(psid, "❌ Could not rejoin queue.", END_MENU_BUTTONS)
            return

        new_partner = await MatchmakingService.find_partner(None, virtual_id)
        if new_partner:
            send_quick_replies(
                psid,
                "💬 Match Found!\nYou are now chatting with a stranger...",
                CHAT_MENU_BUTTONS
            )
            _notify_partner_matched(new_partner)
        else:
            send_quick_replies(
                psid,
                "⏳ Searching for a new partner...",
                [{"title": "❌ Cancel", "payload": "CANCEL_SEARCH"}]
            )

    _run_async(_do_next())


def _handle_stats(psid: str, virtual_id: int):
    """Show user statistics."""
    async def _do_stats():
        user = await UserRepository.get_by_telegram_id(virtual_id)
        if not user:
            send_message(psid, "❌ Profile not found.")
            return

        is_guest = user.get("is_guest", 1)
        guest_tag = " (Guest)" if is_guest else ""
        vip_tag = " ✨ VIP" if user.get("vip_status") else ""
        text = (
            f"📊 User Statistics{guest_tag}{vip_tag}\n\n"
            f"💰 Balance: {user.get('coins', 0)} coins\n"
            f"💬 Total Matches: {user.get('total_matches', 0)}\n"
            f"📈 Total XP: {user.get('xp', 0)} XP\n"
            f"🔥 Daily Streak: {user.get('daily_streak', 0)} days\n"
            f"⌛ Level: {user.get('level', 1)}\n\n"
            "Earn more coins by chatting and staying active!"
        )
        send_quick_replies(psid, text, START_MENU_BUTTONS)

    _run_async(_do_stats())


def _handle_help(psid: str):
    """Show help / how it works."""
    text = (
        "ℹ️ How to use Anonymous Chat Bot\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "1. 🔍 Find Partner: Search for a random stranger.\n"
        "2. 👤 Profile: Set gender, bio for better matches.\n"
        "3. 💰 Economy: Earn coins by chatting.\n"
        "4. 🛡 Moderation: Report offensive users.\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        "Commands:\n"
        "/start — Main menu\n"
        "/search — Find a partner\n"
        "/stop — End current chat\n"
        "/next — Skip to next partner\n"
        "/stats — View your stats\n"
        "/profile — Set up your profile\n"
        "/report — Report current partner\n"
        "/help — This message"
    )
    send_quick_replies(psid, text, START_MENU_BUTTONS)


def _handle_cancel_search(psid: str, virtual_id: int):
    """Cancel an active queue search."""
    async def _do_cancel():
        from services.matchmaking import MatchmakingService
        await MatchmakingService.remove_from_queue(virtual_id)
        user = await UserRepository.get_by_telegram_id(virtual_id)
        coins = user.get("coins", 0) if user else 0
        send_quick_replies(
            psid,
            f"✅ Search cancelled.\n\n💰 Your Balance: {coins} coins",
            START_MENU_BUTTONS
        )

    _run_async(_do_cancel())


def _handle_report(psid: str, virtual_id: int):
    """Report the current chat partner."""
    partner_id = match_state.get_partner(virtual_id)
    if not partner_id:
        send_message(psid, "❌ You are not in a chat!")
        return

    async def _do_report():
        from services.matchmaking import MatchmakingService
        from services.user_service import UserService
        stats = await MatchmakingService.disconnect(virtual_id)
        await UserService.report_user(virtual_id, partner_id, "Reported via Messenger")
        send_quick_replies(
            psid,
            "🚨 Report Submitted.\nThe user has been flagged for review. Chat ended.",
            END_MENU_BUTTONS
        )
        _notify_user(partner_id, "❌ Chat ended. Your partner has left.")

    _run_async(_do_report())


def _handle_relay_message(psid: str, virtual_id: int, text: str):
    """Relay a text message to the partner."""
    partner_id = match_state.get_partner(virtual_id)
    if not partner_id:
        send_quick_replies(
            psid,
            "⚠️ You are not in a chat. Use Find Partner to connect!",
            START_MENU_BUTTONS
        )
        return

    # Auto-mod filter
    text_lower = text.lower()
    toxic_keywords = ["cp ", "child porn", "t.me/joinchat", "t.me/+", "onlyfans.com", "bitcoin double"]
    if any(word in text_lower for word in toxic_keywords):
        async def _auto_ban():
            from services.matchmaking import MatchmakingService
            from services.user_service import UserService
            await MatchmakingService.disconnect(virtual_id)
            await UserService.report_user(virtual_id, virtual_id, f"Auto-Mod: {text[:100]}")
        _run_async(_auto_ban())
        send_message(psid, "🚫 Auto-Moderator: Your message was blocked for violating safety guidelines.")
        _notify_user(partner_id, "❌ Chat ended. Your partner was removed by the Auto-Moderator.")
        return

    # Increment challenge counter
    async def _track_and_relay():
        from services.user_service import UserService
        await UserService.increment_challenge(virtual_id, "messages_sent")

    _run_async(_track_and_relay())

    # Relay to partner
    _notify_user(partner_id, f"💬 {text}")


def _handle_profile_setup(psid: str, virtual_id: int):
    """Start the gender-selection onboarding flow."""
    send_quick_replies(
        psid,
        "👤 Create Your Profile\n\nTo enhance your matchmaking experience, select your gender:",
        GENDER_BUTTONS
    )


def _handle_set_gender(psid: str, virtual_id: int, gender: str):
    """Save gender and complete basic profile."""
    async def _do_set_gender():
        await UserRepository.update(virtual_id, gender=gender, is_guest=0)
        send_quick_replies(
            psid,
            f"✅ Gender set to {gender.capitalize()}!\n\n"
            "Your profile has been created. You can now find partners with gender filters!",
            START_MENU_BUTTONS
        )
    _run_async(_do_set_gender())


def _notify_user(partner_virtual_id: int, text: str):
    """Route a notification to a user on their correct platform."""
    if partner_virtual_id == 1:
        return  # Echo partner — no notification needed

    if partner_virtual_id >= 10**15:
        # Messenger user
        async def _get_psid():
            u = await UserRepository.get_by_telegram_id(partner_virtual_id)
            if u:
                username = u.get("username", "")
                if username.startswith("msg_"):
                    send_message(username[4:], text)
        _run_async(_get_psid())
    else:
        # Telegram user — schedule on async event loop
        try:
            import app_state
            if app_state.bot_loop and app_state.bot_loop.is_running() and app_state.telegram_app:
                asyncio.run_coroutine_threadsafe(
                    app_state.telegram_app.send_message(chat_id=partner_virtual_id, text=text),
                    app_state.bot_loop
                )
        except Exception as e:
            logger.error(f"❌ Cross-platform Telegram notify failed for {partner_virtual_id}: {e}")


# ─────────────────────────────────────────────────────────────────────
# Webhook entry points (called by Flask routes in webhook_server.py)
# ─────────────────────────────────────────────────────────────────────

def handle_messenger_webhook_get():
    """Facebook webhook verification (GET request)."""
    # Debug: Log all incoming arguments
    args = request.args.to_dict()
    logger.info(f"🔍 Incoming Webhook Verification: {args}")

    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")
    verify_token = os.getenv("VERIFY_TOKEN", "")

    if mode == "subscribe" and token == verify_token:
        logger.info("✅ Messenger webhook verified successfully.")
        return challenge, 200
    else:
        logger.error(f"❌ Webhook verification failed. Expected: '{verify_token}', Received: '{token}'")
        return "Forbidden", 403


def handle_messenger_webhook_post():
    """Process incoming Messenger events (POST request). Always returns 200."""
    try:
        data = request.get_json(silent=True)
        if not data or data.get("object") != "page":
            return "ok", 200

        for entry in data.get("entry", []):
            for messaging in entry.get("messaging", []):
                sender_id = messaging.get("sender", {}).get("id")
                if not sender_id:
                    continue

                # Mark as seen
                mark_seen(sender_id)

                # Get/create user record
                user_data = _run_async(_get_or_create_messenger_user(sender_id))
                if not user_data:
                    logger.error(f"❌ Failed to get/create user for PSID: {sender_id}")
                    continue
                user, virtual_id = user_data

                # Check if blocked
                if user and user.get("is_blocked"):
                    send_message(sender_id, "🚫 Your account has been blocked. Contact support to appeal.")
                    continue

                if "message" in messaging:
                    message = messaging["message"]

                    if "quick_reply" in message:
                        payload = message["quick_reply"]["payload"]
                        handle_messenger_quick_reply(sender_id, virtual_id, user, payload)

                    elif "text" in message:
                        text = message["text"]
                        handle_messenger_text(sender_id, virtual_id, user, text)

                    elif "attachments" in message:
                        handle_messenger_attachment(sender_id, virtual_id, message["attachments"])

                elif "postback" in messaging:
                    payload = messaging["postback"]["payload"]
                    handle_messenger_postback(sender_id, virtual_id, user, payload)

    except Exception as e:
        logger.exception(f"❌ Error processing Messenger webhook: {e}")

    return "ok", 200  # Always return 200 to Facebook


def handle_messenger_text(psid: str, virtual_id: int, user: dict, text: str):
    """Route text messages — commands start with /, otherwise relay."""
    text_stripped = text.strip()

    # Command detection
    if text_stripped.startswith("/"):
        cmd = text_stripped.split()[0].lower()
        if cmd in ("/start", "/menu"):
            _handle_start(psid, virtual_id, user)
        elif cmd in ("/search", "/find"):
            _handle_search(psid, virtual_id, user)
        elif cmd == "/stop":
            _handle_stop(psid, virtual_id)
        elif cmd in ("/next", "/skip"):
            _handle_next(psid, virtual_id, user)
        elif cmd in ("/stats", "/me"):
            _handle_stats(psid, virtual_id)
        elif cmd == "/help":
            _handle_help(psid)
        elif cmd == "/profile":
            _handle_profile_setup(psid, virtual_id)
        elif cmd == "/report":
            _handle_report(psid, virtual_id)
        else:
            send_message(psid, f"❓ Unknown command: {cmd}\n\nType /help to see all commands.")
    else:
        # Relay to partner (or show idle message)
        _handle_relay_message(psid, virtual_id, text_stripped)


def handle_messenger_quick_reply(psid: str, virtual_id: int, user: dict, payload: str):
    """Handle quick reply button presses — mirrors Telegram callback_data."""
    if payload == "SEARCH":
        _handle_search(psid, virtual_id, user)
    elif payload == "PREF_ANY":
        _handle_search_with_pref(psid, virtual_id, user, "Any")
    elif payload == "PREF_MALE":
        _handle_search_with_pref(psid, virtual_id, user, "Male")
    elif payload == "PREF_FEMALE":
        _handle_search_with_pref(psid, virtual_id, user, "Female")
    elif payload == "CANCEL_SEARCH":
        _handle_cancel_search(psid, virtual_id)
    elif payload == "STOP":
        _handle_stop(psid, virtual_id)
    elif payload == "NEXT":
        _handle_next(psid, virtual_id, user)
    elif payload == "REPORT":
        _handle_report(psid, virtual_id)
    elif payload == "STATS":
        _handle_stats(psid, virtual_id)
    elif payload == "LEADERBOARD":
        send_quick_replies(psid, "🏆 Leaderboard coming soon! Check stats instead.", START_MENU_BUTTONS)
    elif payload == "HELP":
        _handle_help(psid)
    elif payload == "ADD_FRIEND":
        send_message(psid, "💌 Friend feature available on Telegram! Download Telegram for the full experience.")
    elif payload.startswith("SET_GENDER_"):
        gender = payload.replace("SET_GENDER_", "")
        _handle_set_gender(psid, virtual_id, gender)
    else:
        logger.warning(f"⚠️ Unhandled quick_reply payload: {payload}")
        _handle_start(psid, virtual_id, user)


def handle_messenger_postback(psid: str, virtual_id: int, user: dict, payload: str):
    """Handle postback events (persistent menu, Get Started button)."""
    logger.info(f"📨 Messenger postback from {psid}: {payload}")

    if payload == "GET_STARTED":
        send_quick_replies(
            psid,
            "👋 Welcome to Anonymous Chat Bot!\n\n"
            "Connect with random strangers anonymously.\n"
            "Your identity stays hidden until YOU choose to reveal it.\n\n"
            "Ready to find your first match?",
            START_MENU_BUTTONS
        )
    elif payload in ("CMD_START", "SEARCH"):
        _handle_search(psid, virtual_id, user)
    elif payload == "CMD_NEXT":
        _handle_next(psid, virtual_id, user)
    elif payload == "CMD_STOP":
        _handle_stop(psid, virtual_id)
    elif payload == "CMD_HELP":
        _handle_help(psid)
    elif payload == "CMD_STATS":
        _handle_stats(psid, virtual_id)
    else:
        logger.warning(f"⚠️ Unhandled postback payload: {payload}")
        _handle_start(psid, virtual_id, user)


def handle_messenger_attachment(psid: str, virtual_id: int, attachments: list):
    """Handle media attachments — relay description to partner."""
    partner_id = match_state.get_partner(virtual_id)
    for att in attachments:
        att_type = att.get("type", "file")
        url = att.get("payload", {}).get("url", "")
        description = f"📎 [Partner sent a {att_type}]"
        if partner_id:
            _notify_user(partner_id, description)
        else:
            send_message(psid, "⚠️ You are not in a chat. Find a partner first!")
            break


# ═══════════════════════════════════════════════════════════════════════
# END OF messenger_handlers.py
# ═══════════════════════════════════════════════════════════════════════
