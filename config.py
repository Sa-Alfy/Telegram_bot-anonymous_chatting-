import os
from dotenv import load_dotenv

load_dotenv()

# ═══════════════════════════════════════════════════════
# Telegram / Pyrogram Configuration
# ═══════════════════════════════════════════════════════
API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", 0))

# ═══════════════════════════════════════════════════════
# Facebook Messenger Configuration
# ═══════════════════════════════════════════════════════
PAGE_ACCESS_TOKEN = os.getenv("PAGE_ACCESS_TOKEN", "")
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN", "")
APP_SECRET = os.getenv("APP_SECRET", "")
APP_ID = os.getenv("APP_ID", "")
FB_PAGE_ID = os.getenv("FB_PAGE_ID", "")

# ═══════════════════════════════════════════════════════
# Server / Deployment Configuration
# ═══════════════════════════════════════════════════════
PORT = int(os.getenv("PORT", 10000))
RENDER_EXTERNAL_URL = os.getenv("RENDER_EXTERNAL_URL", "")
DATABASE_URL = os.getenv("DATABASE_URL")
REDIS_URL = os.getenv("REDIS_URL")

# ═══════════════════════════════════════════════════════
# Logging
# ═══════════════════════════════════════════════════════
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

# ═══════════════════════════════════════════════════════
# Feature Flags
# ═══════════════════════════════════════════════════════
MESSENGER_ENABLED = bool(PAGE_ACCESS_TOKEN and VERIFY_TOKEN)

# ═══════════════════════════════════════════════════════
# Startup validation (non-fatal)
# ═══════════════════════════════════════════════════════
if MESSENGER_ENABLED and PAGE_ACCESS_TOKEN and not PAGE_ACCESS_TOKEN.startswith("EAA"):
    import logging
    logging.getLogger(__name__).warning(
        "PAGE_ACCESS_TOKEN does not start with 'EAA' — may be invalid or a short-lived token."
    )
