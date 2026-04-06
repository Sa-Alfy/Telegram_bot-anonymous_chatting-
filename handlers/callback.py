from pyrogram import Client, filters
from pyrogram.types import CallbackQuery
from services.matchmaking import add_to_queue, add_priority_to_queue, remove_from_queue, find_partner, disconnect
from services.user_service import report_user, get_coins, deduct_coins, update_last_active, get_user_profile
from state.persistence import save_profiles
from state.memory import user_ui_messages, user_cooldowns, active_chats, waiting_queue, searching_users, rematch_requests, queue_lock, chat_start_times
from utils.keyboard import search_menu, chat_menu, end_menu, start_menu, confirm_reveal_menu
from utils.helpers import update_user_ui
from handlers.start import get_start_text
from handlers.stats import get_stats_text, get_leaderboard_text
from utils.logger import logger
import asyncio
import time
import random
from services.economy_service import get_dynamic_cost, buy_shop_item
from services.event_manager import get_active_event, add_event_points

async def matching_animation(client: Client, user_id: int):
    """Updates searching message with animations while user is in queue."""
    from utils.keyboard import search_menu
    
    if user_id in searching_users:
        return
    
    searching_users.add(user_id)
    
    hour = time.localtime().tm_hour
    is_day = 6 <= hour < 18
    
    if is_day:
        msgs = [
            "☀️ Plenty of people awake! Finding one...",
            "☕ Sip some coffee, matching soon...",
            "🔎 Filtering through the crowd...",
            "📡 Scanning for active users...",
            "🤝 Connecting you soon...",
            "🛰 Looking for available partners...",
            "🌊 Sifting through the sea of users...",
            "🏃 Day-dwellers are busy! Squeezing you in...",
            "🏙 Searching the city for a match..."
        ]
    else:
        msgs = [
            "🌙 It's late! Looking for a night owl...",
            "✨ Stars are bright, match found soon...",
            "🌘 Dimming the lights, sifting through the night...",
            "🦉 Finding another owl to chat with...",
            "🤝 Connecting you soon...",
            "🌌 Looking through the late-night stars...",
            "🕯 Searching for a midnight companion...",
            "🔭 Scanning the night sky for partners...",
            "🌃 The night is young! Finding a match..."
        ]
    
    while user_id in waiting_queue and user_id not in active_chats:
        try:
            await asyncio.sleep(4)
            if user_id not in waiting_queue or user_id in active_chats:
                break
                
            await update_user_ui(
                client, user_id,
                random.choice(msgs),
                search_menu()
            )
        except Exception:
            break
            
    searching_users.discard(user_id)

def get_progression_text(stats: dict, is_user1: bool) -> str:
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

def get_milestone_text(user_id: int, type: str) -> str:
    """Checks for milestones and returns notification text."""
    from services.user_service import check_milestone, add_xp, add_coins
    milestone = check_milestone(user_id, type)
    if milestone:
        m = milestone['milestone']
        xp = milestone['reward_xp']
        coins = milestone['reward_coins']
        add_xp(user_id, xp)
        add_coins(user_id, coins)
        return f"\n\n🎖 **Mini-Challenge Reached!**\nYou've completed **{m} {type.replace('_', ' ')}**!\n🎁 **Reward:** +{xp} XP, +{coins} coins"
    return ""

def get_session_rank(user_id: int) -> str:
    """Calculates approximate daily rank for motivation."""
    from state.persistence import user_profiles
    # Simplified: Rank based on total_xp_earned today (or total if not available)
    sorted_profiles = sorted(user_profiles.items(), key=lambda x: x[1].get("total_xp_earned", 0), reverse=True)
    
    try:
        rank = next(i for i, (uid, p) in enumerate(sorted_profiles) if uid == user_id) + 1
        if rank <= 10:
            return f"🔥 **Rank:** Top {rank} active users this hour!"
        return f"📊 **Session Rank:** #{rank} globally"
    except StopIteration:
        return ""

