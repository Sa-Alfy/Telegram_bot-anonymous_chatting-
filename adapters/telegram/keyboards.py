from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from utils.renderer import StateBoundPayload
from core.engine.state_machine import UnifiedState

def get_home_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔍 Find Partner", callback_data=StateBoundPayload.encode("START_SEARCH", "0", UnifiedState.HOME))],
        [InlineKeyboardButton("👤 Profile", callback_data="CMD_PROFILE"), InlineKeyboardButton("📊 Stats", callback_data="STATS")]
    ])

def get_searching_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("❌ Cancel Search", callback_data=StateBoundPayload.encode("STOP_SEARCH", "0", UnifiedState.SEARCHING))]
    ])

def get_chat_keyboard(match_id: str):
    """Full visibility for Telegram power users."""
    state = UnifiedState.CHAT_ACTIVE
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("⏭️ Next", callback_data=StateBoundPayload.encode("NEXT_MATCH", match_id, state)),
            InlineKeyboardButton("🛑 End", callback_data=StateBoundPayload.encode("END_CHAT", match_id, state))
        ],
        [
            InlineKeyboardButton("🧊 Icebreaker", callback_data=StateBoundPayload.encode("ICEBREAKER", match_id, state)),
            InlineKeyboardButton("🔓 Reveal", callback_data=StateBoundPayload.encode("REVEAL", match_id, state))
        ],
        [InlineKeyboardButton("🚩 Report", callback_data=StateBoundPayload.encode("REPORT", match_id, state))]
    ])

def get_voting_keyboard(match_id: str, step: str = "reputation"):
    state = UnifiedState.VOTING
    if step == "reputation":
        return InlineKeyboardMarkup([
            [
                InlineKeyboardButton("👍 Good", callback_data=StateBoundPayload.encode("VOTE", f"reputation:good", match_id)),
                InlineKeyboardButton("👎 Bad", callback_data=StateBoundPayload.encode("VOTE", f"reputation:bad", match_id))
            ],
            [InlineKeyboardButton("⏩ Skip Feedback", callback_data=StateBoundPayload.encode("SKIP_VOTE", match_id, state))]
        ])
    elif step == "identity":
        return InlineKeyboardMarkup([
            [
                InlineKeyboardButton("👨 Male", callback_data=StateBoundPayload.encode("VOTE", f"identity:male", match_id)),
                InlineKeyboardButton("👩 Female", callback_data=StateBoundPayload.encode("VOTE", f"identity:female", match_id)),
                InlineKeyboardButton("❓ Unsure", callback_data=StateBoundPayload.encode("VOTE", f"identity:unsure", match_id))
            ],
            [InlineKeyboardButton("⏩ Skip Feedback", callback_data=StateBoundPayload.encode("SKIP_VOTE", match_id, state))]
        ])

def get_preferences_keyboard():
    state = UnifiedState.PREFERENCES
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("👫 Anyone", callback_data=StateBoundPayload.encode("SEARCH_PREF", "Any", state))],
        [
            InlineKeyboardButton("👨 Male (15 coins)", callback_data=StateBoundPayload.encode("SEARCH_PREF", "Male", state)),
            InlineKeyboardButton("👩 Female (15 coins)", callback_data=StateBoundPayload.encode("SEARCH_PREF", "Female", state))
        ],
        [InlineKeyboardButton("🔙 Back", callback_data=StateBoundPayload.encode("STOP_SEARCH", "0", state))]
    ])
