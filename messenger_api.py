# ═══════════════════════════════════════════════════════════════════════
# FILE: messenger_api.py
# PURPOSE: Facebook Messenger Send API wrapper functions
# STATUS: NEW FILE
# DEPENDENCIES: requests, os, config.py
# ═══════════════════════════════════════════════════════════════════════

import requests
import os
import logging
from typing import Optional

logger = logging.getLogger(__name__)

GRAPH_API_VERSION = "v18.0"
GRAPH_API_URL = f"https://graph.facebook.com/{GRAPH_API_VERSION}/me/messages"


def _get_token() -> str:
    """Get the PAGE_ACCESS_TOKEN at call time (supports late-binding from env)."""
    return os.getenv("PAGE_ACCESS_TOKEN", "")


def _send_action(recipient_id: str, sender_action: str) -> Optional[dict]:
    """Internal helper to send a sender_action (typing_on, typing_off, mark_seen)."""
    token = _get_token()
    if not token:
        return None
    payload = {
        "recipient": {"id": recipient_id},
        "sender_action": sender_action
    }
    try:
        response = requests.post(
            GRAPH_API_URL,
            json=payload,
            params={"access_token": token},
            timeout=10
        )
        if response.status_code != 200:
            logger.warning(f"Messenger action '{sender_action}' failed: {response.status_code} - {response.text[:200]}")
            return {"error": response.text}
        return response.json()
    except requests.exceptions.RequestException as e:
        logger.error(f"❌ Messenger action request failed: {e}")
        return None


def send_message(recipient_id: str, text: str) -> dict:
    """Send a plain text message to a Messenger user.

    Args:
        recipient_id: The PSID (Page-Scoped ID) of the recipient.
        text: The message text (max 2000 chars for Messenger).

    Returns:
        The JSON response from the Graph API, or an error dict.
    """
    token = _get_token()
    if not token:
        logger.error("❌ PAGE_ACCESS_TOKEN not set — cannot send Messenger message.")
        return {"error": "PAGE_ACCESS_TOKEN not configured"}

    # Messenger max text length is 2000 characters
    text = text[:2000] if text else "(empty)"

    payload = {
        "recipient": {"id": recipient_id},
        "message": {"text": text}
    }
    try:
        response = requests.post(
            GRAPH_API_URL,
            json=payload,
            params={"access_token": token},
            timeout=10
        )
        if response.status_code != 200:
            logger.error(f"❌ Messenger API error: {response.status_code} - {response.text[:300]}")
            return {"error": response.text}
        logger.debug(f"✅ Messenger message sent to {recipient_id}")
        return response.json()
    except requests.exceptions.ConnectionError as e:
        logger.error(f"❌ Messenger connection error: {e}")
        return {"error": str(e)}
    except requests.exceptions.Timeout:
        logger.error(f"❌ Messenger request timed out for {recipient_id}")
        return {"error": "timeout"}
    except requests.exceptions.RequestException as e:
        logger.error(f"❌ Messenger request exception: {e}")
        return {"error": str(e)}


def send_quick_replies(recipient_id: str, text: str, quick_replies: list) -> dict:
    """Send a message with quick reply buttons (Messenger's inline keyboard equivalent).

    Args:
        recipient_id: The PSID of the recipient.
        text: The message text shown above the buttons.
        quick_replies: List of dicts: [{'title': 'Male', 'payload': 'GENDER_MALE'}, ...]

    Returns:
        The JSON response from the Graph API, or an error dict.
    """
    token = _get_token()
    if not token:
        return {"error": "PAGE_ACCESS_TOKEN not configured"}

    qr_formatted = [
        {
            "content_type": "text",
            "title": qr["title"][:20],  # Messenger max 20 chars per button
            "payload": qr["payload"]
        }
        for qr in quick_replies[:13]  # Messenger max 13 quick replies
    ]

    payload = {
        "recipient": {"id": recipient_id},
        "message": {
            "text": text[:640],  # Messenger limit for messages with quick replies
            "quick_replies": qr_formatted
        }
    }
    try:
        response = requests.post(
            GRAPH_API_URL,
            json=payload,
            params={"access_token": token},
            timeout=10
        )
        if response.status_code != 200:
            logger.error(f"❌ Messenger quick replies error: {response.status_code} - {response.text[:200]}")
            return {"error": response.text}
        return response.json()
    except requests.exceptions.RequestException as e:
        logger.error(f"❌ Messenger quick_replies request failed: {e}")
        return {"error": str(e)}


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
    """Send an image attachment to a Messenger user.

    Args:
        recipient_id: The PSID of the recipient.
        image_url: A publicly accessible URL of the image.

    Returns:
        The JSON response from the Graph API, or an error dict.
    """
    token = _get_token()
    if not token:
        return {"error": "PAGE_ACCESS_TOKEN not configured"}

    payload = {
        "recipient": {"id": recipient_id},
        "message": {
            "attachment": {
                "type": "image",
                "payload": {"url": image_url, "is_reusable": True}
            }
        }
    }
    try:
        response = requests.post(
            GRAPH_API_URL,
            json=payload,
            params={"access_token": token},
            timeout=15
        )
        if response.status_code != 200:
            logger.error(f"❌ Messenger send_image error: {response.status_code}")
            return {"error": response.text}
        return response.json()
    except requests.exceptions.RequestException as e:
        logger.error(f"❌ Messenger send_image request failed: {e}")
        return {"error": str(e)}


# ═══════════════════════════════════════════════════════════════════════
# END OF messenger_api.py
# ═══════════════════════════════════════════════════════════════════════
