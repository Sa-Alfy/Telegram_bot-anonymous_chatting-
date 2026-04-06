from pyrogram import Client, filters
from pyrogram.types import Message
from services.chat_service import relay_message
from services.user_service import is_user_blocked, update_last_active, increment_challenge, check_milestone, add_xp, add_coins

@Client.on_message(~filters.command(["start", "help", "stop", "next", "admin_stats", "stats", "leaderboard", "reveal", "priority", "find", "report"]) & filters.private)
async def chat_handler(client: Client, message: Message):
    user_id = message.from_user.id
    
    # Update last active
    update_last_active(user_id)
    
    # Check if blocked
    if is_user_blocked(user_id):
        return

    # Tracking mini-challenges: messages_sent
    increment_challenge(user_id, "messages_sent")
    milestone = check_milestone(user_id, "messages_sent")
    if milestone:
        m = milestone['milestone']
        xp = milestone['reward_xp']
        coins = milestone['reward_coins']
        add_xp(user_id, xp)
        add_coins(user_id, coins)
        await message.reply_text(
            f"🎖 **Mini-Challenge Reached!**\n"
            f"You've sent **{m} messages**!\n"
            f"🎁 **Reward:** +{xp} XP, +{coins} coins"
        )

    await relay_message(client, message)