def format_session_summary(stats: dict, is_user1: bool, coins_balance: int) -> str:
    """Creates a beautiful, animated-style summary text."""
    duration = stats.get('duration_minutes', 0)
    
    # Use user-specific rewards from stats (Step 6)
    earned = stats.get('coins_earned', 0) if is_user1 else stats.get('u2_coins_earned', 0)
    xp = stats.get('xp_earned', 0) if is_user1 else stats.get('u2_xp_earned', 0)
    event_points = stats.get('event_points', 0) if is_user1 else stats.get('u2_event_points', 0)
    reactions = stats.get('u1_reactions', 0) if is_user1 else stats.get('u2_reactions', 0)
    
    active_event = get_active_event()
    event_text = ""
    if event_points > 0:
        event_text = f"🏆 **{active_event['name']} Points:** +{event_points}\n"
    
    header = "✨ **Chat Session Summary** ✨"
    
    summary = (
        f"{header}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"⌛ **Duration:** {duration} min\n"
    )
    
    if reactions > 0:
        summary += f"🎭 **Reactions Received:** {reactions}\n"
        
    summary += (
        f"💰 **Coins:** +{earned}\n"
        f"📈 **XP Gained:** +{xp}\n"
        f"{event_text}"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"💰 **Total Balance:** {coins_balance} coins"
    )
    
    # Daily Challenge Progress (Step 4/6)
    user_id = stats.get('user_id') if is_user1 else stats.get('partner_id')
    if user_id:
        profile = get_user_profile(user_id)
        challenge = profile.get("daily_challenge", {})
        if not challenge.get("completed"):
            m = challenge.get("matches_completed", 0)
            ms = challenge.get("messages_sent", 0)
            summary += f"\n\n📅 **Daily Challenge:** {min(5, m)}/5 matches, {min(50, ms)}/50 msgs"
        else:
            summary += f"\n\n📅 **Daily Challenge:** ✅ Completed!"

    # Progress notifications (Level up, Achievements)
    summary += get_progression_text(stats, is_user1)
    
    # Session Rank
    if user_id:
        rank_text = get_session_rank(user_id)
        if rank_text:
            summary += f"\n\n{rank_text}"
        
    return summary

COOLDOWN_SECONDS = 0.5

