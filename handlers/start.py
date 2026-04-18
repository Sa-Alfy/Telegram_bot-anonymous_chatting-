import time
import asyncio
from pyrogram import Client, filters
from pyrogram.types import Message
from utils.keyboard import start_menu, appeal_menu, onboarding_menu, consent_menu
from state.match_state import match_state
from database.repositories.user_repository import UserRepository
from services.user_service import UserService
from utils.logger import logger
from database.repositories.report_repository import ReportRepository

def get_start_text(coins: int, is_guest: bool = False) -> str:
    guest_text = "\n\n⚠️ **Guest Mode**: Create a profile to earn XP and Coins!" if is_guest else ""
    return (
        "🤖 **Anonymous Chat**\n\n"
        "Connect with a random stranger.\n\n"
        f"💰 **Your Balance:** {coins} coins"
        f"{guest_text}"
    )

@Client.on_message(filters.command("start") & filters.private)
async def start_command(client: Client, message: Message):
    user_id = message.from_user.id
    first_name = message.from_user.first_name
    username = message.from_user.username
    
    # 1. Fetch or Create User
    user = await UserRepository.get_by_telegram_id(user_id)
    if not user:
        user = await UserRepository.create(user_id, username, first_name)
        logger.info(f"🆕 New user registered: {first_name} ({user_id})")

    # 2. Block Check
    if user.get("is_blocked"):
        # Check appeal status (logic simplified: if user has any appeal row)
        appeals = await ReportRepository.get_pending_appeals()
        user_appeal = next((a for a in appeals if a['user_id'] == user_id), None)
        appeal_status = "✅ Appeal Submitted. Waiting for review." if user_appeal else "❌ No appeal submitted yet."
        
        text = (
            "🚫 **ACCESS DENIED**\n\n"
            "Your account has been blocked due to multiple reports or administrative action.\n\n"
            f"📊 **Reports:** {user.get('reports', 0)}\n"
            f"📝 **Status:** {appeal_status}\n\n"
            "If you believe this is a mistake, you can submit a one-time appeal below."
        )
        sent = await message.reply_text(text=text, reply_markup=appeal_menu())
        match_state.user_ui_messages[user_id] = sent.id
        return

    # 3. UI Cleanup (Delete previous message if exists)
    prev_msg_id = match_state.user_ui_messages.get(user_id)
    if prev_msg_id:
        try:
            await client.delete_messages(user_id, prev_msg_id)
        except Exception as e:
            logger.debug(f"UI cleanup failed for {user_id}: {e}")
            pass

    # 4. Consent Gate (Meta Compliance)
    if not user.get("consent_given_at"):
        text = (
            "👋 **Welcome to Neonymo!**\n\n"
            "Before you can start chatting anonymously, please review and accept our "
            "Terms of Service and Privacy Policy.\n\n"
            "🛡️ **Privacy:** We do not store your real identity. Chats are end-to-end encrypted.\n"
            "📋 **Terms of Service:** You must be 18+. No harassment, spam, or illegal content.\n\n"
            "By tapping 'I Accept', you agree to our Privacy Policy and Terms of Service."
        )
        sent = await message.reply_text(text=text, reply_markup=consent_menu())
        match_state.user_ui_messages[user_id] = sent.id
        return

    # 5. Daily Login Reward
    is_guest = user.get("is_guest", 1)
    reward_text = ""
    if not is_guest:
        reward_data = await UserService.check_daily_reward(user_id)
        if reward_data:
            # Refresh user data to get new coins
            user = await UserRepository.get_by_telegram_id(user_id)
            
            # Send a dedicated rich media pop-up
            try:
                await message.reply_text(
                    f"🎁 **DAILY LOGIN REWARD** 🎁\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"💰 **+{reward_data['reward']} Coins** added to your balance!\n"
                    f"🔥 **Current Streak:** {reward_data['streak']} Days\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"Come back tomorrow to increase your multiplier!"
                )
            except Exception as e:
                logger.debug(f"Daily reward notify failed for {user_id}: {e}")
                pass

    # 5. Onboarding or Normal Start
    if is_guest and user.get("gender") == "Not specified":
        text = (
            "👋 **Welcome to Neonymo!**\n\n"
            "You are currently in **Guest Mode**. You can chat with anyone, but you won't earn rewards.\n\n"
            "Would you like to create a profile now? (Takes 30 seconds)"
        )
        sent = await message.reply_photo(
            photo="https://raw.githubusercontent.com/Sa-Alfy/Telegram_bot-anonymous_chatting-/main/assets/logo.png",
            caption=text,
            reply_markup=onboarding_menu()
        )
    else:
        coins = user.get("coins") or 0
        text = get_start_text(coins, is_guest) + reward_text
        sent = await message.reply_photo(
            photo="https://raw.githubusercontent.com/Sa-Alfy/Telegram_bot-anonymous_chatting-/main/assets/logo.png",
            caption=text,
            reply_markup=start_menu(is_guest)
        )
        
    match_state.user_ui_messages[user_id] = sent.id
    asyncio.create_task(UserRepository.update(user_id, last_active=int(time.time())))
