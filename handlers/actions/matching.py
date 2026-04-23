import asyncio
import time
from typing import Dict, Any, Optional
from utils.rate_limiter import rate_limiter
from pyrogram import Client, types
from services.matchmaking import MatchmakingService
from state.match_state import match_state
from adapters.telegram.keyboards import search_menu, chat_menu, end_menu, start_menu, persistent_chat_menu
from pyrogram.types import ReplyKeyboardRemove
from utils.helpers import update_user_ui
from handlers.start import get_start_text
from services.user_service import UserService
from adapters.telegram.keyboards import retry_search_menu
from state.match_state import UserState
from utils.ui_formatters import get_match_found_text
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
    async def handle_search(client: Client, user_id: int, platform: str = "telegram") -> Dict[str, Any]:
        """Prompts the user for their matchmaking preferences."""
        if not await rate_limiter.can_matchmake(user_id, update=False):
            remaining = await rate_limiter.get_cooldown_remaining(user_id, "matchmake") or 0
            return {
                "text": f"⏳ **Please slow down!**\nWait {remaining:.1f}s before opening choices again.",
                "reply_markup": retry_search_menu(UserState.HOME)
            }
            
        current_state = await match_state.get_user_state(user_id) or UserState.HOME
        return {
            "text": "🔍 **Matchmaking Preferences**\n\nWho are you looking for today?",
            "reply_markup": retry_search_menu(current_state)
        }

    @staticmethod
    async def handle_search_with_pref(client: Client, user_id: int, pref: str, platform: str = "telegram") -> Dict[str, Any]:
        """Starts searching for a partner via the Unified Engine."""
        import app_state
        
        # Dispatch to Engine
        result = await app_state.engine.process_event({
            "event_type": "START_SEARCH",
            "user_id": str(user_id),
            "payload": {"pref": pref}
        })

        if not result.get("success"):
            return {"alert": result.get("error", "Search failed."), "show_alert": True}
        
        # Engine's rehydrate_ui handles the "Searching..." or "Match Found" message.
        return None

    @staticmethod
    async def handle_cancel(client: Client, user_id: int, platform: str = "telegram") -> Dict[str, Any]:
        """Cancels the search via the Unified Engine."""
        import app_state
        result = await app_state.engine.process_event({
            "event_type": "STOP_SEARCH",
            "user_id": str(user_id)
        })
        
        if not result.get("success"):
            return {"alert": result.get("error", "Failed to cancel search."), "show_alert": True}
        
        return None

    @staticmethod
    async def handle_stop(client: Client, user_id: int, platform: str = "telegram") -> Dict[str, Any]:
        """Disconnects from current chat via the Unified Engine."""
        import app_state
        result = await app_state.engine.process_event({
            "event_type": "END_CHAT",
            "user_id": str(user_id)
        })

        if not result.get("success"):
            return {"alert": result.get("error", "You are not in a chat!"), "show_alert": True}
            
        # UI is handled by Engine (State: VOTING)
        return None

    @staticmethod
    async def handle_next(client: Client, user_id: int, platform: str = "telegram") -> Dict[str, Any]:
        """Skips to the next partner via the Unified Engine."""
        import app_state
        result = await app_state.engine.process_event({
            "event_type": "NEXT_MATCH",
            "user_id": str(user_id)
        })

        if not result.get("success"):
            return {"alert": result.get("error", "Action failed."), "show_alert": True}

        # UI is handled by Engine
        return None

    @staticmethod
    async def handle_rematch(client: Client, user_id: int) -> Dict[str, Any]:
        """Requests a rematch with the last partner (Atomic claim)."""
        from database.repositories.user_repository import UserRepository
        user = await UserRepository.get_by_telegram_id(user_id)
        partner_id = user.get("last_partner_id")
        
        if not partner_id:
            return {"alert": "❌ Rematch no longer available!", "show_alert": True}
            
        # 1. Deduct 1 coin for rematch attempt
        if not await UserService.deduct_coins(user_id, 1):
            return {"alert": "❌ Not enough coins (1 required)!", "show_alert": True}
            
        # 2. Atomic attempt
        code, reason = await MatchmakingService.request_rematch(user_id, partner_id)
        
        if code == 1: # REMATCH_SUCCESS
            await MatchmakingService.initialize_match(client, user_id, partner_id)
            return {
                "text": "✅ **Rematch successful!**",
                "reply_markup": None
            }
        
        if code == 2: # WAITING_FOR_PARTNER / ALREADY_WAITING
            # Notify partner they have a rematch request
            return {
                "alert": "🔄 Rematch requested! Waiting for partner...",
                "show_alert": True,
                "notify_partner": {
                    "target_id": partner_id,
                    "text": "🔄 **Your last partner wants a rematch!**\nClick 'Rematch' in your summary to reconnect."
                }
            }

        # code == 0: Failure (Refund coins)
        await UserRepository.increment_coins(user_id, 1) # Direct refund without boosters
        return {
            "alert": "❌ Partner is currently in another chat or unavailable. Coin refunded.",
            "show_alert": True
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
        from adapters.telegram.keyboards import chat_menu
        
        return {
            "alert": "✅ Icebreaker sent!",
            "show_alert": False,
            "text": f"🎲 **You activated an Icebreaker!**\n\n{question}",
            "reply_markup": chat_menu(UserState.CHATTING, partner_id),
            "partner_msg": {
                "target_id": partner_id,
                "text": f"🎲 **Your partner activated an Icebreaker!**\n\n{question}",
                "reply_markup": chat_menu(UserState.CHATTING, user_id)
            }
        }
