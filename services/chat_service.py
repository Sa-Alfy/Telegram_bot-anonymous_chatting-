import asyncio
import random
import time
from pyrogram import Client
from pyrogram.types import Message
from pyrogram.enums import ChatAction

from state.match_state import match_state
from database.repositories.user_repository import UserRepository
from services.matchmaking import MatchmakingService
from utils.keyboard import end_menu
from utils.helpers import update_user_ui
from utils.logger import logger
from services.event_manager import get_active_event

async def trigger_mini_event(client: Client, user_id: int):
    """Triggers a random mini-event for a user during chat."""
    user = await UserRepository.get_by_telegram_id(user_id)
    if not user: return
    
    now = int(time.time())
    # Cooldown check (using user row or extra data)
    last_event = user.get("last_event_time", 0)
    if now - last_event < 300:
        return
    
    # 5% chance
    if random.random() > 0.05:
        return
        
    events = [
        {"name": "Lucky Coin Bonus", "msg": "💰 **Lucky Coin Bonus!**\nYou found some extra coins during the chat: **+3 Coins!**", "coins": 3, "xp": 0},
        {"name": "XP Boost", "msg": "📈 **XP Boost!**\nYou earned a quick XP boost from this interaction: **+5 XP!**", "coins": 0, "xp": 5}
    ]
    
    event = random.choice(events)
    # Update user
    await UserRepository.increment_coins(user_id, event["coins"])
    await UserRepository.update(user_id, last_event_time=now)
    # XP update (Assuming UserService.add_xp is async)
    from services.user_service import UserService
    await UserService.add_xp(user_id, event["xp"])
    
    try:
        await client.send_message(user_id, event["msg"])
    except:
        pass

async def relay_message(client: Client, message: Message):
    user_id = message.from_user.id
    partner_id = match_state.get_partner(user_id)
    
    if partner_id:
        # 1. VIP Media Filter Check
        if message.voice or message.video or message.video_note or message.audio:
            user = await UserRepository.get_by_telegram_id(user_id)
            if not user or not user.get("vip_status"):
                try:
                    await message.reply_text("❌ **Premium Feature**\nYou must be a **VIP Member** to send Voice Notes or Videos! Purchase a VIP Subscription from the Seasonal Shop.")
                except:
                    pass
                return

        # DEBUG ECHO LOGIC
        if partner_id == 1:
            await message.reply_text(f"💬 **Echo Partner:** {message.text or '[Media]'}")
            return

        try:
            # Trigger Mini-Event
            asyncio.create_task(trigger_mini_event(client, user_id))

            active_event = get_active_event()
            
            # Randomized Typing Styles
            style = random.choice(["fast", "slow", "thoughtful", "normal"])
            if active_event["id"] and active_event["type"] == "mini":
                style = "fast"
                
            base_delay = len(message.text or "") / 20
            delay = base_delay + 0.8
            if style == "fast": delay = base_delay * 0.4 + 0.2
            elif style == "slow": delay = base_delay * 1.5 + 2.0
            elif style == "thoughtful": await asyncio.sleep(random.uniform(1.0, 2.5))
            
            # Safe Chat Action
            try:
                await client.send_chat_action(partner_id, ChatAction.TYPING)
            except:
                pass

            await asyncio.sleep(min(7.0, delay))

            # Relay the message
            try:
                await message.copy(chat_id=partner_id)
            except Exception as e:
                logger.warning(f"Failed to relay message to {partner_id}: {e}")
                await MatchmakingService.disconnect(user_id)
                return

        except Exception as e:
            logger.warning(f"Failed to relay message from {user_id} to {partner_id}: {e}")
            await MatchmakingService.disconnect(user_id)
            await update_user_ui(client, user_id, "❌ Chat ended due to an error.", end_menu())
            await update_user_ui(client, partner_id, "❌ Chat ended. Your partner disconnected.", end_menu())
