# ═══════════════════════════════════════════════════════════════════════
# FILE: setup_messenger.py
# PURPOSE: One-time Messenger profile configuration (run after deployment)
# STATUS: NEW FILE
# DEPENDENCIES: requests, python-dotenv
# ═══════════════════════════════════════════════════════════════════════

import requests
import os
import sys
import json
from dotenv import load_dotenv

GRAPH_API_VERSION = "v18.0"
PROFILE_URL = f"https://graph.facebook.com/{GRAPH_API_VERSION}/me/messenger_profile"


def _post(payload: dict, token: str) -> dict:
    """POST to the Messenger Profile API."""
    response = requests.post(
        PROFILE_URL,
        json=payload,
        params={"access_token": token},
        timeout=15
    )
    return {"status": response.status_code, "body": response.json()}


def _delete(fields: list, token: str) -> dict:
    """DELETE fields from the Messenger Profile."""
    response = requests.delete(
        PROFILE_URL,
        json={"fields": fields},
        params={"access_token": token},
        timeout=15
    )
    return {"status": response.status_code, "body": response.json()}


def setup_get_started(token: str) -> dict:
    """Add the 'Get Started' button shown to new users before they message the page."""
    payload = {"get_started": {"payload": "GET_STARTED"}}
    result = _post(payload, token)
    if result["status"] == 200:
        print("  ✅ Get Started button configured.")
    else:
        print(f"  ❌ Get Started failed: {result['body']}")
    return result


def setup_persistent_menu(token: str) -> dict:
    """Add a hamburger menu with bot commands — visible to all Messenger users."""
    payload = {
        "persistent_menu": [
            {
                "locale": "default",
                "composer_input_disabled": False,
                "call_to_actions": [
                    {
                        "type": "postback",
                        "title": "▶️ Find Partner",
                        "payload": "CMD_START"
                    },
                    {
                        "type": "postback",
                        "title": "⏭️ Next Person",
                        "payload": "CMD_NEXT"
                    },
                    {
                        "type": "postback",
                        "title": "⏹️ Stop Chat",
                        "payload": "CMD_STOP"
                    },
                    {
                        "type": "postback",
                        "title": "📊 My Stats",
                        "payload": "CMD_STATS"
                    },
                    {
                        "type": "postback",
                        "title": "ℹ️ Help",
                        "payload": "CMD_HELP"
                    }
                ]
            }
        ]
    }
    result = _post(payload, token)
    if result["status"] == 200:
        print("  ✅ Persistent menu configured.")
    else:
        print(f"  ❌ Persistent menu failed: {result['body']}")
    return result


def setup_greeting_text(token: str) -> dict:
    """Set the greeting shown before a user clicks 'Get Started'."""
    payload = {
        "greeting": [
            {
                "locale": "default",
                "text": (
                    "👋 Welcome to Anonymous Chat Bot!\n\n"
                    "Connect with random strangers anonymously. "
                    "Your identity stays hidden until YOU choose to reveal it.\n\n"
                    "Press 'Get Started' to find your first match! 🔍"
                )
            }
        ]
    }
    result = _post(payload, token)
    if result["status"] == 200:
        print("  ✅ Greeting text configured.")
    else:
        print(f"  ❌ Greeting text failed: {result['body']}")
    return result


def remove_persistent_menu(token: str) -> dict:
    """Remove the persistent menu (useful for debugging or resetting)."""
    result = _delete(["persistent_menu"], token)
    if result["status"] == 200:
        print("  ✅ Persistent menu removed.")
    else:
        print(f"  ❌ Remove menu failed: {result['body']}")
    return result


def verify_webhook_subscription(token: str, app_url: str) -> None:
    """Print instructions for subscribing the webhook on Facebook."""
    print("\n📋 Manual Step Required — Webhook Subscription:")
    print("  Go to: https://developers.facebook.com/apps/")
    print("  → Your App → Messenger → Settings → Webhooks")
    print(f"  → Callback URL: {app_url}/messenger-webhook")
    print("  → Verify Token: (your VERIFY_TOKEN from .env)")
    print("  → Subscribe to: messages, messaging_postbacks, messaging_referrals")


if __name__ == "__main__":
    print("=" * 60)
    print("  Messenger Profile Setup Script")
    print("=" * 60)

    load_dotenv()
    PAGE_ACCESS_TOKEN = os.getenv("PAGE_ACCESS_TOKEN", "")
    RENDER_URL = os.getenv("RENDER_EXTERNAL_URL", "")

    if not PAGE_ACCESS_TOKEN:
        print("\n[!] PAGE_ACCESS_TOKEN not found in .env")
        print("   Add it to your .env file and try again.")
        sys.exit(1)

    print(f"\n[*] Using token: {PAGE_ACCESS_TOKEN[:20]}...")
    print()

    print("1. Setting up Get Started button...")
    setup_get_started(PAGE_ACCESS_TOKEN)

    print("\n2. Setting up Persistent Menu...")
    setup_persistent_menu(PAGE_ACCESS_TOKEN)

    print("\n3. Setting up Greeting Text...")
    setup_greeting_text(PAGE_ACCESS_TOKEN)

    if RENDER_URL:
        verify_webhook_subscription(PAGE_ACCESS_TOKEN, RENDER_URL)
    else:
        verify_webhook_subscription(PAGE_ACCESS_TOKEN, "https://your-app.onrender.com")

    print("\n" + "=" * 60)
    print("  [OK] Messenger profile setup complete!")
    print("  Go to your Facebook Page -> Send Message to test.")
    print("=" * 60)

# =========================================================================
# END OF setup_messenger.py
# =========================================================================
