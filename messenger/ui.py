# ═══════════════════════════════════════════════════════════════════════
# FILE: messenger/ui.py
# PURPOSE: Messenger UI Constants, Cards & Quick Reply Menus
# ═══════════════════════════════════════════════════════════════════════

# ─────────────────────────────────────────────────────────────────────
# UI Constants & Assets
# ─────────────────────────────────────────────────────────────────────
LOGO_URL = "https://raw.githubusercontent.com/Sa-Alfy/Telegram_bot-anonymous_chatting-/main/assets/logo.png"
# Missing assets fallback to LOGO_URL to avoid broken images
SHOP_BANNER_URL = LOGO_URL 
VIP_IMAGE_URL = LOGO_URL
LEADERBOARD_IMAGE_URL = LOGO_URL

from state.match_state import UserState
from utils.renderer import StateBoundPayload

# ─────────────────────────────────────────────────────────────────────
# Structured Templates (Messenger Cards & Carousels)
# ─────────────────────────────────────────────────────────────────────

def get_welcome_card(state: str = UserState.HOME):
    """Returns a high-end Welcome Card for Messenger."""
    return [{
        "title": "Neonymo Anonymous Chat",
        "subtitle": "Connect with strangers. Earn coins. Stay anonymous.",
        "image_url": LOGO_URL,
        "buttons": [
            {"type": "postback", "title": "🔍 Find Partner", "payload": StateBoundPayload.encode("SEARCH", "0", state)},
            {"type": "postback", "title": "👤 My Profile",   "payload": StateBoundPayload.encode("CMD_PROFILE", "0", state)},
            {"type": "postback", "title": "ℹ️ Help & Info",  "payload": StateBoundPayload.encode("HELP", "0", state)}
        ]
    }]

def get_stats_card(user_data: dict, state: str = UserState.HOME):
    """Returns a visual Stats Card — shows user's profile photo if available."""
    coins = user_data.get("coins", 0)
    level = user_data.get("level", 1)
    xp = user_data.get("xp", 0)
    matches = user_data.get("total_matches", 0)
    photo = user_data.get("profile_photo") or LEADERBOARD_IMAGE_URL
    
    return [{
        "title": f"Profile: {user_data.get('first_name', 'User')}",
        "subtitle": f"🌟 Level {level} | 💰 {coins} Coins | 🤝 {matches} Matches\nXP: {xp}",
        "image_url": photo,
        "buttons": [
            {"type": "postback", "title": "🔍 Find Partner", "payload": StateBoundPayload.encode("SEARCH", "0", state)},
            {"type": "postback", "title": "✏️ Edit Profile", "payload": StateBoundPayload.encode("CMD_PROFILE", "0", state)}
        ]
    }]

def get_profile_dashboard_card(user_data: dict, state: str = UserState.HOME):
    """Returns a rich Profile Dashboard card — shows user's profile photo if available."""
    gender = user_data.get("gender", "Not set")
    age = user_data.get("age", "Not set")
    bio = user_data.get("bio", "No bio yet")
    location = user_data.get("location", "Not set")
    photo = user_data.get("profile_photo") or LOGO_URL
    has_photo = bool(user_data.get("profile_photo"))
    photo_status = "📸 Photo set" if has_photo else "📷 No photo"
    
    subtitle = (
        f"Gender: {gender} | Age: {age}\n"
        f"📍 {location} | {photo_status}\n"
        f"📝 {bio[:60]}{'...' if len(bio) > 60 else ''}"
    )
    
    return [{
        "title": f"👤 {user_data.get('first_name', 'Your Profile')}",
        "subtitle": subtitle,
        "image_url": photo,
        "buttons": [
            {"type": "postback", "title": "✏️ Edit Profile", "payload": StateBoundPayload.encode("EDIT_PROFILE", "0", state)},
            {"type": "postback", "title": "📷 Set Photo",    "payload": StateBoundPayload.encode("SET_PHOTO", "0", state)},
            {"type": "postback", "title": "🏠 Main Menu",    "payload": StateBoundPayload.encode("CMD_START", "0", state)}
        ]
    }]

