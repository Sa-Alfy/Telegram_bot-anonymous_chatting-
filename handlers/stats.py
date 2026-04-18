import time
from typing import Optional, Dict, Any
from pyrogram import Client, filters
from pyrogram.types import Message

from database.repositories.user_repository import UserRepository
from database.repositories.admin_repository import AdminRepository
from database.connection import db
from services.event_manager import get_active_event
from utils.keyboard import start_menu, leaderboard_menu
from utils.logger import logger

def format_time(seconds: int) -> str:
    """Formats seconds into a human-readable HH:MM or MM string."""
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    if hours > 0:
        return f"{hours}h {minutes}m"
    return f"{minutes}m"

async def get_stats_text(user_id: int) -> str:
    """Retrieves and formats user statistics asynchronously."""
    user = await UserRepository.get_by_telegram_id(user_id)
    if not user:
        return "❌ User profile not found."
    
    coins = user.get("coins", 0)
    matches = user.get("total_matches", 0)
    total_time = user.get("total_chat_time", 0)
    level = user.get("level", 1)
    xp = user.get("xp", 0)
    vip = user.get("vip_status", 0)
    streak = user.get("daily_streak", 0)
    weekly = user.get("weekly_streak", 0)
    monthly = user.get("monthly_streak", 0)
    
    formatted_time = format_time(total_time)
    avg_dur = format_time(user.get("avg_duration_seconds", 0)) if matches > 0 else "0m"
    vip_tag = " ✨ **VIP**" if vip else ""
    
    # Daily Challenge stats (from JSON data via UserRepository)
    challenge = user.get("daily_challenge", {})
    matches_c = challenge.get("matches_completed", 0)
    messages_c = challenge.get("messages_sent", 0)
    challenge_status = "✅ **Completed!**" if challenge.get("completed") else f"({min(5, matches_c)}/5 Matches, {min(50, messages_c)}/50 Msgs)"
    
    # Achievement Badges
    badges = []
    if vip: badges.append("✨ VIP")
    if coins >= 100: badges.append("💎 Whale")
    if streak >= 7: badges.append("🔥 Streak Master")
    if matches >= 10: badges.append("🤝 Matcher")
    
    badge_text = " ".join(badges) if badges else "None yet"
    
    # Event Stats
    active_event = get_active_event()
    event_info = ""
    if active_event["id"] and active_event["type"] == "tournament":
        pts = user.get("seasonal_events", {}).get("event_points", 0)
        event_info = f"\n🏆 **Tournament:** {active_event['name']}\n🎗 **Event Points:** {pts} pts\n"
    
    is_guest = user.get("is_guest", 1)
    guest_tag = " (Guest)" if is_guest else ""
    
    return (
        f"📊 **User Statistics** (Lv. {level}){guest_tag}{vip_tag}\n\n"
        f"💰 **Balance:** {coins} coins\n"
        f"💬 **Total Matches:** {matches}\n"
        f"⏱ **Total Chat Time:** {formatted_time}\n"
        f"📈 **Avg. Match Duration:** {avg_dur}\n"
        f"📈 **Total XP:** {xp} XP\n\n"
        f"📅 **Daily Challenge:** {challenge_status}\n\n"
        f"🎖 **Badges:** {badge_text}\n"
        f"🔥 **Daily Streak:** {streak} days\n"
        f"🗓 **Weekly Streaks:** {weekly}\n"
        f"🌙 **Monthly Streaks:** {monthly}\n"
        f"{event_info}\n"
        "Earn more coins and XP by staying active in chats!"
    )

@Client.on_message(filters.command("stats") & filters.private)
async def stats_command(client: Client, message: Message):
    user_id = message.from_user.id
    user = await UserRepository.get_by_telegram_id(user_id)
    text = await get_stats_text(user_id)
    await message.reply_text(
        text=text,
        reply_markup=start_menu(user.get("is_guest", 1) if user else True)
    )

async def get_admin_stats_text() -> str:
    """Aggregates system-wide statistics from the async database."""
    stats = await AdminRepository.get_system_stats()
    
    return (
        f"🛠 **Admin System Analytics**\n\n"
        f"👥 **Total Users:** {stats['total_users']}\n"
        f"💬 **Recent Sessions:** {stats['sessions_24h']}\n"
        f"🚩 **Pending Reports:** {stats['pending_reports']}\n"
        f"\n🕒 *Dashboard Sync: {time.strftime('%H:%M:%S')}*"
    )

async def get_leaderboard_text(filter_type: str = "all") -> str:
    """Generates a leaderboard of top 10 users using the production database."""
    if filter_type == "weekly":
        title = "🏆 **Weekly Top Matchmakers**"
        query = "SELECT telegram_id, total_matches as val, vip_status FROM users WHERE is_blocked=false ORDER BY total_matches DESC LIMIT 10"
    elif filter_type == "daily":
        title = "☀️ **Daily Top Matchmakers**"
        query = "SELECT telegram_id, total_matches as val, vip_status FROM users WHERE is_blocked=false ORDER BY total_matches DESC LIMIT 10"
    else:
        title = "🏆 **Global Top Matchmakers**"
        query = "SELECT telegram_id, total_matches as val, vip_status FROM users WHERE is_blocked=false ORDER BY total_matches DESC LIMIT 10"

    rows = await db.fetchall(query)
    
    leaderboard_lines = []
    for i, row in enumerate(rows, 1):
        uid = row['telegram_id']
        val = row['val']
        is_vip = row['vip_status']
        mask_id = str(uid)[-4:]
        vip_star = "✨" if is_vip else ""
        leaderboard_lines.append(f"{i}. {vip_star}Stranger **#{mask_id}** — {val} matches")
    
    if not leaderboard_lines:
        return f"{title}\n\nNo records found for this category!"
        
    return f"{title}\n\n" + "\n".join(leaderboard_lines)

@Client.on_message(filters.command("leaderboard") & filters.private)
async def leaderboard_command(client: Client, message: Message):
    text = await get_leaderboard_text()
    await message.reply_text(
        text=text,
        reply_markup=leaderboard_menu()
    )
