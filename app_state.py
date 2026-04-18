# ═══════════════════════════════════════════════════════════════════════
# FILE: app_state.py
# PURPOSE: Holds shared mutable references across modules (Pyrogram client, etc.)
# STATUS: NEW FILE
# DEPENDENCIES: None (imported by main.py then written to before use)
# ═══════════════════════════════════════════════════════════════════════

# This module prevents circular imports by acting as a neutral container.
# main.py assigns `telegram_app` after bot initialisation.
# messenger_handlers.py reads it to send cross-platform Telegram messages.

telegram_app = None  # Pyrogram Client instance — set in main.py
bot_loop = None      # Main asyncio Event Loop — set in main.py

# ═══════════════════════════════════════════════════════════════════════
# END OF app_state.py
# ═══════════════════════════════════════════════════════════════════════
