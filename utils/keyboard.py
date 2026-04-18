from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from utils.renderer import StateBoundPayload
from state.match_state import UserState

def start_menu(is_guest: bool = False, current_state: str = UserState.HOME):
    buttons = [
        [InlineKeyboardButton("🔍 Find Partner", callback_data=StateBoundPayload.encode("search", "0", current_state))],
    ]
    if is_guest:
        buttons.append([InlineKeyboardButton("👤 Create Profile (Gain XP/Coins)", callback_data=StateBoundPayload.encode("onboarding_start", "0", current_state))])
    
    buttons.extend([
        [
            InlineKeyboardButton("📊 Stats", callback_data=StateBoundPayload.encode("stats", "0", current_state)),
            InlineKeyboardButton("🏆 Leaderboard", callback_data=StateBoundPayload.encode("leaderboard", "0", current_state))
        ],
        [InlineKeyboardButton("🛍 Seasonal Shop", callback_data=StateBoundPayload.encode("seasonal_shop", "0", current_state))],
        [InlineKeyboardButton("ℹ️ How it Works", callback_data=StateBoundPayload.encode("help", "0", current_state))]
    ])
    return InlineKeyboardMarkup(buttons)

def onboarding_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("👤 Create Profile", callback_data="onboarding_start")],
        [InlineKeyboardButton("⏩ Skip for now", callback_data="onboarding_skip")]
    ])

def consent_menu():
    """Menu for mandatory Terms & Conditions acceptance."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ I Accept", callback_data="consent_accept")],
        [InlineKeyboardButton("❌ Decline", callback_data="consent_decline")]
    ])

def gender_menu():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("👨 Male", callback_data="set_gender_male"),
            InlineKeyboardButton("👩 Female", callback_data="set_gender_female")
        ],
        [InlineKeyboardButton("🌈 Other", callback_data="set_gender_other")]
    ])

def age_menu():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🎓 18-21", callback_data="set_age_18-21"),
            InlineKeyboardButton("💼 22-25", callback_data="set_age_22-25")
        ],
        [
            InlineKeyboardButton("📈 26-29", callback_data="set_age_26-29"),
            InlineKeyboardButton("🍷 30+", callback_data="set_age_30+")
        ]
    ])

def goal_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💬 Casual Chatting", callback_data="set_goal_chat")],
        [InlineKeyboardButton("❤️ Dating / Romance", callback_data="set_goal_dating")],
        [InlineKeyboardButton("🤝 Making Friends", callback_data="set_goal_friends")]
    ])

def interests_skip_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⏩ Skip Interests", callback_data="set_interests_skip")]
    ])

def location_skip_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⏩ Skip Location", callback_data="set_location_skip")]
    ])

def bio_skip_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⏩ Skip Bio", callback_data="set_bio_skip")]
    ])

def stats_menu(has_pending: bool = False):
    """Profile/Stats menu with friend request alerts."""
    buttons = [
        [
            InlineKeyboardButton("🔍 Find Partner", callback_data="search"),
            InlineKeyboardButton("✏️ Edit Profile", callback_data="onboarding_start")
        ]
    ]
    if has_pending:
        buttons.append([InlineKeyboardButton("📬 Pending Requests", callback_data="view_requests")])
    
    buttons.append([InlineKeyboardButton("👥 Friends List", callback_data="friends_list")])
        
    buttons.extend([
        [
            InlineKeyboardButton("🛍 Seasonal Shop", callback_data="seasonal_shop"),
            InlineKeyboardButton("🔙 Back", callback_data="cancel_search")
        ]
    ])
    return InlineKeyboardMarkup(buttons)

def friends_list_menu(friends_list: list):
    buttons = []
    for f in friends_list[:10]: # Limit to 10 for UI layout
        buttons.append([InlineKeyboardButton(f"👤 {f.get('first_name', 'Friend')}", callback_data=f"friend_action_{f['telegram_id']}")])
    buttons.append([InlineKeyboardButton("🔙 Back", callback_data="stats")])
    return InlineKeyboardMarkup(buttons)

def friend_action_menu(friend_id: int):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💬 Send Message", callback_data=f"msg_friend_{friend_id}")],
        [InlineKeyboardButton("❌ Remove Friend", callback_data=f"remove_friend_{friend_id}")],
        [InlineKeyboardButton("🔙 Back to Friends", callback_data="friends_list")]
    ])

def seasonal_shop_menu(user_coins: int = 0):
    """Temporary Seasonal Shop UI."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("👑 30-Day VIP Subscription (500 coins)", callback_data="buy_shop_vip")],
        [InlineKeyboardButton("🔥 'OG User' Badge (300 coins)", callback_data="buy_shop_og")],
        [InlineKeyboardButton("🐋 'Whale' Badge (1000 coins)", callback_data="buy_shop_whale")],
        [InlineKeyboardButton("💳 Top-Up Coins (bKash/Card)", url="https://t.me/YourAdminStore")],
        [InlineKeyboardButton("🔙 Back", callback_data="cancel_search")]
    ])

