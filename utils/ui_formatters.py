from typing import Dict, Any

DIVIDER = "━━━━━━━━━━━━━━━━━━"

def get_progress_bar(current_xp: int) -> str:
    """Generates a visual progress bar for levels.
    Formula: Level = floor(sqrt(xp / 10)) + 1
    Next Level XP = (Level)^2 * 10
    Base Level XP = (Level - 1)^2 * 10
    """
    import math
    level = int(math.floor(math.sqrt(current_xp / 10))) + 1
    base_xp = ((level - 1) ** 2) * 10
    next_xp = (level ** 2) * 10
    
    needed = next_xp - base_xp
    progress = current_xp - base_xp
    
    if needed <= 0: return ""
    
    percent = (progress / needed) * 10
    filled = int(percent)
    empty = 10 - filled
    
    bar = "█" * filled + "░" * empty
    return f"\n`[{bar}]` **Level {level}** ({progress}/{needed} XP)"

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
    xp_earned = stats.get('xp_earned', 0) if is_user1 else stats.get('u2_xp_earned', 0)
    
    # We need total XP to show the bar
    # (Assuming stats contains total_xp or we can sum it)
    total_xp = stats.get('total_xp', 0) # Fallback if not injected by service
    
    header = "✨ **Chat Session Summary** ✨"
    partner_id = stats.get('partner_id') if is_user1 else stats.get('user_id')
    
    summary = (
        f"{header}\n"
        f"{DIVIDER}\n"
        f"🆔 **Partner ID:** `{partner_id or 'Unknown'}`\n"
        f"⌛ **Duration:** {duration} min\n"
        f"💰 **Coins:** +{earned}\n"
        f"📈 **XP Gained:** +{xp_earned}\n"
        f"{DIVIDER}\n"
        f"💰 **Total Balance:** {coins_balance} coins"
    )
    
    if total_xp > 0:
        summary += f"\n{get_progress_bar(total_xp)}"
    
    summary += get_progression_text(stats, is_user1)
    
    return summary

def get_match_found_text(is_rematch: bool = False, include_safety: bool = False) -> str:
    """Standardized 'Match Found' message. Safety included only if requested."""
    emoji = "🔄" if is_rematch else "💬"
    header = "**Rematch Successful!**" if is_rematch else "**Match Found!**"
    sub_text = "Reconnected with partner..." if is_rematch else "You are now chatting with a stranger..."
    
    text = f"{emoji} {header}\n{sub_text}"
    
    if include_safety:
        text += (
            f"\n\n🛡️ **Safety Reminder:** Stay anonymous! "
            f"Sharing external links or inviting users to other platforms is against our safety policy "
            f"and results in a **10 coin penalty**."
        )
    return text