def get_shop_carousel(state: str = UserState.HOME):
    """Returns a Carousel of shop items with state-bound payloads."""
    return [
        {
            "title": "👑 30-Day VIP",
            "subtitle": "Double coins, gender filters, and exclusive badge.",
            "image_url": VIP_IMAGE_URL,
            "buttons": [{"type": "postback", "title": "Buy (500 coins)", "payload": StateBoundPayload.encode("BUY_VIP", "0", state)}]
        },
        {
            "title": "🔥 'OG User' Badge",
            "subtitle": "Show everyone you were here from the start.",
            "image_url": SHOP_BANNER_URL,
            "buttons": [{"type": "postback", "title": "Buy (300 coins)", "payload": StateBoundPayload.encode("BUY_OG", "0", state)}]
        },
        {
            "title": "🐋 'Whale' Badge",
            "subtitle": "The ultimate status symbol for high earners.",
            "image_url": SHOP_BANNER_URL,
            "buttons": [{"type": "postback", "title": "Buy (1000 coins)", "payload": StateBoundPayload.encode("BUY_WHALE", "0", state)}]
        }
    ]

# ... [rest of the file remains same, I will use replace_file_content for precision if possible, but write_to_file is safer for whole sections] ...
# [I'll just provide the full file to ensure alignment]
def get_start_menu_buttons(state: str = UserState.HOME):
    return [
        {"title": "🔍 Find Partner", "payload": StateBoundPayload.encode("SEARCH", "0", state)},
        {"title": "👤 My Profile",   "payload": StateBoundPayload.encode("CMD_PROFILE", "0", state)},
        {"title": "📊 My Stats",     "payload": StateBoundPayload.encode("STATS", "0", state)},
        {"title": "⚙️ Settings",    "payload": StateBoundPayload.encode("SETTINGS_MENU", "0", state)},
    ]

def get_search_pref_buttons(state: str = UserState.HOME):
    return [
        {"title": "👫 Anyone",  "payload": StateBoundPayload.encode("search_pref_any", "0", state)},
        {"title": "👩 Female",  "payload": StateBoundPayload.encode("search_pref_female", "0", state)},
        {"title": "👨 Male",    "payload": StateBoundPayload.encode("search_pref_male", "0", state)},
        {"title": "❌ Cancel",  "payload": StateBoundPayload.encode("cancel_search", "0", state)},
    ]

def get_chat_menu_buttons(state: str = UserState.HOME):
    return [
        {"title": "⏭ Next",        "payload": StateBoundPayload.encode("NEXT", "0", state)},
        {"title": "🛑 Stop",        "payload": StateBoundPayload.encode("STOP", "0", state)},
        {"title": "👁 Reveal",      "payload": StateBoundPayload.encode("REVEAL", "0", state)},
        {"title": "⚠️ Report",      "payload": StateBoundPayload.encode("REPORT", "0", state)},
        {"title": "🚫 Block",       "payload": StateBoundPayload.encode("BLOCK_PARTNER", "0", state)},
        {"title": "💌 Add Friend",  "payload": StateBoundPayload.encode("ADD_FRIEND", "0", state)},
        {"title": "🎲 Icebreaker",  "payload": StateBoundPayload.encode("ICEBREAKER", "0", state)},
    ]

def get_end_menu_buttons(state: str = UserState.HOME, partner_id: int = None):
    buttons = [
        {"title": "🔍 Find New",    "payload": StateBoundPayload.encode("SEARCH", "0", state)},
    ]
    
    if partner_id:
        buttons.extend([
            {"title": "👍 Like", "payload": StateBoundPayload.encode("vote_like", str(partner_id), state)},
            {"title": "👎 Dislike", "payload": StateBoundPayload.encode("vote_dislike", str(partner_id), state)},
            {"title": "👨 Boy", "payload": StateBoundPayload.encode("vote_gender_male", str(partner_id), state)},
            {"title": "👩 Girl", "payload": StateBoundPayload.encode("vote_gender_female", str(partner_id), state)}
        ])
        
    buttons.extend([
        {"title": "📊 My Stats",    "payload": StateBoundPayload.encode("STATS", "0", state)},
        {"title": "🏠 Main Menu",   "payload": StateBoundPayload.encode("CMD_START", "0", state)},
    ])
    return buttons

def get_gender_buttons(state: str = UserState.HOME):
    return [
        {"title": "👨 Male",   "payload": StateBoundPayload.encode("SET_GENDER_male", "0", state)},
        {"title": "👩 Female", "payload": StateBoundPayload.encode("SET_GENDER_female", "0", state)},
        {"title": "🌈 Other",  "payload": StateBoundPayload.encode("SET_GENDER_other", "0", state)},
        {"title": "🔙 Back",  "payload": StateBoundPayload.encode("BACK_HOME", "0", state)},
    ]

