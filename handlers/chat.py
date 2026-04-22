import time
import asyncio
from pyrogram import Client, filters
from pyrogram.types import Message

from state.match_state import match_state
from utils.rate_limiter import rate_limiter
from database.repositories.user_repository import UserRepository
from services.user_service import UserService
from services.matchmaking import MatchmakingService
from adapters.telegram.keyboards import bio_skip_menu, start_menu, end_menu, admin_menu, admin_vip_menu, admin_action_menu
from utils.logger import logger
from utils.helpers import update_user_ui
from config import ADMIN_ID
from database.repositories.report_repository import ReportRepository
from database.connection import db
from utils.content_filter import check_message, get_user_warning, SEVERITY_AUTO_BAN, SEVERITY_BLOCK

@Client.on_message(filters.regex(r"^🛑 Stop Chatting") & filters.private)
async def stop_button_handler(client: Client, message: Message):
    from handlers.actions.matching import MatchingHandler
    resp = await MatchingHandler.handle_stop(client, message.from_user.id)
    await update_user_ui(client, message.from_user.id, resp["text"], resp.get("reply_markup"))

@Client.on_message(filters.regex(r"^⏮ Next") & filters.private)
async def next_button_handler(client: Client, message: Message):
    from handlers.actions.matching import MatchingHandler
    resp = await MatchingHandler.handle_next(client, message.from_user.id)
    await update_user_ui(client, message.from_user.id, resp["text"], resp.get("reply_markup"))

@Client.on_message(filters.regex(r"^(👤|📊) My Stats") & filters.private)
async def stats_button_handler(client: Client, message: Message):
    from handlers.actions.stats import StatsHandler
    resp = await StatsHandler.handle_stats(client, message.from_user.id)
    await update_user_ui(client, message.from_user.id, resp["text"], resp.get("reply_markup"))

@Client.on_message(filters.regex(r"^ℹ️ Help") & filters.private)
async def help_button_handler(client: Client, message: Message):
    from handlers.callbacks import handle_help
    resp = await handle_help(client, message.from_user.id)
    await update_user_ui(client, message.from_user.id, resp["text"], resp.get("reply_markup"))

@Client.on_message(filters.regex(r"^🔍 Find Partner") & filters.private)
async def find_partner_button_handler(client: Client, message: Message):
    from handlers.actions.matching import MatchingHandler
    resp = await MatchingHandler.handle_search(client, message.from_user.id)
    await update_user_ui(client, message.from_user.id, resp["text"], resp.get("reply_markup"))

@Client.on_message(filters.regex(r"^🏆 Leaderboard") & filters.private)
async def leaderboard_button_handler(client: Client, message: Message):
    from handlers.actions.stats import StatsHandler
    resp = await StatsHandler.handle_leaderboard(client, message.from_user.id)
    await update_user_ui(client, message.from_user.id, resp["text"], resp.get("reply_markup"))

@Client.on_message(filters.regex(r"^🛍 Seasonal Shop") & filters.private)
async def seasonal_shop_button_handler(client: Client, message: Message):
    from handlers.actions.economy import EconomyHandler
    resp = await EconomyHandler.handle_seasonal_shop(client, message.from_user.id)
    await update_user_ui(client, message.from_user.id, resp["text"], resp.get("reply_markup"))

@Client.on_message(~filters.command(["start", "help", "stop", "next", "admin_stats", "stats", "leaderboard", "reveal", "priority", "find", "search", "match", "report", "terms", "privacy", "shop", "store", "profile", "account", "me"]) & 
                   ~filters.regex(r"^(🛑 Stop|⏮ Next|👤 My Stats|📊 My Stats|ℹ️ Help|🔍 Find Partner|🏆 Leaderboard|🛍 Seasonal Shop)") & 
                   filters.private)
