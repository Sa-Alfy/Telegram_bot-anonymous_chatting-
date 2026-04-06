from pyrogram import Client, filters
from pyrogram.types import Message
from services.user_service import get_user_profile
from state.persistence import user_profiles
from utils.keyboard import start_menu
from config import ADMIN_ID
from services.event_manager import get_active_event

def format_time(seconds: int) -> str:
    """Formats seconds into a human-readable HH:MM or MM string."""
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    if hours > 0:
        return f"{hours}h {minutes}m"
    return f"{minutes}m"

def get_stats_text(user_id: int) -> str:
    """Retrieves and formats user statistics."""
    profile = get_user_profile(user_id)
    
    coins = profile.get("coins", 0)
    matches = profile.get("matches", 0)
    total_time = profile.get("total_chat_time", 0)
    level = profile.get("level", 1)
    xp = profile.get("xp", 0)
    vip = profile.get("vip", False)
    streak = profile.get("daily_streak", 0)
    weekly = profile.get("weekly_streak", 0)
    
    formatted_time = format_time(total_time)
    avg_dur = format_time(profile.get("avg_duration_seconds", 0)) if matches > 0 else "0m"
    vip_tag = " ✨ **VIP**" if vip else ""
    monthly = profile.get("monthly_streak", 0)
    friends_count = len(profile.get("friends", []))
    
    # Step 4: Daily Challenge stats
    challenge = profile.get("daily_challenge", {})
    matches_c = challenge.get("matches_completed", 0)
    messages_c = challenge.get("messages_sent", 0)
    challenge_status = "✅ **Completed!**" if challenge.get("completed") else f"({min(5, matches_c)}/5 Matches, {min(50, messages_c)}/50 Msgs)"
    
    # Step 5: Achievement Badges
    badges = []
    if profile.get("vip"): badges.append("✨ VIP")
    if coins >= 100: badges.append("💎 Whale")
    if streak >= 7: badges.append("🔥 Streak Master")
    if matches >= 10: badges.append("🤝 Matcher")
    if len(profile.get("reaction_history", [])) > 20: badges.append("👑 Reaction King")
    
    badge_text = " ".join(badges) if badges else "None yet"
    
    # Phase 5: Event Stats
    active_event = get_active_event()
    event_info = ""
    if active_event["id"] and active_event["type"] == "tournament":
        pts = profile.get("seasonal_events", {}).get("event_points", 0)
        event_info = f"\n🏆 **Tournament:** {active_event['name']}\n🎗 **Event Points:** {pts} pts\n"
    
    return (
        f"📊 **User Statistics** (Lv. {level}){vip_tag}\n\n"
        f"💰 **Balance:** {coins} coins\n"
        f"💬 **Total Matches:** {matches}\n"
        f"💌 **Friends:** {friends_count}\n"
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
    await message.reply_text(
        text=get_stats_text(user_id),
        reply_markup=start_menu()
    )

def get_admin_stats_text() -> str:
    """Aggregates system-wide statistics for admins."""
    profiles = user_profiles.values()
    total_users = len(profiles)
    total_coins = sum(p.get("coins", 0) for p in profiles)
    total_matches = sum(p.get("matches", 0) for p in profiles)
    vip_users = sum(1 for p in profiles if p.get("vip", False))
    blocked_users = sum(1 for p in profiles if p.get("blocked", False))
    
    # Step 7: New Social & Challenge Metrics
    total_friends = sum(len(p.get("friends", [])) for p in profiles)
    challenges_completed = sum(1 for p in profiles if p.get("daily_challenge", {}).get("completed"))
    
    # Simple aggregation of reaction emojis (Step 7)
    all_reactions = []
    for p in profiles:
        for entry in p.get("reaction_history", []):
            if isinstance(entry, dict):
                all_reactions.append(entry.get("emoji", ""))
    
    top_emoji = max(set(all_reactions), key=all_reactions.count) if all_reactions else "None"

    avg_level = sum(p.get("level", 1) for p in profiles) / max(1, total_users)
    avg_matches = total_matches / max(1, total_users)
    
    return (
        f"🛠 **Admin System Analytics**\n\n"
        f"👥 **Total Users:** {total_users}\n"
        f"✨ **VIP Users:** {vip_users}\n"
        f"🚫 **Blocked Users:** {blocked_users}\n\n"
        f"💰 **Economy Pool:** {total_coins} coins\n"
        f"🤝 **Total Matches:** {total_matches}\n\n"
        f"💌 **Total Friends Made:** {total_friends}\n"
        f"🏆 **Challenges Done Today:** {challenges_completed}\n"
        f"🎭 **Top Reaction:** {top_emoji}\n\n"
        f"📈 **Leveling Average:** Lv. {avg_level:.1f}\n"
        f"📊 **Matching Average:** {avg_matches:.1f} per user"
    )

@Client.on_message(filters.command("admin_stats") & filters.private)
async def admin_stats_command(client: Client, message: Message):
    if message.from_user.id != ADMIN_ID:
        await message.reply_text(f"🚫 **Access Denied!**\n\nYour ID: `{message.from_user.id}`\n\nPlease ensure this ID is added as the `ADMIN_ID` in your `.env` file.")
        return
    await message.reply_text(get_admin_stats_text())

def get_leaderboard_text(filter_type: str = "all") -> str:
    """Generates a leaderboard of top 10 users based on filter."""
    valid_users = [(uid, p) for uid, p in user_profiles.items() if not p.get("blocked", False)]
    
    if filter_type == "weekly":
        title = "🏆 **Weekly Top Matchmakers**"
        sort_key = lambda x: x[1].get("matches_this_week", 0)
    elif filter_type == "daily":
        title = "☀️ **Daily Top Matchmakers**"
        sort_key = lambda x: x[1].get("matches_today", 0)
    elif filter_type == "hourly":
        title = "🔥 **Hourly Top Matchmakers**"
        sort_key = lambda x: x[1].get("matches_today", 0) // 4 # Simulated for now
    elif filter_type == "vip":
        title = "🏆 **VIP Leaderboard**"
        valid_users = [u for u in valid_users if u[1].get("vip", False)]
        sort_key = lambda x: x[1].get("matches", 0)
    elif filter_type == "event":
        active_event = get_active_event()
        title = f"🏆 **Tournament: {active_event['name']}**"
        sort_key = lambda x: x[1].get("seasonal_events", {}).get("event_points", 0)
    else:
        title = "🏆 **Global Top Matchmakers**"
        sort_key = lambda x: x[1].get("matches", 0)

    sorted_users = sorted(valid_users, key=sort_key, reverse=True)
    top_10 = sorted_users[:10]
    
    leaderboard_lines = []
    for i, (uid, profile) in enumerate(top_10, 1):
        # Since it's anonymous, we use a masked ID
        mask_id = str(uid)[-4:]
        val = sort_key((uid, profile))
        unit = "pts" if filter_type == "event" else "matches"
        vip_star = "✨" if profile.get("vip") else ""
        leaderboard_lines.append(f"{i}. {vip_star}Stranger **#{mask_id}** — {val} {unit}")
    
    if not leaderboard_lines:
        return f"{title}\n\nNo records found for this category!"
        
    return f"{title}\n\n" + "\n".join(leaderboard_lines)

def get_admin_events_text() -> str:
    """Aggregates event-specific statistics for admins."""
    active_event = get_active_event()
    if not active_event["id"]:
        return "❌ **No active event right now.**"
        
    profiles = user_profiles.values()
    participants = [p for p in profiles if p.get("seasonal_events", {}).get("event_points", 0) > 0]
    total_pts = sum(p.get("seasonal_events", {}).get("event_points", 0) for p in participants)
    
    return (
        f"📅 **Event Monitor: {active_event['name']}**\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🆔 **ID:** `{active_event['id']}`\n"
        f"🎭 **Type:** {active_event['type'].capitalize()}\n"
        f"⚡ **Multiplier:** {active_event['multiplier']}x\n"
        f"⌛ **Ends in:** {int((active_event['ends_at'] - time.time()) // 60)} min\n\n"
        f"👥 **Active Participants:** {len(participants)}\n"
        f"🎗 **Total Points Earned:** {total_pts} pts\n"
        f"📈 **Participation Rate:** {(len(participants)/max(1, len(profiles))*100):.1f}%"
    )

@Client.on_message(filters.command("admin_events") & filters.private)
async def admin_events_command(client: Client, message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    await message.reply_text(get_admin_events_text())

@Client.on_message(filters.command("leaderboard") & filters.private)
async def leaderboard_command(client: Client, message: Message):
    from utils.keyboard import leaderboard_menu
    await message.reply_text(
        text=get_leaderboard_text(),
        reply_markup=leaderboard_menu()
    )