def get_age_buttons(state: str = UserState.HOME):
    return [
        {"title": "🎓 18-21", "payload": StateBoundPayload.encode("SET_AGE_18-21", "0", state)},
        {"title": "💼 22-25", "payload": StateBoundPayload.encode("SET_AGE_22-25", "0", state)},
        {"title": "📈 26-29", "payload": StateBoundPayload.encode("SET_AGE_26-29", "0", state)},
        {"title": "🍷 30+", "payload": StateBoundPayload.encode("SET_AGE_30+", "0", state)},
        {"title": "🔙 Back",  "payload": StateBoundPayload.encode("BACK_HOME", "0", state)},
    ]

def get_goal_buttons(state: str = UserState.HOME):
    return [
        {"title": "💬 Casual Chatting", "payload": StateBoundPayload.encode("SET_GOAL_chat", "0", state)},
        {"title": "❤️ Dating / Romance", "payload": StateBoundPayload.encode("SET_GOAL_dating", "0", state)},
        {"title": "🤝 Making Friends", "payload": StateBoundPayload.encode("SET_GOAL_friends", "0", state)},
        {"title": "🔙 Back",  "payload": StateBoundPayload.encode("BACK_HOME", "0", state)},
    ]

def get_interests_skip_buttons(state: str = UserState.HOME):
    return [
        {"title": "⏩ Skip Interests", "payload": StateBoundPayload.encode("SET_INTERESTS_SKIP", "0", state)},
        {"title": "🔙 Back To Profile",  "payload": StateBoundPayload.encode("BACK_HOME", "0", state)},
    ]

CONSENT_BUTTONS = [
    {"title": "✅ I Accept", "payload": StateBoundPayload.encode("CONSENT_ACCEPT", "0", UserState.HOME)},
    {"title": "❌ Decline",  "payload": StateBoundPayload.encode("CONSENT_DECLINE", "0", UserState.HOME)},
]

SETTINGS_MENU_BUTTONS = [
    {"type": "postback", "title": "👤 Edit Profile", "payload": StateBoundPayload.encode("CMD_PROFILE", "0", UserState.HOME)},
    {"type": "postback", "title": "🗑 Delete My Data", "payload": StateBoundPayload.encode("DELETE_DATA", "0", UserState.HOME)},
    {"type": "postback", "title": "ℹ️ How It Works", "payload": StateBoundPayload.encode("HELP", "0", UserState.HOME)},
]

IDLE_MENU_BUTTONS = [
    {"title": "🔍 Find Partner", "payload": StateBoundPayload.encode("SEARCH", "0", UserState.HOME)},
    {"title": "👤 My Profile",   "payload": StateBoundPayload.encode("CMD_PROFILE", "0", UserState.HOME)},
    {"title": "📊 My Stats",     "payload": StateBoundPayload.encode("STATS", "0", UserState.HOME)},
]

FRIEND_CONFIRM_BUTTONS = [
    {"title": "💌 Yes, Add",  "payload": StateBoundPayload.encode("CONFIRM_FRIEND", "0", UserState.HOME)},
    {"title": "❌ No Thanks", "payload": StateBoundPayload.encode("CANCEL_FRIEND", "0", UserState.HOME)},
]

def get_retry_search_buttons(state: str = UserState.HOME):
    return [
        {"title": "🔄 Try Again", "payload": StateBoundPayload.encode("SEARCH", "0", state)},
        {"title": "🏠 Main Menu", "payload": StateBoundPayload.encode("CMD_START", "0", state)},
    ]

START_MENU_BUTTONS = get_start_menu_buttons(UserState.HOME)
SEARCH_PREF_BUTTONS = get_search_pref_buttons(UserState.HOME)
CHAT_MENU_BUTTONS = get_chat_menu_buttons(UserState.HOME)
END_MENU_BUTTONS = get_end_menu_buttons(UserState.HOME)
GENDER_BUTTONS = get_gender_buttons(UserState.HOME)
AGE_BUTTONS = get_age_buttons(UserState.HOME)
GOAL_BUTTONS = get_goal_buttons(UserState.HOME)
INTERESTS_SKIP_BUTTONS = get_interests_skip_buttons(UserState.HOME)
