from typing import Dict, Any
from pyrogram import Client
from database.repositories.stats_repository import StatsRepository
from utils.keyboard import leaderboard_menu, event_leaderboard_menu, start_menu, stats_menu
from utils.logger import logger

class StatsHandler:
    @staticmethod
    async def handle_stats(client: Client, user_id: int) -> Dict[str, Any]:
        """Provides the user's personal statistics dashboard."""
        user = await StatsRepository.get_user_stats(user_id)
        if not user:
            return {"alert": "❌ Profile not found!", "show_alert": True}

        # Format stats message
        stats_text = (
            f"👤 **Your Anonymous Identity**\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"🆔 **My ID:** `{user_id}` (Tap to copy)\n"
            f"🏷 **Name:** {user['first_name']}\n"
            f"📈 **Level:** {user['level']} ({user['xp']} XP)\n"
            f"💰 **Coins:** {user['coins']}\n"
            f"⌛ **Chat Time:** {user['total_chat_time']} min\n"
            f"🤝 **Total Matches:** {user['total_matches']}\n"
            f"🔥 **Daily Streak:** {user['daily_streak']} days\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"✨ **VIP Status:** {'💎 Active' if user['vip_status'] else 'None'}"
        )
        # Check for pending requests
        from database.repositories.friend_repository import FriendRepository
        incoming = await FriendRepository.get_incoming_requests(user_id)
        has_pending = len(incoming) > 0

        return {
            "text": stats_text,
            "reply_markup": stats_menu(has_pending=has_pending)
        }

    @staticmethod
    async def handle_leaderboard(client: Client, user_id: int) -> Dict[str, Any]:
        """Displays the main leaderboard category selection menu."""
        return {
            "text": "🏆 **Global Leaderboards**\n\nChoose a category to see top performers:",
            "reply_markup": leaderboard_menu()
        }

    @classmethod
    async def handle_leaderboard_category(cls, client: Client, user_id: int, category: str) -> Dict[str, Any]:
        """Displays the top 10 users for a specific category."""
        # Handle special menu redirection
        if category == "event_leaderboard":
            return {
                "text": "🏆 **Seasonal Tournament**\n\nTrack your progress in the current global event:",
                "reply_markup": event_leaderboard_menu()
            }
            
        top_users = await StatsRepository.get_leaderboard(category)
        
        category_titles = {
            "all": "🌎 Global All-Time",
            "hourly": "🔥 Hourly Top",
            "daily": "☀️ Daily Top",
            "weekly": "📅 Weekly Top",
            "vip": "✨ VIP Members",
            "lb_event": "🏆 Current Tournament", # Special category from keyboard
            "lb_all": "🌎 Global Top" # Mapping for keyboard callback
        }
        
        title = category_titles.get(category, "🏆 Hall of Fame")
        lb_text = f"**{title}**\n━━━━━━━━━━━━━━━━━━\n\n"
        
        if not top_users:
            lb_text += "_No rankings yet..._"
        else:
            for i, user in enumerate(top_users, 1):
                medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else "👤"
                vip_icon = "💎" if user.get('vip_status') else ""
                lb_text += f"{medal} **{user['first_name']}** - Lvl {user['level']} ({user['xp']} XP) {vip_icon}\n"
        
        lb_text += "\n━━━━━━━━━━━━━━━━━━"
        return {
            "text": lb_text,
            "reply_markup": leaderboard_menu()
        }
