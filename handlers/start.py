from pyrogram import Client, filters
from pyrogram.types import Message
from utils.keyboard import start_menu
from state.memory import user_ui_messages
from services.user_service import get_coins, check_daily_reward, update_last_active

def get_start_text(coins: int) -> str:
    return (
        "🤖 **Anonymous Chat**\n\n"
        "Connect with a random stranger.\n\n"
        f"💰 **Your Balance:** {coins} coins"
    )

@Client.on_message(filters.command("start") & filters.private)
async def start_command(client: Client, message: Message):
    user_id = message.from_user.id
    coins = get_coins(user_id)
    
    # Try deleting the previous active UI message to maintain single UI per user
    if user_id in user_ui_messages:
        try:
            await client.delete_messages(chat_id=user_id, message_ids=user_ui_messages[user_id])
        except Exception:
            pass
            
    # Update last active
    update_last_active(user_id)
    
    # Check Daily Login Reward
    reward_data = check_daily_reward(user_id)
    reward_text = ""
    if reward_data:
        coins = get_coins(user_id) # Refresh coins after reward
        reward_text = (
            f"\n\n🎉 **Daily Reward Collected!**\n"
            f"💰 **Coins earned:** {reward_data['reward']}\n"
            f"🔥 **Streak:** {reward_data['streak']} days"
        )

    sent = await message.reply_text(
        text=get_start_text(coins) + reward_text,
        reply_markup=start_menu()
    )
    user_ui_messages[user_id] = sent.id

