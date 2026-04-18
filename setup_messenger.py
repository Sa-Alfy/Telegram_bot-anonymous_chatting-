# =========================================================================
# FILE: setup_messenger.py
# PURPOSE: One-time Messenger profile configuration (Get Started, Menu, etc.)
# STATUS: UPGRADED — Meta App Review ready with whitelisted_domains + ice_breakers
# DEPENDENCIES: messenger_api.py, python-dotenv
# =========================================================================

import os
import sys
import logging
from dotenv import load_dotenv
from config import USE_NGROK
from utils.ngrok_utils import start_ngrok_tunnel

# Set up logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# Add current directory to path so we can import messenger_api
sys.path.append(os.getcwd())

try:
    from messenger_api import set_messenger_profile
except ImportError:
    logger.error("Could not import messenger_api. Ensure it's in the same directory.")
    sys.exit(1)

def run_setup():
    """Configure Page-level settings (Persistent Menu, Get Started button, etc)."""
    load_dotenv()
    
    token = os.getenv("PAGE_ACCESS_TOKEN")
    if not token or len(token) < 20:
        logger.error("PAGE_ACCESS_TOKEN is missing or too short. Check your .env file.")
        return

    # Start ngrok if requested for standalone setup
    if USE_NGROK:
        start_ngrok_tunnel()

    render_url = os.getenv("RENDER_EXTERNAL_URL", "").rstrip("/")

    logger.info("Messenger Profile Setup starting...")

    # 1. Setting the 'Get Started' button
    logger.info("🔘 Setting 'Get Started' button...")
    gs_payload = {
        "get_started": {"payload": "GET_STARTED"}
    }
    res = set_messenger_profile(gs_payload)
    if res and "error" in res:
        logger.error(f"Failed to set 'Get Started' button: {res['error']}")
    else:
        logger.info("'Get Started' button activated.")

    # 2. Setting Greeting Text
    logger.info("👋 Setting Welcome Greeting...")
    greeting_payload = {
        "greeting": [
            {
                "locale": "default",
                "text": "Welcome to Neonymo! 🎭 Meet new people anonymously. Click 'Get Started' to begin."
            }
        ]
    }
    res = set_messenger_profile(greeting_payload)
    if res and "error" in res:
        logger.error(f"Failed to set Greeting text: {res['error']}")
    else:
        logger.info("Welcome Greeting configured.")

    # 3. Setting Persistent Menu
    logger.info("📋 Setting Persistent Menu...")
    menu_payload = {
        "persistent_menu": [
            {
                "locale": "default",
                "composer_input_disabled": False,
                "call_to_actions": [
                    {
                        "type": "postback",
                        "title": "🔍 Find Partner",
                        "payload": "SEARCH"
                    },
                    {
                        "type": "postback",
                        "title": "🛑 End Chat",
                        "payload": "CMD_STOP"
                    },
                    {
                        "type": "postback",
                        "title": "👤 My Profile",
                        "payload": "CMD_PROFILE"
                    },
                    {
                        "type": "postback",
                        "title": "📊 Stats",
                        "payload": "CMD_STATS"
                    },
                    {
                        "type": "postback",
                        "title": "⚙️ Settings",
                        "payload": "SETTINGS_MENU"
                    }
                ]
            }
        ]
    }
    res = set_messenger_profile(menu_payload)
    if res and "error" in res:
        logger.error(f"Failed to set Persistent Menu: {res['error']}")
    else:
        logger.info("Persistent Menu configured.")

    # 4. Whitelisted Domains (required for URL buttons and webviews)
    if render_url:
        logger.info("🌐 Setting Whitelisted Domains...")
        domain_payload = {
            "whitelisted_domains": [
                render_url,
                "https://meet.jit.si"  # For video call links
            ]
        }
        res = set_messenger_profile(domain_payload)
        if res and "error" in res:
            logger.error(f"Failed to set Whitelisted Domains: {res['error']}")
        else:
            logger.info("Whitelisted Domains configured.")
    else:
        logger.warning("⚠️ RENDER_EXTERNAL_URL not set — skipping whitelisted_domains.")

    # 5. Ice Breakers (conversation starters for new users)
    logger.info("🧊 Setting Ice Breakers...")
    ice_payload = {
        "ice_breakers": [
            {
                "question": "🔍 How do I find a chat partner?",
                "payload": "SEARCH"
            },
            {
                "question": "👤 How do I set up my profile?",
                "payload": "CMD_PROFILE"
            },
            {
                "question": "🛡 Is this safe and anonymous?",
                "payload": "HELP"
            }
        ]
    }
    res = set_messenger_profile(ice_payload)
    if res and "error" in res:
        logger.error(f"Failed to set Ice Breakers: {res['error']}")
    else:
        logger.info("Ice Breakers configured.")

    logger.info("=" * 60)
    logger.info("✨ Messenger profile setup complete!")
    logger.info("Go to your Facebook Page and send a message to test.")
    if render_url:
        logger.info(f"Privacy Policy: {render_url}/privacy")
        logger.info(f"Terms of Service: {render_url}/terms")
        logger.info(f"Data Deletion: {render_url}/delete-data")
    logger.info("=" * 60)

if __name__ == "__main__":
    run_setup()