@Client.on_callback_query()
async def on_callback(client: Client, query: CallbackQuery):
    user_id = query.from_user.id
    data = query.data
    now = time.time()

    try:
        # Rate limiting
        if user_id in user_cooldowns:
            if now - user_cooldowns[user_id] < COOLDOWN_SECONDS:
                await query.answer("Please wait...", show_alert=False)
                return
        user_cooldowns[user_id] = now
    
    # Update last active
    update_last_active(user_id)

    # Ensure UI message tracking
    if query.message:
        user_ui_messages[user_id] = query.message.id

    if data == "help":
        await query.answer("Click Find Partner to connect to a stranger anonymously.", show_alert=True)
        return

    if data == "search":
        await query.edit_message_text(
            text="⏳ Searching for a partner...",
            reply_markup=search_menu()
        )
        
        # Phase 5: Event Multipliers match start
        active_event = get_active_event()
        if active_event["id"]:
            await query.answer(f"📅 Event Active: {active_event['name']}!", show_alert=False)

        success = await add_to_queue(user_id)
        if not success:
            await query.answer("You are already in a chat!")
            return
            
        asyncio.create_task(matching_animation(client, user_id))
            
        partner_id = await find_partner(user_id)
        if partner_id is not None:
            # Check for milestones
            u1_milestone = get_milestone_text(user_id, "matches_completed")
            u2_milestone = get_milestone_text(partner_id, "matches_completed")
            
            await update_user_ui(
                client, user_id, 
                f"💬 You are now chatting with a stranger...{u1_milestone}", chat_menu()
            )
            await update_user_ui(
                client, partner_id, 
                f"💬 You are now chatting with a stranger...{u2_milestone}", chat_menu()
            )
        else:
            await query.answer("Added to queue.")

    elif data == "priority_search":
        profile = get_user_profile(user_id)
        timed_pack = profile.get("priority_pack", {})
        is_timed_active = timed_pack.get("active") and timed_pack.get("expires_at", 0) > time.time()
        has_matches = profile.get("priority_matches", 0) > 0
        
        if is_timed_active or has_matches or deduct_coins(user_id, 5):
            if is_timed_active:
                await query.answer("⚡ Using your Unlimited Priority Pack!", show_alert=False)
            elif has_matches:
                profile["priority_matches"] -= 1
                asyncio.create_task(save_profiles())
                await query.answer("⚡ Using 1 Priority Match from your pack!")
            
            await add_priority_to_queue(user_id)
            partner_id = await find_partner(user_id)
            if partner_id:
                u1_milestone = get_milestone_text(user_id, "matches_completed")
                u2_milestone = get_milestone_text(partner_id, "matches_completed")
                await update_user_ui(
                    client, user_id, 
                    f"⚡ **Priority Match Found!**\n💬 You are now chatting with a stranger...{u1_milestone}", chat_menu()
                )
                await update_user_ui(
                    client, partner_id, 
                    f"💬 You are now chatting with a stranger...{u2_milestone}", chat_menu()
                )
            else:
                await query.answer("⚡ Priority activated! You are at the front of the queue.", show_alert=True)
                asyncio.create_task(matching_animation(client, user_id))
        else:
            await query.answer("❌ Not enough coins for Priority Match (5 coins required)!", show_alert=True)

    elif data == "priority_packs":
        from utils.keyboard import priority_pack_menu
        await query.edit_message_text(
            text="💎 **Priority Match Packs**\n\nBuy packs to skip the queue anytime! One pack use = Top of queue.",
            reply_markup=priority_pack_menu()
        )

    elif data.startswith("buy_pack_"):
        count = int(data.split("_")[-1])
        prices = {5: 20, 15: 50, 50: 150}
        price = prices.get(count, 999)
        
        if deduct_coins(user_id, price):
            profile = get_user_profile(user_id)
            profile["priority_matches"] += count
            asyncio.create_task(save_profiles())
            await query.answer(f"✅ Purchased {count} Priority Matches!", show_alert=True)
            await query.edit_message_text(
                text=get_start_text(get_coins(user_id)),
                reply_markup=start_menu()
            )
        else:
            await query.answer("❌ Not enough coins!", show_alert=True)

    elif data.startswith("buy_timed_priority_"):
        hours = int(data.split("_")[-1])
        prices = {1: 30, 3: 75, 24: 200}
        price = prices.get(hours, 999)
        
        if deduct_coins(user_id, price):
            profile = get_user_profile(user_id)
            profile["priority_pack"] = {
                "active": True,
                "expires_at": int(time.time()) + (hours * 3600)
            }
            asyncio.create_task(save_profiles())
            await query.answer(f"✅ Activated {hours}h Unlimited Priority!", show_alert=True)
            await query.edit_message_text(
                text="⏳ Searching for a partner...",
                reply_markup=search_menu()
            )
            await add_priority_to_queue(user_id)
            asyncio.create_task(matching_animation(client, user_id))
            await find_partner(user_id)
        else:
            await query.answer("❌ Not enough coins!", show_alert=True)

    elif data == "booster_menu":
        from utils.keyboard import booster_menu
        await query.edit_message_text(
            text="🚀 **Coin Booster Packs**\n\nDouble your session rewards (XP & Coins) for a limited time!",
            reply_markup=booster_menu()
        )

    elif data.startswith("buy_booster_"):
        hours = int(data.split("_")[-1])
        price = 50
        if deduct_coins(user_id, price):
            profile = get_user_profile(user_id)
            profile["coin_booster"] = {
                "active": True,
                "expires_at": int(time.time()) + (hours * 3600)
            }
            asyncio.create_task(save_profiles())
            await query.answer(f"✅ Activated {hours}h Coin Booster (2x Rewards)!", show_alert=True)
            await query.edit_message_text(
                text=get_start_text(get_coins(user_id)),
                reply_markup=start_menu()
            )
        else:
            await query.answer("❌ Not enough coins!", show_alert=True)

    elif data == "cancel_search":
        await remove_from_queue(user_id)
        coins = get_coins(user_id)
        await query.edit_message_text(
            text=get_start_text(coins),
            reply_markup=start_menu()
        )

    elif data == "add_friend":
        if user_id not in active_chats:
            await query.answer("❌ You are not in a chat!", show_alert=True)
            return
            
        partner_id = active_chats[user_id]
        profile = get_user_profile(user_id)
        
        # Avoid self-adding (echo partner)
        if partner_id == 1:
            await query.answer("🤖 This is a bot, focus on finding real people!")
            return
            
        if partner_id in profile.get("friends", []):
            await query.answer("📝 Already in your friends list!", show_alert=True)
            return
            
        profile["friends"].append(partner_id)
        asyncio.create_task(save_profiles())
        
        await query.answer("💌 Partner added to your anonymous friends list!", show_alert=True)
        try:
            await client.send_message(partner_id, "✨ **Someone added you as a friend!**\nYou're making a great impression.")
        except Exception:
            pass

    elif data == "stop":
        stats = await disconnect(user_id)
        coins = get_coins(user_id)
        
        if stats:
            partner_id = stats['partner_id']
            # Store for rematch (Step 3)
            p1 = get_user_profile(user_id)
            p2 = get_user_profile(partner_id)
            p1["last_partner_id"] = partner_id
            p2["last_partner_id"] = user_id
            p1["rematch_available"] = True
            p2["rematch_available"] = True
            asyncio.create_task(save_profiles())

            # Insert user_id into stats for formatting
            stats['user_id'] = user_id
            text = format_session_summary(stats, True, coins)
            await query.edit_message_text(text=text, reply_markup=end_menu(can_rematch=True))
            
            partner_id = stats['partner_id']
            partner_coins = get_coins(partner_id)
            partner_text = f"❌ **Chat ended by stranger**\n" + format_session_summary(stats, False, partner_coins)
            await update_user_ui(
                client, partner_id, partner_text, end_menu(can_rematch=True)
            )
        else:
            await query.edit_message_text(
                text=f"❌ Chat ended\n\n💰 **Your Balance:** {coins} coins",
                reply_markup=end_menu()
            )

    elif data == "next":
        stats = await disconnect(user_id)
        if stats:
            partner_id = stats['partner_id']
            # Store for rematch (Step 3)
            p1 = get_user_profile(user_id)
            p2 = get_user_profile(partner_id)
            p1["last_partner_id"] = partner_id
            p2["last_partner_id"] = user_id
            p1["rematch_available"] = True
            p2["rematch_available"] = True
            asyncio.create_task(save_profiles())

            stats['user_id'] = user_id
            partner_id = stats['partner_id']
            partner_coins = get_coins(partner_id)
            partner_text = f"❌ **Chat ended by stranger**\n" + format_session_summary(stats, False, partner_coins)
            await update_user_ui(
                client, partner_id, partner_text, end_menu(can_rematch=True)
            )
            
        await query.edit_message_text(
            text="⏳ Searching for a partner...",
            reply_markup=search_menu()
        )
        await add_to_queue(user_id)
        asyncio.create_task(matching_animation(client, user_id))
        
        new_partner = await find_partner(user_id)
        if new_partner:
            u1_milestone = get_milestone_text(user_id, "matches_completed")
            u2_milestone = get_milestone_text(new_partner, "matches_completed")
            await update_user_ui(
                client, user_id,
                f"💬 You are now chatting with a stranger...{u1_milestone}", chat_menu()
            )
            await update_user_ui(
                client, new_partner,
                f"💬 You are now chatting with a stranger...{u2_milestone}", chat_menu()
            )

    elif data == "report":
        stats = await disconnect(user_id)
        if stats:
            partner_id = stats['partner_id']
            is_blocked = report_user(partner_id)
            partner_coins = get_coins(partner_id)
            partner_text = (
                ("❌ You have been disconnected and reported." if not is_blocked else "❌ You have been blocked from the bot.") + 
                f"\n⏱ Spent: {stats['duration_minutes']} min\n💰 Earned: {stats['coins_earned']}\n\n💰 **Balance:** {partner_coins} coins"
            )
            partner_text += get_progression_text(stats, False)
            await update_user_ui(
                client, partner_id, partner_text, end_menu(can_rematch=True)
            )

    elif data == "rematch":
        profile = get_user_profile(user_id)
        partner_id = profile.get("last_partner_id", 0)
        
        if not partner_id or not profile.get("rematch_available"):
            await query.answer("❌ Rematch no longer available!", show_alert=True)
            return
            
        if user_id in active_chats:
            await query.answer("❌ You are already in a chat!")
            return
            
        if not deduct_coins(user_id, 1):
            await query.answer("❌ Not enough coins (1 required)!", show_alert=True)
            return
            
        rematch_requests[user_id] = partner_id
        
        # Check if partner also wants a rematch and is available
        if rematch_requests.get(partner_id) == user_id:
            if partner_id in active_chats:
                await query.answer("😔 Partner already joined another chat.", show_alert=True)
                return
                
            async with queue_lock:
                active_chats[user_id] = partner_id
                active_chats[partner_id] = user_id
                chat_start_times[user_id] = time.time()
                chat_start_times[partner_id] = time.time()
                
                # Clear rematch data
                profile["rematch_available"] = False
                get_user_profile(partner_id)["rematch_available"] = False
                if user_id in rematch_requests: del rematch_requests[user_id]
                if partner_id in rematch_requests: del rematch_requests[partner_id]

            await update_user_ui(client, user_id, "🔄 **Rematch Successful!**\n💬 Reconnected with partner...", chat_menu())
            await update_user_ui(client, partner_id, "🔄 **Rematch Successful!**\n💬 Reconnected with partner...", chat_menu())
        else:
            await query.answer("🔄 Rematch requested! Waiting for partner...", show_alert=True)
            try:
                await client.send_message(partner_id, "🔄 **Your last partner wants a rematch!**\nClick 'Rematch' in your summary to reconnect.")
            except:
                pass
            
        coins = get_coins(user_id)
        await query.edit_message_text(
            text=f"🚨 User reported. Chat ended.\n\n💰 **Your Balance:** {coins} coins",
            reply_markup=end_menu()
        )

    elif data == "reveal":
        partner_id = active_chats.get(user_id)
        if not partner_id:
            await query.answer("❌ Partner disconnected!", show_alert=True)
            return

        # Tiered pricing calculation (Step 4 & Economy 2.0)
        from services.economy_service import get_dynamic_cost
        cost = get_dynamic_cost(user_id, "identity_reveal", partner_id)
        
        p_profile = get_user_profile(partner_id)
        p_level = p_profile.get("level", 1)
        p_vip = p_profile.get("vip", False)
        
        if get_coins(user_id) < cost:
            await query.answer(f"❌ You need {cost} coins to reveal this partner's identity!", show_alert=True)
            return
        
        from utils.keyboard import confirm_reveal_menu
        await query.edit_message_text(
            text=f"👤 **Identity Reveal**\n\nThis will reveal your name to your partner for **{cost} coins**.\n"
                 f"(Cost based on partner's Level {p_level}{' + VIP' if p_vip else ''})\n\nContinue?",
            reply_markup=confirm_reveal_menu(cost) # Pass cost to keyboard
        )

    elif data == "peek":
        from utils.keyboard import peek_menu
        await query.edit_message_text(
            text="🔍 **Peek Stats**\n\nShow a hint about your partner's profile for 5 coins.",
            reply_markup=peek_menu()
        )

    elif data.startswith("peek_"):
        if deduct_coins(user_id, 5):
            partner_id = active_chats.get(user_id)
            if not partner_id:
                await query.answer("❌ Partner disconnected!")
                return
            
            p_profile = get_user_profile(partner_id)
            peek_type = data.split("_")[-1]
            
            if peek_type == "streak":
                val = p_profile.get("daily_streak", 0)
                msg = f"🔥 **Partner's Streak:** {val} days"
            else:
                val = p_profile.get("level", 1)
                msg = f"📈 **Partner's Level:** Lv. {val}"
            
            await query.answer(msg, show_alert=True)
            await query.edit_message_text(
                text=f"💬 {msg}\n\nChatting with a stranger...",
                reply_markup=chat_menu()
            )
        else:
            await query.answer("❌ Not enough coins!", show_alert=True)

    elif data.startswith("confirm_reveal"):
        if user_id not in active_chats:
            await query.answer("❌ You are not in a chat!")
            await query.edit_message_text(text="❌ Chat ended", reply_markup=end_menu())
            return

        # Extract cost if provided, otherwise default to 15
        try:
            cost = int(data.split("_")[-1]) if "_" in data else 15
        except:
            cost = 15

        if deduct_coins(user_id, cost):
            profile = get_user_profile(user_id)
            profile["revealed"] = True
            
            partner_id = active_chats[user_id]
            first_name = query.from_user.first_name
            
            await query.edit_message_text(
                text=f"✅ You revealed your identity as **{first_name}**. (-{cost} coins)",
                reply_markup=chat_menu()
            )
            
            if partner_id != 1:
                try:
                    await client.send_message(
                        chat_id=partner_id,
                        text=f"👤 **Your partner revealed their identity:** {first_name}"
                    )
                except Exception as e:
                    logger.warning(f"Failed to send reveal message to partner {partner_id}: {e}")
            else:
                # For Echo Partner, we can just echo it back or ignore
                await query.answer("Reveal echoed to debug partner.")
        else:
            await query.answer("❌ Not enough coins!", show_alert=True)
            await query.edit_message_text(
                text="💬 You are now chatting with a stranger...",
                reply_markup=chat_menu()
            )

    elif data.startswith("lb_"):
        f_type = data.split("_")[-1]
        await query.edit_message_text(
            text=get_leaderboard_text(f_type),
            reply_markup=leaderboard_menu()
        )

    elif data == "cancel_reveal":
        await query.edit_message_text(
            text="💬 You are now chatting with a stranger...",
            reply_markup=chat_menu()
        )

    elif data == "stats":
        await query.edit_message_text(
            text=get_stats_text(user_id),
            reply_markup=start_menu()
        )

    elif data == "open_reactions":
        from utils.keyboard import reaction_menu
        await query.edit_message_reply_markup(reply_markup=reaction_menu())

    elif data == "back_to_chat":
        await query.edit_message_reply_markup(reply_markup=chat_menu())

    elif data.startswith("react_"):
        emoji_map = {
            "heart": "❤️", "joy": "😂", "wow": "😮", "sad": "😢", "up": "👍"
        }
        emoji_key = data.split("_")[1]
        emoji = emoji_map.get(emoji_key, "❓")
        
        partner_id = active_chats.get(user_id)
        if not partner_id:
            await query.answer("❌ Partner disconnected!")
            return
            
        # Log in history
        profile = get_user_profile(user_id)
        profile["reaction_history"].append({
            "to": partner_id,
            "emoji": emoji,
            "time": int(time.time())
        })
        asyncio.create_task(save_profiles())
        
        # Track for session bonus (Step 6)
        p_profile = get_user_profile(partner_id)
        if "reaction_notifications" not in p_profile:
            p_profile["reaction_notifications"] = []
        p_profile["reaction_notifications"].append(emoji)
        
        # Notify partner
        try:
            if partner_id != 1:
                await client.send_message(partner_id, f"🎭 **Partner reacted:** {emoji}")
            await query.answer(f"Sent {emoji}!")
        except Exception:
            await query.answer("Failed to send reaction.")

    elif data == "seasonal_shop":
        from utils.keyboard import seasonal_shop_menu
        await query.edit_message_text(
            text="🛍 **Seasonal Coin Shop**\n\nSpend your hard-earned coins on boosters and exclusive badges!",
            reply_markup=seasonal_shop_menu()
        )

    elif data.startswith("buy_shop_"):
        item_key = data.replace("buy_shop_", "")
        res = await buy_shop_item(user_id, item_key)
        await query.answer(res["message"], show_alert=True)
        if res["success"]:
            await query.edit_message_text(
                text=get_stats_text(user_id),
                reply_markup=start_menu()
            )

    elif data == "event_leaderboard":
        from utils.keyboard import event_leaderboard_menu
        await query.edit_message_text(
            text="📅 **Event Competition**\n\nTrack the top players in the current tournament!",
            reply_markup=event_leaderboard_menu()
        )

    elif data == "lb_event":
        await query.edit_message_text(
            text=get_leaderboard_text("event"),
            reply_markup=leaderboard_menu()
        )

    elif data == "leaderboard":
        await query.edit_message_text(
            text=get_leaderboard_text(),
            reply_markup=start_menu()
        )

    except Exception as e:
        from pyrogram.errors import MessageNotModified
        if isinstance(e, MessageNotModified):
            pass # Ignore if content hasn't changed
        else:
            logger.error(f"Error in on_callback: {e}")
