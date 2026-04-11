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
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN", "my_default_verify_token")

# ═══════════════════════════════════════════════════════
# Server / Deployment Configuration
# ═══════════════════════════════════════════════════════
PORT = int(os.getenv("PORT", 10000))
RENDER_EXTERNAL_URL = os.getenv("RENDER_EXTERNAL_URL", "")

# ═══════════════════════════════════════════════════════
# Feature Flags
# ═══════════════════════════════════════════════════════
MESSENGER_ENABLED = bool(PAGE_ACCESS_TOKEN and VERIFY_TOKEN)
