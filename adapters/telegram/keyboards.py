# adapters/telegram/keyboards.py

from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton

def get_home_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔍 Find Partner", callback_data="START_SEARCH")],
        [InlineKeyboardButton("👤 Profile", callback_data="CMD_PROFILE"), InlineKeyboardButton("📊 Stats", callback_data="STATS")]
    ])

def get_searching_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("❌ Cancel Search", callback_data="STOP_SEARCH")]
    ])

def get_chat_keyboard(match_id: str):
    """Full visibility for Telegram power users."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("⏭️ Next", callback_data=f"NEXT_MATCH:{match_id}"),
            InlineKeyboardButton("🛑 End", callback_data=f"END_CHAT:{match_id}")
        ],
        [
            InlineKeyboardButton("🧊 Icebreaker", callback_data=f"ICEBREAKER:{match_id}"),
            InlineKeyboardButton("🔓 Reveal", callback_data=f"REVEAL:{match_id}")
        ],
        [InlineKeyboardButton("🚩 Report", callback_data=f"REPORT:{match_id}")]
    ])

def get_voting_keyboard(match_id: str, step: str = "reputation"):
    if step == "reputation":
        return InlineKeyboardMarkup([
            [
                InlineKeyboardButton("👍 Good", callback_data=f"VOTE:reputation:good:{match_id}"),
                InlineKeyboardButton("👎 Bad", callback_data=f"VOTE:reputation:bad:{match_id}")
            ]
        ])
    elif step == "identity":
        return InlineKeyboardMarkup([
            [
                InlineKeyboardButton("👨 Male", callback_data=f"VOTE:identity:male:{match_id}"),
                InlineKeyboardButton("👩 Female", callback_data=f"VOTE:identity:female:{match_id}"),
                InlineKeyboardButton("❓ Unsure", callback_data=f"VOTE:identity:unsure:{match_id}")
            ]
        ])
    return None
