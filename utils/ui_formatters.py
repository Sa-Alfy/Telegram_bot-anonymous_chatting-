from typing import Dict, Any

def get_progression_text(stats: Dict[str, Any], is_user1: bool) -> str:
    """Formats level-up and achievement notifications."""
    levelup = stats.get('u1_levelup' if is_user1 else 'u2_levelup')
    achievements = stats.get('u1_achievements' if is_user1 else 'u2_achievements', [])
    
    extra_text = ""
    if levelup:
        extra_text += f"\n\n🎉 **Level Up!**\nYou reached **Level {levelup}**"
    
    if achievements:
        for arch in achievements:
            extra_text += f"\n\n🏅 **Achievement Unlocked!**\n{arch}"
            
    return extra_text

def format_session_summary(stats: Dict[str, Any], is_user1: bool, coins_balance: int) -> str:
    """Creates a beautiful summary text for chat ends."""
    duration = stats.get('duration_minutes', 0)
    earned = stats.get('coins_earned', 0) if is_user1 else stats.get('u2_coins_earned', 0)
    xp = stats.get('xp_earned', 0) if is_user1 else stats.get('u2_xp_earned', 0)
    
    header = "✨ **Chat Session Summary** ✨"
    
    partner_id = stats.get('partner_id') if is_user1 else stats.get('user_id')
    
    summary = (
        f"{header}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🆔 **Partner ID:** `{partner_id or 'Unknown'}`\n"
        f"⌛ **Duration:** {duration} min\n"
        f"💰 **Coins:** +{earned}\n"
        f"📈 **XP Gained:** +{xp}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"💰 **Total Balance:** {coins_balance} coins"
    )
    
    summary += get_progression_text(stats, is_user1)
    
    return summary
