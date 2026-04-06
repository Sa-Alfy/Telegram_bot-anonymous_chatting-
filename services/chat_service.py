from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.enums import ChatAction
import asyncio
import random
from state.memory import active_chats
from services.matchmaking import disconnect
from utils.keyboard import end_menu
from utils.helpers import update_user_ui
from services.user_service import get_user_profile
from state.persistence import save_profiles
from utils.logger import logger
from services.event_manager import get_active_event
import time

async def trigger_mini_event(client: Client, user_id: int):
    """Triggers a random mini-event for a user during chat."""
    profile = get_user_profile(user_id)
    now = int(time.time())
    
    # Cooldown of 5 minutes between events
    if now - profile.get("last_event_time", 0) < 300:
        return
    
    # 5% chance per message
    if random.random() > 0.05:
        return
        
    events = [
        {"name": "Lucky Coin Bonus", "msg": "💰 **Lucky Coin Bonus!**\nYou found some extra coins during the chat: **+3 Coins!**", "coins": 3, "xp": 0},
        {"name": "XP Boost", "msg": "📈 **XP Boost!**\nYou earned a quick XP boost from this interaction: **+5 XP!**", "coins": 0, "xp": 5}
    ]
    
    event = random.choice(events)
    profile["coins"] += event["coins"]
    profile["xp"] += event["xp"]
    profile["last_event_time"] = now
    profile["mini_events_triggered"].append({
        "event": event["name"],
        "time": now
    })
    
    asyncio.create_task(save_profiles())
    
    try:
        await client.send_message(user_id, event["msg"])
    except Exception:
        pass

async def relay_message(client: Client, message: Message):
    user_id = message.from_user.id
    
    if user_id in active_chats:
        partner_id = active_chats[user_id]
        
        # DEBUG ECHO LOGIC (Phase 11)
        if partner_id == 1:
            await message.reply_text(f"💬 **Echo Partner:** {message.text or '[Media]'}")
            return

        try:
            # Step 4: Daily Challenge (messages sent)
            from services.user_service import increment_daily_challenge
            res = increment_daily_challenge(user_id, "messages_sent")
            if res:
                await client.send_message(user_id, res)

            # Step 2: Trigger Mini-Event
            asyncio.create_task(trigger_mini_event(client, user_id))

            active_event = get_active_event()
            
            # Step 8: Randomized Typing Styles (Enhanced with Events)
            style = random.choice(["fast", "slow", "thoughtful", "normal"])
            if active_event["id"] and active_event["type"] == "mini":
                # Special "Frenzy" style during events
                style = "fast"
                
            base_delay = len(message.text or "") / 20
            
            if style == "fast":
                delay = base_delay * 0.4 + 0.2
                action = ChatAction.TYPING
            elif style == "slow":
                delay = base_delay * 1.5 + 2.0
                action = ChatAction.TYPING
            elif style == "thoughtful":
                await asyncio.sleep(random.uniform(1.0, 2.5))
                delay = base_delay + 0.5
                action = ChatAction.TYPING
            else: # normal
                delay = base_delay + 0.8
                action = ChatAction.TYPING
            
            # Matchmaking Event header (Optional: could add [EVENT] prefix)
            
            await client.send_chat_action(partner_id, action)
            await asyncio.sleep(min(7.0, delay))

            # We use copy_message so there is no "Forwarded from" tag
            await message.copy(chat_id=partner_id)
            
            # Track reactions logic (Step 3 will handle the actual reaction, but here we could log history if needed)
            # Actually, Step 3 is about reacting to a message.
        except Exception as e:
            logger.warning(f"Failed to relay message from {user_id} to {partner_id}: {e}")
            # If sending fails (e.g. user blocked the bot), gracefully disconnect
            await disconnect(user_id)
            await update_user_ui(
                client, user_id,
                "❌ Chat ended due to an error.", end_menu()
            )
            await update_user_ui(
                client, partner_id,
                "❌ Chat ended. Your partner disconnected.", end_menu()
            )
    else:
        # User not in chat, can be ignored.
        pass