def event_leaderboard_menu():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🏆 Tournament Top", callback_data="lb_event"),
            InlineKeyboardButton("🌎 Global Top", callback_data="lb_all")
        ],
        [InlineKeyboardButton("🔙 Back", callback_data="leaderboard")]
    ])

def search_pref_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("👫 Anyone", callback_data="search_pref_Any")],
        [
            InlineKeyboardButton("👩 Females (Free VIP / 15 Coins)", callback_data="search_pref_Female"),
            InlineKeyboardButton("👨 Males (Free VIP / 15 Coins)", callback_data="search_pref_Male")
        ],
        [InlineKeyboardButton("🔙 Back", callback_data="cancel_search")]
    ])

def search_menu(current_state: str = UserState.HOME):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⚡ Priority Match (5 coins)", callback_data=StateBoundPayload.encode("search_pref_Priority", "0", current_state))],
        [
            InlineKeyboardButton("💎 Priority Packs", callback_data=StateBoundPayload.encode("priority_packs", "0", current_state)),
            InlineKeyboardButton("🚀 Boosters", callback_data=StateBoundPayload.encode("booster_menu", "0", current_state))
        ],
        [InlineKeyboardButton("❌ Cancel", callback_data=StateBoundPayload.encode("cancel_search", "0", current_state))]
    ])

def priority_pack_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📦 5 Priority Matches - 20 coins", callback_data="buy_pack_5")],
        [InlineKeyboardButton("📦 15 Priority Matches - 50 coins", callback_data="buy_pack_15")],
        [InlineKeyboardButton("⚡ 1h Unlimited Priority - 30 coins", callback_data="buy_timed_priority_1")],
        [InlineKeyboardButton("⚡ 3h Unlimited Priority - 75 coins", callback_data="buy_timed_priority_3")],
        [InlineKeyboardButton("⚡ 24h Unlimited Priority - 200 coins", callback_data="buy_timed_priority_24")],
        [InlineKeyboardButton("🔙 Back", callback_data="search")]
    ])

def booster_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🚀 1h Coin Booster (2x Rewards) - 50 coins", callback_data="buy_booster_1")],
        [InlineKeyboardButton("🔙 Back", callback_data="search")]
    ])

def leaderboard_menu():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🔥 Hourly", callback_data="lb_hourly"),
            InlineKeyboardButton("☀️ Daily", callback_data="lb_daily"),
            InlineKeyboardButton("📅 Weekly", callback_data="lb_weekly")
        ],
        [
            InlineKeyboardButton("✨ VIP", callback_data="lb_vip"),
            InlineKeyboardButton("🏆 Event", callback_data="event_leaderboard")
        ],
        [InlineKeyboardButton("🌎 Global", callback_data="lb_all")],
        [InlineKeyboardButton("🔙 Back", callback_data="cancel_search")]
    ])

def chat_menu():
    """Redesigned chat menu to prevent misclicks between Stop/Next."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⏮ Next (Skip)", callback_data="next")],
        [InlineKeyboardButton("🛑 Stop Chatting", callback_data="stop")],
        [
            InlineKeyboardButton("👁️ Reveal Identity", callback_data="reveal"),
            InlineKeyboardButton("⚠️ Report", callback_data="report")
        ],
        [
            InlineKeyboardButton("🎲 Icebreaker (5 Coins)", callback_data="icebreaker"),
            InlineKeyboardButton("❤️ Reactions", callback_data="open_reactions")
        ]
    ])

def reaction_menu():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("❤️", callback_data="react_heart"),
            InlineKeyboardButton("😂", callback_data="react_joy"),
            InlineKeyboardButton("😮", callback_data="react_wow"),
            InlineKeyboardButton("😢", callback_data="react_sad"),
            InlineKeyboardButton("👍", callback_data="react_up")
        ],
        [InlineKeyboardButton("🔙 Back", callback_data="back_to_chat")]
    ])

def peek_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔥 Reveal Streak", callback_data="peek_streak")],
        [InlineKeyboardButton("📈 Reveal Level", callback_data="peek_level")],
        [InlineKeyboardButton("🔙 Cancel", callback_data="cancel_reveal")]
    ])

def confirm_reveal_menu(cost: int = 15):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(f"✅ Confirm ({cost} coins)", callback_data=f"confirm_reveal_{cost}"),
            InlineKeyboardButton("❌ Cancel", callback_data="cancel_reveal")
        ]
    ])

def end_menu(can_rematch: bool = False, partner_id: int = None):
    buttons = [
        [InlineKeyboardButton("🔍 Find New Partner", callback_data="search")]
    ]
    if can_rematch:
        buttons.append([InlineKeyboardButton("🔄 Rematch (1 coin)", callback_data="rematch")])
        
    if partner_id:
        buttons.extend([
            [
                InlineKeyboardButton("👍 Like", callback_data=StateBoundPayload.encode("vote_like", str(partner_id), "END_MENU")),
                InlineKeyboardButton("👎 Dislike", callback_data=StateBoundPayload.encode("vote_dislike", str(partner_id), "END_MENU"))
            ],
            [
                InlineKeyboardButton("👨 Boy", callback_data=StateBoundPayload.encode("vote_gender_male", str(partner_id), "END_MENU")),
                InlineKeyboardButton("👩 Girl", callback_data=StateBoundPayload.encode("vote_gender_female", str(partner_id), "END_MENU"))
            ]
        ])
    
    buttons.extend([
        [
            InlineKeyboardButton("📊 My Stats", callback_data="stats"),
            InlineKeyboardButton("🏆 Leaderboard", callback_data="leaderboard")
        ]
    ])
    return InlineKeyboardMarkup(buttons)

def admin_menu():
    """Central administrative dashboard with quick-action buttons."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📊 Stats", callback_data="admin_stats"),
            InlineKeyboardButton("🏥 Health", callback_data="admin_health")
        ],
        [
            InlineKeyboardButton("📢 Broadcast", callback_data="admin_broadcast_prompt"),
            InlineKeyboardButton("🚫 Banned List", callback_data="admin_list_banned")
        ],
        [
            InlineKeyboardButton("💰 Gift Coins", callback_data="admin_gift_prompt"),
            InlineKeyboardButton("💸 Take Coins", callback_data="admin_deduct_prompt")
        ],
        [
            InlineKeyboardButton("✨ Set VIP", callback_data="admin_vip_prompt"),
            InlineKeyboardButton("👤 Manage User", callback_data="admin_user_manage_prompt")
        ],
        [InlineKeyboardButton("🛠 Debug Mode", callback_data="admin_debug")],
        [InlineKeyboardButton("🔄 FULL SYSTEM RESET", callback_data="admin_reset_confirm")],
        [InlineKeyboardButton("🔙 Close Admin Console", callback_data="back_to_chat")]
    ])