async def chat_handler(client: Client, message: Message):
    user_id = message.from_user.id
    
    # 1. NEW: Message-level Invariant Recovery (Self-Healing)
    from services.distributed_state import distributed_state
    if not await distributed_state.validate_session(user_id, repair=True):
        await message.reply_text("⚠️ **Session inconsistency detected.**\nYou have been returned to the main menu.", reply_markup=start_menu())
        return

    now = time.time()
    
    # Check if muted for spamming
    mute_until = getattr(match_state, 'mute_until', {}).get(user_id, 0)
    if now < mute_until:
        return
        
    last_time = getattr(match_state, 'last_message_time', {}).get(user_id, 0)
    
    if not await rate_limiter.can_send_message(user_id):
        pass # The advanced spam tracker logic below will handle warnings
    
    # Advanced Rate limiting & Spam Tracking
    if now - last_time < 0.75:
        spam_count = match_state.spam_count.get(user_id, 0) + 1
        match_state.spam_count[user_id] = spam_count
        if spam_count == 3:
            await message.reply_text("⚠️ **Warning:** Please slow down! Sending messages too quickly will get you muted.")
            return
        elif spam_count >= 5:
            match_state.mute_until[user_id] = now + 15  # 15 second mute
            match_state.spam_count[user_id] = 0
            await message.reply_text("🚫 **You have been muted for 15 seconds for spamming.**")
            return
        return
    else:
        if match_state.spam_count.get(user_id, 0) > 0:
            match_state.spam_count[user_id] = 0

    match_state.last_message_time[user_id] = now

    # Update last active
    asyncio.create_task(UserRepository.update(user_id, last_active=int(now)))
    
    # Check if blocked
    user = await UserRepository.get_by_telegram_id(user_id)
    if not user:
        return
        
    state = await match_state.get_user_state(user_id)
    if user.get("is_blocked") and state != "awaiting_appeal":
        return

    # --- Onboarding / State Management ---
    if state:
        if state == "awaiting_interests":
            if message.text:
                interests = message.text[:100]
                await UserRepository.update(user_id, interests=interests)
                await match_state.set_user_state(user_id, "awaiting_location")
                from adapters.telegram.keyboards import location_skip_menu
                await message.reply_text(
                    f"✅ Interests saved!\n\n"
                    "📍 **Where are you from? (City/Country)**\n"
                    "(Or skip this step)",
                    reply_markup=location_skip_menu()
                )
            else:
                await message.reply_text("❌ Please send your interests as text.")
            return

        elif state == "awaiting_location":
            if message.text:
                location = message.text[:50]
                await UserRepository.update(user_id, location=location)
                await match_state.set_user_state(user_id, "awaiting_bio")
                await message.reply_text(
                    f"✅ Location set to **{location}**.\n\n📝 **Tell us a bit about yourself!**\n(Type a short bio in the chat below)",
                    reply_markup=bio_skip_menu()
                )
            else:
                await message.reply_text("❌ Please send your location as text.")
            return

        elif state == "awaiting_bio":
            if message.text:
                bio = message.text.replace('\x00', '')[:200]
                # Finalize profile
                await UserService.update_profile(
                    user_id, 
                    gender=user.get("gender", "Other"), 
                    location=user.get("location", "Secret"), 
                    bio=bio
                )
                await match_state.set_user_state(user_id, None)
                await message.reply_text(
                    "✅ **Profile Complete!**\nYou've unlocked XP and Coins.\n\n(Tip: Send a photo now to set your profile picture!)",
                    reply_markup=start_menu(False)
                )
            else:
                await message.reply_text("❌ Please send your bio as text.")
            return

        elif state == "awaiting_appeal":
            if message.text:
                await ReportRepository.create_appeal(user_id, message.text[:300])
                await match_state.set_user_state(user_id, None)
                await message.reply_text("✅ **Appeal Submitted!**\nAdmin will review your case soon. You can check your status with /start.")
            else:
                await message.reply_text("❌ Please send your appeal as text.")
            return

        elif state.startswith("awaiting_report_reason:"):
            target_id = int(state.split(":")[-1])
            reason = message.text.replace('\x00', '')[:300] if message.text else "No specific context provided."
            
            await match_state.set_user_state(user_id, None)
            stats = await MatchmakingService.disconnect(user_id)
            if stats:
                is_blocked = await UserService.report_user(user_id, target_id, reason)
                user = await UserRepository.get_by_telegram_id(user_id)
                await message.reply_text(f"🚨 **Report Sent.**\nReason: {reason}\n\n💰 **Your Balance:** {user['coins']} coins", reply_markup=end_menu())
            return

        elif state.startswith("awaiting_friend_msg:"):
            target_id = int(state.split(":")[-1])
            from database.repositories.friend_repository import FriendRepository
            from utils.helpers import send_cross_platform
            from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

            if not await FriendRepository.is_friend(user_id, target_id):
                await match_state.set_user_state(user_id, None)
                await message.reply_text("❌ Unauthorized: not a friend.", reply_markup=start_menu())
                return

            try:
                user_doc = await UserRepository.get_by_telegram_id(user_id)
                sender_name = user_doc.get("first_name", "A Friend") if user_doc else "A Friend"
                
                is_target_messenger = target_id >= 10**15
                
                # 1. Send the header notification cross-platform
                # Recipient sees a 'Reply' button that triggers handle_msg_friend back to sender
                reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton("⚡ Reply", callback_data=f"msg_friend_{user_id}")]])
                
                header_text = f"💌 **Private Message from {sender_name}:**"
                await send_cross_platform(client, target_id, header_text, reply_markup=reply_markup)
                
                # 2. Relay the actual content
                if is_target_messenger:
                    if message.text:
                        await send_cross_platform(client, target_id, message.text)
                    else:
                        await message.reply_text("⚠️ **Messenger Note:** Only text messages can be relayed to Messenger friends at this time.")
                else:
                    # Telegram to Telegram: Keep native copy support for photos/stickers
                    await message.copy(chat_id=target_id)
                
                # 3. Confirm to sender and KEEP state (Relay Mode)
                await message.reply_text(
                    "✅ **Relayed!**\nYou can send another message or click the button above to exit.",
                    # We repeat the cancel button to keep the UI clean
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🛑 Stop Relaying", callback_data="cancel_friend_msg")]])
                )
            except Exception as e:
                logger.error(f"Friend message relay failed: {e}")
                await message.reply_text("❌ Failed to relay message. They might have blocked the bot.", reply_markup=start_menu())
                await match_state.set_user_state(user_id, None)
            return

        # --- ADMIN UX STATES ---
        if str(user_id) == str(ADMIN_ID):
            if state.startswith("awaiting_unban_msg:"):
                target_id = int(state.split(":")[-1])
                unban_msg = message.text if message.text else "You have been unbanned by an admin. Welcome back!"
                await UserRepository.update(target_id, is_blocked=False)
                await match_state.set_user_state(user_id, None)
                from utils.helpers import send_cross_platform
                try:
                    await send_cross_platform(client, target_id, f"🔓 **UNBANNED**\n\n{unban_msg}")
                    await message.reply_text(f"✅ User `{target_id}` unbanned and notified.")
                except Exception as e:
                    logger.debug(f"Unban notify failed for {target_id}: {e}")
                    await message.reply_text(f"✅ User `{target_id}` unbanned, but notification failed.")
                return

            elif state == "awaiting_admin_broadcast":
                if message.text == "cancel":
                    await match_state.set_user_state(user_id, None)
                    return await message.reply_text("❌ Broadcast cancelled.", reply_markup=admin_menu())
                
                # Fetch all user IDs from UserRepository
                users = await db.fetchall("SELECT telegram_id FROM users")
                await message.reply_text(f"🚀 Broadcasting message to {len(users)} users...")
                
                count = 0
                for user in users:
                    uid = user['telegram_id']
                    try:
                        if message.text:
                            await client.send_message(uid, f"📢 **SYSTEM ANNOUNCEMENT**\n━━━━━━━━━━━━━━━━━━\n\n{message.text}")
                        else:
                            await message.copy(chat_id=uid)
                        count += 1
                        if count % 20 == 0: await asyncio.sleep(1)
                    except Exception as e:
                        logger.debug(f"Broadcast failed for {uid}: {e}")
                        pass
                
                await match_state.set_user_state(user_id, None)
                return await message.reply_text(f"✅ Success! Sent to {count} users.", reply_markup=admin_menu())

            elif state == "awaiting_gift_target":
                try:
                    target_id = int(message.text)
                    await match_state.set_user_state(user_id, f"awaiting_gift_amount:{target_id}")
                    return await message.reply_text(f"💰 **User ID:** `{target_id}`\nHow many coins do you want to gift?")
                except Exception as e:
                    logger.debug(f"Gift target error: {e}")
                    return await message.reply_text("❌ Invalid ID. Send only the numerical ID:")

            elif state.startswith("awaiting_gift_amount:"):
                target_id = int(state.split(":")[-1])
                try:
                    amount = int(message.text)
                    await UserService.add_coins(target_id, amount)
                    await match_state.set_user_state(user_id, None)
                    from utils.helpers import send_cross_platform
                    try: await send_cross_platform(client, target_id, f"🎁 **Admin gifted you {amount} coins!**")
                    except Exception as e:
                        logger.debug(f"Gift notify failed for {target_id}: {e}")
                        pass
                    return await message.reply_text(f"✅ Gifted **{amount} coins** to `{target_id}`.", reply_markup=admin_menu())
                except Exception as e:
                    logger.debug(f"Gift amount error: {e}")
                    return await message.reply_text("❌ Invalid amount. Send a number:")

            elif state == "awaiting_vip_target":
                try:
                    target_id = int(message.text)
                    await match_state.set_user_state(user_id, None)
                    return await message.reply_text(f"✨ **Managing VIP for:** `{target_id}`", reply_markup=admin_vip_menu(target_id))
                except Exception as e:
                    logger.debug(f"VIP target error: {e}")
                    return await message.reply_text("❌ Invalid ID.")

            elif state == "awaiting_manage_target":
                try:
                    target_id = int(message.text)
                    target_user = await UserRepository.get_by_telegram_id(target_id)
                    if not target_user: return await message.reply_text("❌ User not found.")
                    await match_state.set_user_state(user_id, None)
                    is_blocked = bool(target_user.get("is_blocked", 0))
                    return await message.reply_text(f"👤 **Managing User:** `{target_id}`", reply_markup=admin_action_menu(target_id, is_blocked))
                except Exception as e:
                    logger.debug(f"Manage target error: {e}")
                    return await message.reply_text("❌ Invalid ID.")

            elif state == "awaiting_deduct_target":
                try:
                    target_id = int(message.text)
                    await match_state.set_user_state(user_id, f"awaiting_deduct_amount:{target_id}")
                    return await message.reply_text(f"💸 **User ID:** `{target_id}`\nHow many coins do you want to take away?")
                except Exception as e:
                    logger.debug(f"Deduct target error: {e}")
                    return await message.reply_text("❌ Invalid ID.")

            elif state.startswith("awaiting_deduct_amount:"):
                target_id = int(state.split(":")[-1])
                try:
                    amount = int(message.text)
                    await UserRepository.increment_coins(target_id, -amount)
                    await match_state.set_user_state(user_id, None)
                    from utils.helpers import send_cross_platform
                    try: await send_cross_platform(client, target_id, f"💸 **Admin deducted {amount} coins from your balance.**")
                    except Exception as e:
                        logger.debug(f"Deduct notify failed for {target_id}: {e}")
                        pass
                    return await message.reply_text(f"✅ Successfully deducted **{amount} coins** from `{target_id}`.", reply_markup=admin_menu())
                except Exception as e:
                    logger.debug(f"Deduct amount error: {e}")
                    return await message.reply_text("❌ Invalid amount. Send a number:")

    # Handle Photo Upload for Profile (only when NOT in active chat)
    if message.photo:
        if not await match_state.is_in_chat(user_id):
            file_id = message.photo.file_id
            await UserRepository.update(user_id, profile_photo=file_id)
            await message.reply_text("📸 **Profile Photo Updated!**\nThis will be shown when you reveal your identity.")
            return

    # ═══════════════════════════════════════════════════════════════
    # UNIFIED ENGINE RELAY — All chat messages route through Engine
    # This ensures: single delivery path, telemetry, content filter
    # ═══════════════════════════════════════════════════════════════
    import app_state

    if await match_state.is_in_chat(user_id):
        # ── Text Messages ────────────────────────────────────────
        if message.text:
            result = await app_state.engine.process_event({
                "event_type": "SEND_MESSAGE",
                "user_id": str(user_id),
                "payload": {"text": message.text}
            })
            if result.get("success"):
                # Track milestones in background
                async def _track():
                    try:
                        milestone = await UserService.check_milestones(user_id, "messages_sent")
                        if milestone:
                            await client.send_message(user_id,
                                f"🎖 **Mini-Challenge Reached!**\n"
                                f"You've sent **{milestone['milestone']} messages**!\n"
                                f"🎁 **Reward:** +{milestone['reward_xp']} XP, +{milestone['reward_coins']} coins")
                    except Exception:
                        pass
                asyncio.create_task(_track())
                return
            else:
                error = result.get("error", "")
                if error:
                    await message.reply_text(f"⚠️ {error}")
                if result.get("terminated"):
                    await update_user_ui(client, user_id, "Your active session was terminated.", end_menu())
                return

        # ── Media Messages (photo, sticker, video, etc.) ─────────
        partner_id = await match_state.get_partner(user_id)
        if partner_id:
            from core.telemetry import EventLogger, TelemetryEvent

            # VIP Media Filter
            if message.voice or message.video or message.video_note or message.audio:
                if not user.get("vip_status"):
                    await message.reply_text("❌ **Premium Feature**\nYou must be a **VIP Member** to send Voice Notes or Videos!")
                    return

            try:
                is_messenger = isinstance(partner_id, int) and partner_id >= 10**15
                
                if is_messenger:
                    # TG → Messenger: Download and re-upload
                    from utils.platform_adapter import PlatformAdapter
                    import os
                    
                    if message.photo or message.sticker or message.video or message.animation:
                        temp_path = await message.download()
                        try:
                            m_type = "image"
                            if message.video or message.animation: m_type = "video"
                            from messenger_api import send_attachment_file
                            u = await UserRepository.get_by_telegram_id(partner_id)
                            if u and u.get("username", "").startswith("msg_"):
                                psid = u["username"][4:]
                                res = send_attachment_file(psid, temp_path, file_type=m_type)
                                if res and "error" in res:
                                    await message.reply_text("⚠️ **Media failed to deliver.** Sending description instead.")
                                else:
                                    if message.caption:
                                        from messenger_api import send_message as msg_send
                                        msg_send(psid, f"💬 {message.caption}")
                                    EventLogger.log_event(
                                        event="MEDIA_SENT", layer="message_relay", status=TelemetryEvent.SUCCESS,
                                        user_id=user_id, peer_id=partner_id, data={"type": m_type}
                                    )
                                    return
                        finally:
                            if temp_path and os.path.exists(temp_path):
                                os.remove(temp_path)
                    
                    # Text fallback for unsupported media
                    relay_text = message.text or message.caption or ""
                    if not relay_text:
                        media_type = "file"
                        if message.photo: media_type = "photo 📸"
                        elif message.video or message.video_note: media_type = "video 🎥"
                        elif message.voice or message.audio: media_type = "voice note 🎤"
                        elif message.sticker: media_type = "sticker"
                        relay_text = f"📎 [Partner sent a {media_type}]"

                    await PlatformAdapter.send_cross_platform(client, partner_id, f"💬 {relay_text}", None)
                    EventLogger.log_event(
                        event="MEDIA_SENT", layer="message_relay", status=TelemetryEvent.SUCCESS,
                        user_id=user_id, peer_id=partner_id, data={"type": "fallback_text"}
                    )
                else:
                    # TG → TG: Native copy (preserves formatting, stickers, etc.)
                    await message.copy(chat_id=partner_id)
                    EventLogger.log_event(
                        event="MEDIA_SENT", layer="message_relay", status=TelemetryEvent.SUCCESS,
                        user_id=user_id, peer_id=partner_id, data={"type": "native_copy"}
                    )
            except Exception as e:
                logger.warning(f"Media relay failed from {user_id} to {partner_id}: {e}")
                EventLogger.log_event(
                    event="MEDIA_FAILED", layer="message_relay", status=TelemetryEvent.FAIL,
                    user_id=user_id, peer_id=partner_id, data={"error": str(e)}
                )
                await message.reply_text("⚠️ **Delivery Error:** Your message couldn't be sent. Please try again.")
        return

    # ── Not in chat: ignore non-text silently ────────────────────
    # (User sent a random message but isn't in a chat session)
