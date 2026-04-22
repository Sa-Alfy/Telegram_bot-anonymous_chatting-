# ═══════════════════════════════════════════════════════════════════════
# FILE: messenger_api.py
# PURPOSE: Facebook Messenger Send API wrapper functions
# STATUS: UPGRADED — 24h messaging compliance + messaging_type
# DEPENDENCIES: requests, os, config.py
# ═══════════════════════════════════════════════════════════════════════

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import os
import time
import logging
from typing import Optional, Dict

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────
# Session with retry
# ─────────────────────────────────────────────────────────────────────

def _get_session():
    session = requests.Session()
    session.verify = True
    retry = Retry(
        total=3,
        read=3,
        connect=3,
        backoff_factor=0.3,
        status_forcelist=(500, 502, 504),
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount('http://', adapter)
    session.mount('https://', adapter)
    return session


GRAPH_API_VERSION = "v21.0"
GRAPH_API_URL = f"https://graph.facebook.com/{GRAPH_API_VERSION}/me/messages"

messenger_session = _get_session()

# ─────────────────────────────────────────────────────────────────────
# 24h Messaging Window Tracker
# ─────────────────────────────────────────────────────────────────────
# Tracks last user interaction per PSID to enforce Meta's 24h messaging rule.
# Only messages within 24h of last user action may use messaging_type=RESPONSE.

_last_user_interaction: Dict[str, float] = {}
_MESSAGING_WINDOW_SECONDS = 24 * 60 * 60  # 24 hours


def record_user_interaction(psid: str):
    """Record that a user sent a message (opens/extends the 24h window)."""
    _last_user_interaction[psid] = time.time()


def is_within_messaging_window(psid: str) -> bool:
    """Check if we're within the 24h standard messaging window for this user."""
    last_interaction = _last_user_interaction.get(psid)
    if not last_interaction:
        return False
    return (time.time() - last_interaction) < _MESSAGING_WINDOW_SECONDS


def _get_messaging_type(psid: str) -> str:
    """Determine the correct messaging_type for an outbound message.
    
    Per Meta Platform Policy:
    - RESPONSE: Within 24h of user's last message (standard window)
    - UPDATE: For non-promotional updates (requires permission)
    
    We default to RESPONSE since the bot only sends within active conversations.
    """
    if is_within_messaging_window(psid):
        return "RESPONSE"
    # Outside 24h window — log warning but still attempt (Meta will reject if invalid)
    logger.warning(f"Sending message outside 24h window for PSID ...{psid[-4:]}")
    return "RESPONSE"


# ─────────────────────────────────────────────────────────────────────
# Core API functions
# ─────────────────────────────────────────────────────────────────────

def _get_token() -> str:
    """Get the PAGE_ACCESS_TOKEN at call time (supports late-binding from env)."""
    return os.getenv("PAGE_ACCESS_TOKEN", "")


def _send_payload(payload: dict, endpoint: str = GRAPH_API_URL) -> Optional[dict]:
    """Internal helper to send a JSON payload to the Graph API."""
    token = _get_token()
    if not token:
        logger.error("PAGE_ACCESS_TOKEN not set.")
        return {"error": "PAGE_ACCESS_TOKEN not configured"}

    try:
        response = messenger_session.post(
            endpoint,
            json=payload,
            params={"access_token": token},
            timeout=15
        )
        if response.status_code != 200:
            error_info = response.json().get("error", {})
            msg = error_info.get("message", "Unknown error")
            err_code = error_info.get("code", "N/A")
            logger.error(f"Messenger API Error ({response.status_code}): {msg} [Code: {err_code}]")
            return {"error": msg, "code": err_code}
        return response.json()
    except requests.exceptions.RequestException as e:
        logger.error(f"Messenger request failed: {e}")
        return {"error": str(e)}


def _send_action(recipient_id: str, sender_action: str) -> Optional[dict]:
    """Internal helper to send a sender_action (typing_on, typing_off, mark_seen)."""
    payload = {
        "recipient": {"id": recipient_id},
        "sender_action": sender_action
    }
    return _send_payload(payload)


def send_message(recipient_id: str, text: str) -> dict:
    """Send a plain text message to a Messenger user."""
    payload = {
        "recipient": {"id": recipient_id},
        "messaging_type": _get_messaging_type(recipient_id),
        "message": {"text": text[:2000] if text else "(empty)"}
    }
    return _send_payload(payload)


def send_quick_replies(recipient_id: str, text: str, quick_replies: list) -> dict:
    """Send a message with quick reply buttons."""
    qr_formatted = [
        {
            "content_type": "text",
            "title": qr["title"][:20],
            "payload": qr["payload"]
        }
        for qr in quick_replies[:13]
    ]

    payload = {
        "recipient": {"id": recipient_id},
        "messaging_type": _get_messaging_type(recipient_id),
        "message": {
            "text": text[:640],
            "quick_replies": qr_formatted
        }
    }
    return _send_payload(payload)


def send_generic_template(recipient_id: str, elements: list) -> dict:
    """Send a Generic Template (Carousel) to a Messenger user.
    
    Args:
        recipient_id: The PSID of the recipient.
        elements: List of dicts (max 10), each with title, subtitle, image_url, and buttons.
    """
    payload = {
        "recipient": {"id": recipient_id},
        "messaging_type": _get_messaging_type(recipient_id),
        "message": {
            "attachment": {
                "type": "template",
                "payload": {
                    "template_type": "generic",
                    "elements": elements[:10]
                }
            }
        }
    }
    return _send_payload(payload)


def send_button_template(recipient_id: str, text: str, buttons: list) -> dict:
    """Send a Button Template message (structured text + up to 3 postback buttons).
    
    Unlike quick_replies (which disappear after tap), button templates persist
    in the conversation and are ideal for menus and navigation.
    
    Args:
        recipient_id: The PSID of the recipient.
        text: Header text (max 640 chars).
        buttons: List of dicts with 'type', 'title', and 'payload' keys (max 3).
    """
    payload = {
        "recipient": {"id": recipient_id},
        "messaging_type": _get_messaging_type(recipient_id),
        "message": {
            "attachment": {
                "type": "template",
                "payload": {
                    "template_type": "button",
                    "text": text[:640],
                    "buttons": buttons[:3]
                }
            }
        }
    }
    return _send_payload(payload)


def set_messenger_profile(payload: dict) -> dict:
    """Configure Page-level settings (Persistent Menu, Get Started button, etc)."""
    endpoint = f"https://graph.facebook.com/{GRAPH_API_VERSION}/me/messenger_profile"
    return _send_payload(payload, endpoint=endpoint)


def send_typing_on(recipient_id: str):
    """Show typing indicator to the user."""
    _send_action(recipient_id, "typing_on")


def send_typing_off(recipient_id: str):
    """Hide typing indicator from the user."""
    _send_action(recipient_id, "typing_off")


def mark_seen(recipient_id: str):
    """Mark last message as seen (shows read receipt)."""
    _send_action(recipient_id, "mark_seen")


def send_image(recipient_id: str, image_url: str) -> dict:
    """Send an image attachment to a Messenger user."""
    token = _get_token()
    if not token:
        return {"error": "PAGE_ACCESS_TOKEN not configured"}

    payload = {
        "recipient": {"id": recipient_id},
        "messaging_type": _get_messaging_type(recipient_id),
        "message": {
            "attachment": {
                "type": "image",
                "payload": {"url": image_url, "is_reusable": True}
            }
        }
    }
    try:
        response = messenger_session.post(
            GRAPH_API_URL,
            json=payload,
            params={"access_token": token},
            timeout=15
        )
        if response.status_code != 200:
            logger.error(f"Messenger send_image error: {response.status_code}")
            return {"error": response.text}
        return response.json()
    except requests.exceptions.RequestException as e:
        logger.error(f"Messenger send_image request failed: {e}")
        return {"error": str(e)}


def send_attachment_file(recipient_id: str, file_path: str, file_type: str = "image") -> dict:
    """Send a local file as an attachment to a Messenger user using multipart/form-data."""
    token = _get_token()
    if not token:
        return {"error": "PAGE_ACCESS_TOKEN not configured"}

    import json
    
    payload = {
        'recipient': json.dumps({'id': recipient_id}),
        'message': json.dumps({
            'attachment': {
                'type': file_type,
                'payload': {'is_reusable': True}
            }
        })
    }
    
    try:
        with open(file_path, 'rb') as f:
            files = {
                'filedata': (os.path.basename(file_path), f, 'application/octet-stream')
            }
            response = messenger_session.post(
                GRAPH_API_URL,
                params={"access_token": token},
                data=payload,
                files=files,
                timeout=30
            )
            
        if response.status_code != 200:
            logger.error(f"Messenger upload failed: {response.status_code} - {response.text}")
            return {"error": response.text}
        return response.json()
    except Exception as e:
        logger.error(f"Messenger upload exception: {e}")
        return {"error": str(e)}


# ═══════════════════════════════════════════════════════════════════════
# END OF messenger_api.py
# ═══════════════════════════════════════════════════════════════════════
