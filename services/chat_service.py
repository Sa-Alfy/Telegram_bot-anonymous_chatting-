import os
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
    except Exception as e:
        logger.debug(f"Mini-event notify failed for {user_id}: {e}")
        pass

async def relay_message(client: Client, message: Message):
    user_id = message.from_user.id
    partner_id = await match_state.get_partner(user_id)
    
    if partner_id:
        from core.behavior_engine import behavior_engine
        await behavior_engine.record_message_sent(user_id, message.text or "", sentiment_score=None) # Consider plugging in a real sentiment model later
        await behavior_engine.record_message_received(partner_id)
        
        # 1. VIP Media Filter Check
        if message.voice or message.video or message.video_note or message.audio:
            user = await UserRepository.get_by_telegram_id(user_id)
            if not user or not user.get("vip_status"):
                try:
                    await message.reply_text("❌ **Premium Feature**\nYou must be a **VIP Member** to send Voice Notes or Videos! Purchase a VIP Subscription from the Seasonal Shop.")
                except Exception as e:
                    logger.debug(f"Media filter alert failed for {user_id}: {e}")
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
                if partner_id >= 10**15:
                    from messenger_api import send_typing_on
                    u = await UserRepository.get_by_telegram_id(partner_id)
                    if u and u.get("username", "").startswith("msg_"):
                        send_typing_on(u["username"][4:])
                else:
                    await client.send_chat_action(partner_id, ChatAction.TYPING)
            except Exception as e:
                logger.debug(f"Typing indicator failed for {partner_id}: {e}")
                pass

            await asyncio.sleep(min(7.0, delay))

            # Relay the message cross-platform safely
            try:
                if partner_id >= 10**15:
                    # Partner is on Messenger
                    u = await UserRepository.get_by_telegram_id(partner_id)
                    if not u or not u.get("username", "").startswith("msg_"):
                        raise Exception("Failed to locate Messenger PSID for partner")
                    psid = u["username"][4:]
                    
                    # Media Relay Check (T -> M content)
                    if message.photo or message.sticker or message.video or message.animation:
                        logger.info(f"📤 Relaying media from TG:{user_id} to MSG:{partner_id}")
                        temp_path = await message.download()
                        try:
                            m_type = "image"
                            if message.video or message.animation: m_type = "video"
                            
                            from messenger_api import send_attachment_file
                            res = send_attachment_file(psid, temp_path, file_type=m_type)
                            if res and "error" in res:
                                logger.warning(f"⚠️ Messenger Media Upload Failed: {res['error']}")
                                await message.reply_text("⚠️ **Original content failed to deliver.** Sending description instead.")
                                # Fallback to text description below
                            else:
                                # Media sent! Now just send the caption if it exists
                                if message.caption:
                                    from messenger_api import send_message as msg_send
                                    msg_send(psid, f"💬 {message.caption}")
                                return
                        finally:
                            if temp_path and os.path.exists(temp_path):
                                os.remove(temp_path)

                    # Text/Fallback description relay
                    relay_text = message.text or message.caption
                    if not relay_text:
                        media_type = "file"
                        if message.photo: media_type = "photo 📸"
                        elif message.video or message.video_note: media_type = "video 🎥"
                        elif message.voice or message.audio: media_type = "voice note 🎤"
                        elif message.sticker: media_type = "sticker"
                        relay_text = f"📎 [Partner sent a {media_type}]"
                    elif message.photo or message.video or message.voice or message.audio or message.document:
                        relay_text = f"📎 [Media attachment]\n\n{relay_text}"
                        
                    from messenger_api import send_message as msg_send
                    res = msg_send(psid, f"💬 {relay_text}")
                    if res and "error" in res:
                        logger.warning(f"⚠️ Messenger Delivery Failed: {res['error']}")
                        await message.reply_text("⚠️ **Message failed to deliver.** Your partner's Messenger connection might be unstable.")
                    
                else:
                    # Partner is on Telegram
                    await message.copy(chat_id=partner_id)
                    
            except Exception as e:
                # Log the error but DO NOT DISCONNECT. 
                # Disconnecting on transient delivery errors is too aggressive and ruins UX.
                logger.warning(f"Resilient Relay: Failed to send to {partner_id}: {e}")
                try:
                    await message.reply_text("⚠️ **Delivery Error:** Your message couldn't be sent. Please try again.")
                except Exception as e_inner:
                    logger.debug(f"Error notification failed for {user_id}: {e_inner}")
                    pass

        except Exception as e:
            logger.error(f"Critical error in relay_message for {user_id}: {e}")
