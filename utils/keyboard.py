from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

def start_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔍 Find Partner", callback_data="search")],
        [
            InlineKeyboardButton("📊 Stats", callback_data="stats"),
            InlineKeyboardButton("🏆 Leaderboard", callback_data="leaderboard")
        ],
        [InlineKeyboardButton("🛍 Seasonal Shop", callback_data="seasonal_shop")],
        [InlineKeyboardButton("ℹ️ How it Works", callback_data="help")]
    ])

def seasonal_shop_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✨ 3h XP Booster - 100 coins", callback_data="buy_shop_exp_boost_3h")],
        [InlineKeyboardButton("💰 3h Coin Booster - 150 coins", callback_data="buy_shop_coin_boost_3h")],
        [InlineKeyboardButton("⚡ 1h Priority Match - 250 coins", callback_data="buy_shop_priority_1h")],
        [InlineKeyboardButton("🏅 Seasonal Badge - 500 coins", callback_data="buy_shop_badge_seasonal")],
        [InlineKeyboardButton("🔙 Back", callback_data="stats")]
    ])

def event_leaderboard_menu():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🏆 Tournament Top", callback_data="lb_event"),
            InlineKeyboardButton("🌎 Global Top", callback_data="lb_all")
        ],
        [InlineKeyboardButton("🔙 Back", callback_data="leaderboard")]
    ])

def search_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⚡ Priority Match (5 coins)", callback_data="priority_search")],
        [
            InlineKeyboardButton("💎 Priority Packs", callback_data="priority_packs"),
            InlineKeyboardButton("🚀 Boosters", callback_data="booster_menu")
        ],
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel_search")]
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

def chat_menu(reveal_cost: int = 15, peek_cost: int = 5):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("⏭ Next", callback_data="next"),
            InlineKeyboardButton("❌ Stop", callback_data="stop")
        ],
        [
            InlineKeyboardButton(f"👤 Reveal ID ({reveal_cost} coins)", callback_data="reveal"),
            InlineKeyboardButton(f"🔍 Peek Stats ({peek_cost} coins)", callback_data="peek")
        ],
        [
            InlineKeyboardButton("🚨 Report", callback_data="report"),
            InlineKeyboardButton("🎭 React", callback_data="open_reactions"),
            InlineKeyboardButton("💌 Add Friend", callback_data="add_friend")
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

def end_menu(can_rematch: bool = False):
    buttons = [
        [InlineKeyboardButton("🔍 Find New Partner", callback_data="search")]
    ]
    if can_rematch:
        buttons.append([InlineKeyboardButton("🔄 Rematch (1 coin)", callback_data="rematch")])
    
    buttons.extend([
        [
            InlineKeyboardButton("📊 My Stats", callback_data="stats"),
            InlineKeyboardButton("🏆 Leaderboard", callback_data="leaderboard")
        ]
    ])
    return InlineKeyboardMarkup(buttons)
