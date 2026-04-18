# ═══════════════════════════════════════════════════════════════════════
# FILE: keep_alive.py
# PURPOSE: Prevent Render.com free tier from sleeping (pings /health every 10 min)
# STATUS: NEW FILE
# DEPENDENCIES: threading, requests, os
# ═══════════════════════════════════════════════════════════════════════

import threading
import time
import requests
import os
import logging

logger = logging.getLogger(__name__)


def keep_alive():
    """Infinite loop that pings the bot's own /health endpoint every 10 minutes.

    Only runs when RENDER_EXTERNAL_URL is set (i.e., deployed on Render).
    Safe to call from a daemon thread — exits automatically when the process ends.
    """
    app_url = os.getenv("RENDER_EXTERNAL_URL", "").rstrip("/")
    if not app_url:
        logger.info("⚠️ RENDER_EXTERNAL_URL not set — skipping keep-alive (local/non-Render env).")
        return

    logger.info(f"✅ Keep-alive started. Pinging {app_url}/health every 10 minutes.")

    while True:
        try:
            time.sleep(600)  # Wait 10 minutes before first ping
            response = requests.get(f"{app_url}/health", timeout=15)
            if response.status_code == 200:
                logger.info("✅ Keep-alive ping successful.")
            else:
                logger.warning(f"⚠️ Keep-alive ping returned status {response.status_code}.")
        except requests.exceptions.ConnectionError:
            logger.error("❌ Keep-alive ping failed: connection error (server may be starting).")
        except requests.exceptions.Timeout:
            logger.error("❌ Keep-alive ping timed out.")
        except requests.exceptions.RequestException as e:
            logger.error(f"❌ Keep-alive request error: {e}")
        except Exception as e:
            logger.error(f"❌ Keep-alive unexpected error: {e}")


def start_keep_alive():
    """Launch keep_alive() in a background daemon thread.

    The daemon flag ensures the thread is killed automatically when the
    main process exits — no cleanup needed.
    """
    thread = threading.Thread(target=keep_alive, daemon=True, name="KeepAlive")
    thread.start()
    logger.info("🔄 Keep-alive thread launched.")


# ═══════════════════════════════════════════════════════════════════════
# END OF keep_alive.py
# ═══════════════════════════════════════════════════════════════════════
