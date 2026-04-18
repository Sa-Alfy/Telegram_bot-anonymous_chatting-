# ═══════════════════════════════════════════════════════════════════════
# FILE: messenger/dispatcher.py
# PURPOSE: Messenger webhook routing and event dispatching
# ═══════════════════════════════════════════════════════════════════════

import os
import logging
import asyncio
from flask import request

from messenger_api import send_message, mark_seen, record_user_interaction
from utils.rate_limiter import rate_limiter
from state.match_state import match_state
from services.distributed_state import distributed_state

from messenger.utils import _get_or_create_messenger_user

# Imports from messenger_handlers are deferred to avoid circular dependency

logger = logging.getLogger(__name__)

def handle_messenger_webhook_get():
    """Facebook webhook verification (GET request)."""
    args = request.args.to_dict()
    logger.info(f"Incoming Webhook Verification request")

    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")
    verify_token = os.getenv("VERIFY_TOKEN", "")

    if mode == "subscribe" and token == verify_token:
        logger.info("Messenger webhook verified successfully.")
        return challenge, 200
    else:
        logger.error("Webhook verification failed — token mismatch.")
        return "Forbidden", 403


def handle_messenger_webhook_post():
    """Process incoming Messenger events (POST request). Non-blocking to prevent Meta retries."""
    import hmac as _hmac
    import hashlib as _hashlib
    import app_state
    
    _app_secret = os.getenv("APP_SECRET", "").strip()
    if _app_secret:
        _sig = request.headers.get("X-Hub-Signature-256", "")
        _body = request.get_data()
        _expected = "sha256=" + _hmac.new(
            _app_secret.encode('utf-8'), _body, _hashlib.sha256
        ).hexdigest()
        
        if not _hmac.compare_digest(_sig, _expected):
            logger.warning(f"Messenger Webhook Signature MISMATCH.")
            if os.getenv("FLASK_ENV") == "development":
                logger.warning("Bypassing signature block to allow development testing.")
            else:
                return "Forbidden", 403
        else:
            logger.debug("Webhook signature verified.")

    try:
        data = request.get_json(silent=True)
        if not data or data.get("object") != "page":
            return "ok", 200

        if not app_state.bot_loop or not app_state.bot_loop.is_running():
            logger.error("Cannot process Messenger webhook: bot_loop not running")
            return "ok", 200

        # Offload event processing to the async event loop to free the Flask thread immediately
        for entry in data.get("entry", []):
            for messaging in entry.get("messaging", []):
                asyncio.run_coroutine_threadsafe(_process_messaging_event(messaging), app_state.bot_loop)

    except Exception as e:
        logger.error(f"Error scheduling Messenger event: {e}")

    return "ok", 200


