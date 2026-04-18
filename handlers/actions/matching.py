import asyncio
import time
from typing import Dict, Any, Optional
from utils.rate_limiter import rate_limiter
from pyrogram import Client, types
from services.matchmaking import MatchmakingService
from state.match_state import match_state
from utils.keyboard import search_menu, chat_menu, end_menu, start_menu
from utils.helpers import update_user_ui
from handlers.start import get_start_text
from services.user_service import UserService
from utils.keyboard import retry_search_menu
from state.match_state import UserState
from utils.ui_formatters import format_session_summary, get_match_found_text
from services.distributed_state import distributed_state


def _fire(coro):
    """Schedule a coroutine as a background task with exception logging."""
    async def _safe():
        try:
            await coro
        except Exception as e:
            from utils.logger import logger
            logger.error(f"Background task failed: {e}")
    asyncio.create_task(_safe())


class MatchingHandler:
    @staticmethod
    async def handle_search(client: Client, user_id: int) -> Dict[str, Any]:
        """Prompts the user for their matchmaking preferences."""
        if not await rate_limiter.can_matchmake(user_id, update=False):
            remaining = await rate_limiter.get_cooldown_remaining(user_id, "matchmake") or 0
            return {
                "text": f"⏳ **Please slow down!**\nWait {remaining:.1f}s before opening choices again.",
                "reply_markup": retry_search_menu(UserState.HOME)
            }
            
        from utils.keyboard import search_pref_menu
        return {
            "text": "🔍 **Matchmaking Preferences**\n\nWho are you looking for today?",
            "reply_markup": search_pref_menu()
        }

    @staticmethod
    async def handle_search_with_pref(client: Client, user_id: int, pref: str) -> Dict[str, Any]:
        """Starts searching for a partner with explicit filters."""
        if not await rate_limiter.can_matchmake(user_id):
            remaining = await rate_limiter.get_cooldown_remaining(user_id, "matchmake") or 0
            return {
                "text": f"⏳ **Cooldown Active**\n\nPlease wait {remaining:.1f}s between searches.",
                "reply_markup": retry_search_menu(UserState.HOME)
            }
            
        # Check if they need to pay for filters
        from services.user_service import UserService
        from database.repositories.user_repository import UserRepository
        
        user = await UserRepository.get_by_telegram_id(user_id)
        if pref in ["Male", "Female"]:
            is_vip = user.get("vip_status", 0)
            if not is_vip:
                if user.get("coins", 0) < 15:
                    return {"alert": "❌ Gender filters cost 15 coins for non-VIPs!", "show_alert": True}
                await UserService.deduct_coins(user_id, 15)
                
        # Priority check handles passing 'Priority' intent
        is_priority = (pref == "Priority")
        if is_priority:
            pref = "Any" # Reset actual core filter to Any for priority
            if user.get("coins", 0) < 5:
                # If they have priority packs it's handled in the service, but if they click the 5 coin button directly:
                if not user.get("priority_pack", {}).get("active") and user.get("priority_matches", 0) <= 0:
                    if not await UserService.deduct_coins(user_id, 5):
                        return {"alert": "❌ Not enough coins!", "show_alert": True}

        success = await MatchmakingService.add_to_queue(user_id, gender_pref=pref)
        if not success:
            return {"alert": "You are already in a chat!", "show_alert": True}
        
        partner_id = await MatchmakingService.find_partner(client, user_id)
        if partner_id:
            now = time.time()
            # Safety logic: Only show full warning once every 24 hours
            user_last_safety = user.get("safety_last_seen", 0)
            show_safety = (now - user_last_safety > 86400)
            
            if show_safety:
                _fire(UserRepository.update(user_id, safety_last_seen=int(now)))
            
            match_text = get_match_found_text(include_safety=show_safety)
            
            # For partner, check their status too
            partner_user = await UserRepository.get_by_telegram_id(partner_id)
            p_last_safety = partner_user.get("safety_last_seen", 0) if partner_user else 0
            p_show_safety = (now - p_last_safety > 86400)
            if p_show_safety:
                _fire(UserRepository.update(partner_id, safety_last_seen=int(now)))
            
            p_match_text = get_match_found_text(include_safety=p_show_safety)

            return {
                "text": match_text,
                "reply_markup": chat_menu(),
                "partner_msg": {
                    "target_id": partner_id,
                    "text": p_match_text,
                    "reply_markup": chat_menu()
                }
            }
            
        from utils.keyboard import search_menu
        return {
            "text": f"⏳ Searching for a partner...\n**Filter:** {pref}",
            "reply_markup": search_menu(),
            "start_animation": True
        }

    @staticmethod
    async def handle_cancel(client: Client, user_id: int) -> Dict[str, Any]:
        """Cancels the search."""
        await MatchmakingService.remove_from_queue(user_id)
        from database.repositories.user_repository import UserRepository
        user = await UserRepository.get_by_telegram_id(user_id)
        coins = user.get("coins", 0)
        is_guest = user.get("is_guest", 1)
        
        return {
            "text": get_start_text(coins, is_guest),
            "reply_markup": start_menu(is_guest)
        }

    @staticmethod
    async def handle_stop(client: Client, user_id: int) -> Dict[str, Any]:
        """Disconnects from current chat."""
        stats = await MatchmakingService.disconnect(user_id)
        if not stats:
            return {"text": "❌ Chat ended.", "reply_markup": end_menu()}
            
        partner_id = stats["partner_id"]
        
        # Build proper session summary for the user who clicked Stop
        from database.repositories.user_repository import UserRepository
        user = await UserRepository.get_by_telegram_id(user_id)
        user_coins = user.get("coins", 0) if user else 0
        
        # Inject total_xp for progress bar
        stats["total_xp"] = user.get("xp", 0) if user else 0
        user_summary = format_session_summary(stats, is_user1=True, coins_balance=user_coins)
        
        # Build partner summary
        partner = await UserRepository.get_by_telegram_id(partner_id)
        partner_coins = partner.get("coins", 0) if partner else 0
        stats["total_xp"] = partner.get("xp", 0) if partner else 0
        partner_summary = "❌ **Chat ended by stranger**\n\n" + format_session_summary(stats, is_user1=False, coins_balance=partner_coins)
        
        return {
            "text": user_summary,
            "reply_markup": end_menu(can_rematch=True, partner_id=partner_id),
            "partner_msg": {
                "text": partner_summary,
                "reply_markup": end_menu(can_rematch=True, partner_id=user_id),
                "target_id": partner_id
            }
        }

    @staticmethod
    async def handle_next(client: Client, user_id: int) -> Dict[str, Any]:
        """Skips to the next partner (disconnect + auto-search)."""
        # Record action for behavior scoring
        from utils.behavior_tracker import behavior_tracker
        await behavior_tracker.record_next(user_id)
        
        # Check behavioral cooldown (progressive)
        cooldown = await behavior_tracker.get_next_cooldown(user_id)
        if cooldown > 3.0:
            # Use the behavior engine's value directly — it is the authoritative source
            return {"alert": f"⏳ Please slow down! Wait {cooldown:.0f}s before skipping again.", "show_alert": True}

        # Save preference before disconnect — read from Redis when available (C9 fix)
        if distributed_state.redis:
            pref_data = await distributed_state.get_user_queue_data(user_id)
            prev_pref = pref_data.get("pref", "Any")
            # get_user_queue_data may return int/float for non-string fields; cast to str
            if not isinstance(prev_pref, str):
                prev_pref = str(prev_pref)
        else:
            async with match_state._lock:
                prev_pref = match_state.user_preferences.get(user_id, {}).get("pref", "Any")

        stats = await MatchmakingService.disconnect(user_id)
        
        if stats:
            partner_id = stats["partner_id"]
            # Notify the partner they were skipped
            from database.repositories.user_repository import UserRepository
            partner = await UserRepository.get_by_telegram_id(partner_id)
            partner_coins = partner.get("coins", 0) if partner else 0
            partner_summary = "⏭ **Partner skipped to the next chat.**\n\n" + format_session_summary(stats, is_user1=False, coins_balance=partner_coins)
            
            await update_user_ui(client, partner_id, partner_summary, end_menu(can_rematch=True, partner_id=user_id))
        
        # Auto-search for a new partner with original preference restored
        success = await MatchmakingService.add_to_queue(user_id, gender_pref=prev_pref)
        if not success:
            return {"text": "❌ Could not rejoin queue.", "reply_markup": end_menu()}
            
        new_partner = await MatchmakingService.find_partner(client, user_id)
        if new_partner:
            now = time.time()
            from database.repositories.user_repository import UserRepository
            user_row = await UserRepository.get_by_telegram_id(user_id)
            user_last_safety = user_row.get("safety_last_seen", 0) if user_row else 0
            show_safety = (now - user_last_safety > 86400)
            
            match_text = get_match_found_text(include_safety=show_safety)
            if show_safety:
                _fire(UserRepository.update(user_id, safety_last_seen=int(now)))

            return {
                "text": match_text,
                "reply_markup": chat_menu(),
                "partner_msg": {
                    "target_id": new_partner,
                    "text": get_match_found_text(),
                    "reply_markup": chat_menu()
                }
            }
        
        # Get intelligent hint
        hint = await behavior_tracker.get_contextual_hint(user_id, "disconnected")
        hint_text = f"\n\n💡 {hint}" if hint else ""

        return {
            "text": f"⏳ Searching for a new partner...{hint_text}",
            "reply_markup": search_menu(),
            "start_animation": True
        }

    @staticmethod
    async def handle_rematch(client: Client, user_id: int) -> Dict[str, Any]:
        """Requests a rematch with the last partner."""
        from database.repositories.user_repository import UserRepository
        user = await UserRepository.get_by_telegram_id(user_id)
        partner_id = user.get("last_partner_id")
        
        if not partner_id:
            return {"alert": "❌ Rematch no longer available!", "show_alert": True}
            
        # Deduct 1 coin for rematch
        if not await UserService.deduct_coins(user_id, 1):
            return {"alert": "❌ Not enough coins (1 required)!", "show_alert": True}
            
        success = await MatchmakingService.request_rematch(user_id, partner_id)
        if success:
            match_text = get_match_found_text(is_rematch=True)
            return {
                "text": match_text,
                "reply_markup": chat_menu(),
                "partner_msg": {
                    "target_id": partner_id,
                    "text": match_text,
                    "reply_markup": chat_menu()
                }
            }
            
        # Notify partner they have a rematch request
        return {
            "alert": "🔄 Rematch requested! Waiting for partner...",
            "show_alert": True,
            "notify_partner": {
                "target_id": partner_id,
                "text": "🔄 **Your last partner wants a rematch!**\nClick 'Rematch' in your summary to reconnect."
            }
        }

    @staticmethod
    async def handle_icebreaker(client: Client, user_id: int) -> Dict[str, Any]:
        """Triggers a premium icebreaker question during chat."""
        from services.user_service import UserService
        import random
        from state.match_state import match_state
        
        partner_id = await match_state.get_partner(user_id)
        if not partner_id:
            return {"alert": "❌ You are not connected to anyone!", "show_alert": True}
        
        questions = [
            "Truth or Dare: What’s the most embarrassing thing you’ve done on a date? 😳",
            "Deep Question: What’s a controversial opinion you have? 🤔",
            "Fun Fact: If you could only eat one food for the rest of your life, what would it be? 🍕",
            "Spicy: What’s the worst pickup line you’ve ever used or heard? 🔥",
            "Icebreaker: If you had to describe yourself in 3 emojis, what would they be? 🙈"
        ]
        
        if not await UserService.deduct_coins(user_id, 5):
            return {"alert": "❌ Icebreakers cost 5 coins!", "show_alert": True}
            
        question = random.choice(questions)
        from utils.keyboard import chat_menu
        
        return {
            "alert": "✅ Icebreaker sent!",
            "show_alert": False,
            "text": f"🎲 **You activated an Icebreaker!**\n\n{question}",
            "reply_markup": chat_menu(),
            "partner_msg": {
                "target_id": partner_id,
                "text": f"🎲 **Your partner activated an Icebreaker!**\n\n{question}",
                "reply_markup": chat_menu()
            }
        }
