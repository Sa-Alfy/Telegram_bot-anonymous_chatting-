# adapters/telegram/adapter.py

from typing import Dict, Any, Optional
from adapters.base import BaseAdapter
from adapters.telegram.keyboards import *
from core.engine.state_machine import UnifiedState
from utils.renderer import StateBoundPayload
from pyrogram import Client

class TelegramAdapter(BaseAdapter):
    """Telegram UI Platform Adapter."""

    def __init__(self, client: Client):
        self.client = client

    async def translate_event(self, raw_update: Any) -> Optional[Dict[str, Any]]:
        """Maps CallbackQuery or Message to Event Contract."""
        if hasattr(raw_update, "data"):
            # Callback Query
            data = raw_update.data
            uid = str(raw_update.from_user.id)
            
            # Decode payload using the now-robust decode logic
            action, target_str, state_gate = StateBoundPayload.decode(data)
            action = action.upper()
            
            # Match ID resolution (Contextual)
            # If state_gate looks like a partner ID (numeric) or a match ID (m_...)
            ctx_id = state_gate if (state_gate.startswith("m_") or state_gate.isdigit()) else target_str
            mid = ctx_id if ctx_id.startswith("m_") else f"m_{uid}_{ctx_id}" if (ctx_id and ctx_id != "0") else "global"

            if action in {"SEARCH", "START_SEARCH"}:
                return self.create_event("SHOW_PREFS", uid)
            elif action == "SEARCH_PREF":
                # target_str contains the chosen preference (Male/Female/Any)
                return self.create_event("START_SEARCH", uid, payload={"pref": target_str})
            elif action in {"CANCEL_SEARCH", "STOP_SEARCH"}:
                return self.create_event("STOP_SEARCH", uid)
            elif action in {"STOP", "END_CHAT"}:
                return self.create_event("END_CHAT", uid, mid)
            elif action in {"NEXT", "NEXT_MATCH"}:
                return self.create_event("NEXT_MATCH", uid, mid)
            elif action == "SKIP_VOTE":
                return self.create_event("SKIP_VOTE", uid, mid)
            elif action == "RECOVER":
                return self.create_event("RECOVER", uid)
            elif action == "VOTE":
                # Format: VOTE:sig:val:state -> target_str is "sig:val"
                parts = target_str.split(":")
                if len(parts) >= 2:
                    sig, val = parts[0], parts[1]
                    return self.create_event("SUBMIT_VOTE", uid, mid, {"type": sig, "value": val})
            
            # Non-engine events (Stats, Shop, etc.) return None to fallback to legacy dispatcher
            return None
        elif hasattr(raw_update, "text"):
            # Text commands
            uid = str(raw_update.from_user.id)
            text = raw_update.text
            if text == "/start":
                return self.create_event("CMD_START", uid)
            elif text == "/search":
                return self.create_event("SHOW_PREFS", uid)
            elif text == "/recover":
                return self.create_event("RECOVER", uid)

        return None

    async def render_state(self, user_id: str, state: str, payload: Optional[Dict[str, Any]] = None) -> bool:
        """Standardized Telegram rendering. Returns True for Render-ACK."""
        try:
            uid = int(user_id)
            mid = payload.get("match_id") if payload else "global"

            if state == UnifiedState.HOME:
                await self.client.send_message(
                    uid, 
                    "🏠 **Main Menu**\nWelcome back! Tap below to start.",
                    reply_markup=get_home_keyboard()
                )
            elif state == UnifiedState.PREFERENCES:
                await self.client.send_message(
                    uid,
                    "🔍 **Matchmaking Preferences**\n\nWho are you looking for today?",
                    reply_markup=get_preferences_keyboard()
                )
            elif state == UnifiedState.SEARCHING:
                await self.client.send_message(
                    uid,
                    "⏳ **Searching...**\nFinding someone for you. Please wait.",
                    reply_markup=get_searching_keyboard()
                )
            elif state == UnifiedState.CHAT_ACTIVE:
                await self.client.send_message(
                    uid,
                    "🎉 **Connected!**\nYou are now chatting anonymously.",
                    reply_markup=get_chat_keyboard(mid)
                )
            elif state == UnifiedState.VOTING:
                # 1. Extract Stats for Summary
                from utils.ui_formatters import format_session_summary
                stats = payload.get("payload", {}) if payload else {}
                summary_text = ""
                if stats:
                    summary_text = "📊 **Session Summary**\n" + format_session_summary(stats, is_user1=True) + "\n\n"
                
                # 2. Determine Voting Step
                signals = payload.get("signals", {}) if payload else {}
                if not signals.get("reputation"):
                    await self.client.send_message(
                        uid,
                        f"{summary_text}🗳 **Feedback Required**\nHow was your experience with this partner?",
                        reply_markup=get_voting_keyboard(mid, "reputation")
                    )
                elif not signals.get("identity"):
                    await self.client.send_message(
                        uid,
                        f"🗳 **Identity Hint**\nOne more thing: What was their gender?",
                        reply_markup=get_voting_keyboard(mid, "identity")
                    )
            return True
        except Exception as e:
            from utils.logger import logger
            logger.error(f"Telegram Render Failed: {e}")
            return False


    async def send_error(self, user_id: str, error_msg: str):
        await self.client.send_message(int(user_id), f"⚠️ **Error:** {error_msg}")