async def _process_messaging_event(messaging: dict):
    """Async internal handler for a single messaging event."""
    try:
        from messenger_handlers import (
            handle_messenger_quick_reply, handle_messenger_text, 
            handle_messenger_attachment, handle_messenger_postback, handle_messenger_call
        )
        from messenger.handlers.profile import (
            show_consent_screen, handle_consent_accept, handle_consent_decline
        )
        sender_id = messaging.get("sender", {}).get("id")
        if not sender_id:
            logger.warning("TRACE: No sender_id in messaging event")
            return

        # Determine event type for logging
        _event_type = "unknown"
        _event_payload = ""
        if "postback" in messaging:
            _event_type = "postback"
            _event_payload = messaging["postback"].get("payload", "")
        elif "message" in messaging:
            msg = messaging["message"]
            if "quick_reply" in msg:
                _event_type = "quick_reply"
                _event_payload = msg["quick_reply"].get("payload", "")
            elif "text" in msg:
                _event_type = "text"
                _event_payload = msg["text"][:50]
            elif "attachments" in msg:
                _event_type = "attachment"
        logger.info(f"TRACE: Processing {_event_type} from PSID ...{sender_id[-4:]}: {_event_payload}")

        # Record interaction for 24h window (H2: run in executor to avoid blocking the event loop)
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, record_user_interaction, sender_id)
        await loop.run_in_executor(None, mark_seen, sender_id)

        # Get/create user record (async)
        user_data = await _get_or_create_messenger_user(sender_id)
        if not user_data:
            logger.warning(f"TRACE: _get_or_create_messenger_user returned None for PSID ...{sender_id[-4:]}")
            return
        user, virtual_id = user_data
        logger.info(f"TRACE: VirtualID=...{str(virtual_id)[-4:]} for PSID ...{sender_id[-4:]}")

        # Block Check
        if user and user.get("is_blocked"):
            logger.info(f"TRACE: User ...{str(virtual_id)[-4:]} is BLOCKED, rejecting")
            send_message(sender_id, "\U0001f6ab Your account has been blocked.")
            return

        # ── Consent Gate ──────────────────────────────────────────────
        has_consent = user and user.get("consent_given_at")
        if not has_consent:
            logger.info(f"TRACE: User ...{str(virtual_id)[-4:]} has NO CONSENT, showing consent screen")
            payload = None
            text_cmd = ""
            
            if "postback" in messaging:
                payload = messaging["postback"]["payload"]
            elif "message" in messaging:
                if "quick_reply" in messaging["message"]:
                    payload = messaging["message"]["quick_reply"]["payload"]
                elif "text" in messaging["message"]:
                    text_cmd = messaging["message"]["text"].strip().lower()

            # White-listed payloads/commands for unconsented users
            if payload in ("CONSENT_ACCEPT", "CONSENT_DECLINE", "TERMS", "PRIVACY") or text_cmd in ("/terms", "/privacy"):
                if payload == "CONSENT_ACCEPT":
                    await handle_consent_accept(sender_id, virtual_id, user)
                elif payload == "CONSENT_DECLINE":
                    handle_consent_decline(sender_id)
                elif payload == "TERMS" or text_cmd == "/terms":
                    from messenger.handlers.profile import handle_terms
                    handle_terms(sender_id)
                elif payload == "PRIVACY" or text_cmd == "/privacy":
                    from messenger.handlers.profile import handle_privacy
                    handle_privacy(sender_id)
                return
            
            await show_consent_screen(sender_id)
            return

        from messenger_handlers import (
            handle_messenger_text, handle_messenger_quick_reply,
            handle_messenger_postback, handle_messenger_attachment,
            handle_messenger_call
        )

        # ── Event Dispatching ────────────────────────────────────────
        if "message" in messaging:
            message = messaging["message"]
            mid = message.get("mid")
            
            # Deduplicate Messages (using built-in mid)
            if mid and await distributed_state.is_duplicate_message(mid):
                logger.info(f"TRACE: DROPPED duplicate message mid={mid[:20]}...")
                return

            if "quick_reply" in message:
                payload = message["quick_reply"]["payload"]
                # Deduplicate quick-reply clicks (prevent double-tap)
                is_dup = await distributed_state.is_duplicate_interaction(virtual_id, f"qr:{payload}")
                if is_dup:
                    logger.info(f"TRACE: DROPPED duplicate quick_reply: {payload}")
                    return
                logger.info(f"TRACE: Dispatching quick_reply: {payload} for VID ...{str(virtual_id)[-4:]}")
                await handle_messenger_quick_reply(sender_id, virtual_id, user, payload)
                logger.info(f"TRACE: quick_reply handler COMPLETED for {payload}")

            elif "text" in message:
                logger.info(f"TRACE: Dispatching text message for VID ...{str(virtual_id)[-4:]}")
                await handle_messenger_text(sender_id, virtual_id, user, message["text"])

            elif "attachments" in message:
                await handle_messenger_attachment(sender_id, virtual_id, message["attachments"])

        elif "postback" in messaging:
            payload = messaging["postback"]["payload"]
            # Deduplicate postback clicks (prevent double-tap)
            is_dup = await distributed_state.is_duplicate_interaction(virtual_id, f"pb:{payload}")
            if is_dup:
                logger.info(f"TRACE: DROPPED duplicate postback: {payload}")
                return
            logger.info(f"TRACE: Dispatching postback: {payload} for VID ...{str(virtual_id)[-4:]}")
            await handle_messenger_postback(sender_id, virtual_id, user, payload)
            logger.info(f"TRACE: postback handler COMPLETED for {payload}")

        elif "call" in messaging:
            await handle_messenger_call(sender_id, virtual_id, user, messaging["call"])

    except Exception as e:
        logger.exception(f"TRACE-ERROR in _process_messaging_event: {e}")