def admin_vip_menu(target_id: int):
    """Menu for toggling VIP status."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Give VIP Status", callback_data=f"admin_set_vip_{target_id}_true"),
            InlineKeyboardButton("❌ Revoke VIP status", callback_data=f"admin_set_vip_{target_id}_false")
        ],
        [InlineKeyboardButton("🔙 Cancel", callback_data="admin_stats")]
    ])

def admin_action_menu(target_id: int, is_blocked: bool):
    """Menu for individual user management."""
    btn_text = "🔓 Unban User" if is_blocked else "🚫 Ban User"
    callback = f"admin_unban_{target_id}" if is_blocked else f"admin_ban_{target_id}"
    
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(btn_text, callback_data=callback)],
        [
            InlineKeyboardButton("💰 Gift 50", callback_data=f"admin_quick_gift_{target_id}_50"),
            InlineKeyboardButton("💸 Take 50", callback_data=f"admin_quick_deduct_{target_id}_50")
        ],
        [InlineKeyboardButton("🔙 Cancel", callback_data="admin_stats")]
    ])

def appeal_menu():
    """Menu shown to banned users allowing them to submit an appeal."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📝 Submit Appeal", callback_data="user_appeal")],
        [InlineKeyboardButton("🔄 Refresh Status", callback_data="stats")]
    ])

def banned_list_menu(user_id: int):
    """Admin menu for an individual banned user."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Unban & Send Message", callback_data=f"admin_unban_{user_id}"),
            InlineKeyboardButton("❌ Keep Banned", callback_data="admin_list_banned")
        ]
    ])

def report_confirm_menu():
    """Prompt after clicking Report to allow for an optional reason."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🚫 Report Immediately", callback_data="report_confirm")],
        [InlineKeyboardButton("📝 Add Reason & Report", callback_data="report_with_reason")],
        [InlineKeyboardButton("❌ Cancel", callback_data="back_to_chat")]
    ])
def accept_friend_menu(sender_id: int):
    """Menu sent to the recipient of a friend request."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Accept Friend", callback_data=f"accept_friend_{sender_id}"),
            InlineKeyboardButton("❌ Ignore", callback_data="back_to_chat")
        ]
    ])

def pending_requests_menu(requests: list):
    """Menu for viewing and managing multiple pending requests."""
    buttons = []
    for req in requests:
        sender_name = req.get('first_name', 'Stranger')
        sender_id = req.get('telegram_id')
        buttons.append([
            InlineKeyboardButton(f"👤 {sender_name}", callback_data=f"peek_detail_{sender_id}"),
            InlineKeyboardButton("✅", callback_data=f"accept_friend_{sender_id}"),
            InlineKeyboardButton("❌", callback_data=f"decline_friend_{sender_id}")
        ])
    
    buttons.append([InlineKeyboardButton("🔙 Back to Stats", callback_data="stats")])
    return InlineKeyboardMarkup(buttons)

def retry_search_menu(current_state: str = UserState.HOME):
    """Menu shown when matchmaking is rate-limited."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Try Searching Again", callback_data=StateBoundPayload.encode("search", "0", current_state))]
    ])
