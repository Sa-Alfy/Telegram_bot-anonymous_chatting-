# adapters/telegram/adapter.py

from typing import Dict, Any, Optional
from adapters.base import BaseAdapter
from adapters.telegram.keyboards import (
    get_home_keyboard, get_searching_keyboard, get_chat_keyboard,
    get_voting_keyboard, get_preferences_keyboard,
    persistent_home_menu, persistent_chat_menu, get_error_keyboard
)
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
            # Only use state_gate if it's a valid match_id or a numeric partner_id
            mid = "global"
            if state_gate and (state_gate.startswith("m_") or state_gate.isdigit()):
                mid = state_gate if state_gate.startswith("m_") else f"m_{uid}_{state_gate}"
            elif target_str and target_str.startswith("m_"):
                mid = target_str

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
            elif action == "KARMA_BOOST":
                return self.create_event("KARMA_BOOST", uid)
            elif action == "gift_menu":
                return self.create_event("SHOW_GIFTS", uid)
            elif action == "open_reactions":
                return self.create_event("SHOW_REACTIONS", uid, payload={"menu": True})
            elif action.startswith("react_"):
                reaction_type = action.replace("react_", "")
                # Map internal names to emojis if needed, or just pass the type
                reactions = {"heart": "❤️", "joy": "😂", "wow": "😮", "sad": "😢", "up": "👍"}
                emoji = reactions.get(reaction_type, "✨")
                return self.create_event("SUBMIT_REACTION", uid, payload={"value": emoji})
            elif action.startswith("send_gift_") or action.startswith("SEND_GIFT:"):
                gift_key = action.replace("send_gift_", "").replace("SEND_GIFT:", "").lower()
                return self.create_event("SEND_GIFT", uid, payload={"gift_key": gift_key})
            
            # Non-engine events (Stats, Shop, etc.) return LEGACY_DISPATCH
            return self.create_event("LEGACY_DISPATCH", uid, payload={"raw_data": data})
        elif hasattr(raw_update, "text") or hasattr(raw_update, "photo") or hasattr(raw_update, "sticker") or hasattr(raw_update, "video") or hasattr(raw_update, "animation") or hasattr(raw_update, "voice"):
            # Telegram Message
            uid = str(raw_update.from_user.id)
            from services.distributed_state import distributed_state
            state = await distributed_state.get_user_state(uid)

            # 1. Handle Commands (regardless of state)
            if hasattr(raw_update, "text"):
                text = raw_update.text
                if text == "/start":
                    return self.create_event("CMD_START", uid)
                elif text == "/search":
                    return self.create_event("SHOW_PREFS", uid)
                elif text == "/recover":
                    return self.create_event("RECOVER", uid)
                elif text == "/stop":
                    return self.create_event("END_CHAT", uid)
                elif text == "/next":
                    return self.create_event("NEXT_MATCH", uid)

            # 2. Handle Chat Messaging (only if state is CHAT_ACTIVE)
            if state == UnifiedState.CHAT_ACTIVE:
                if hasattr(raw_update, "text") and raw_update.text:
                    if not raw_update.text.startswith("/"):
                        return self.create_event("SEND_MESSAGE", uid, payload={"text": raw_update.text})
                
                # Media Handling
                media_type = None
                file_id = None
                if raw_update.photo:
                    media_type = "image"
                    file_id = raw_update.photo.file_id
                elif raw_update.sticker:
                    media_type = "sticker"
                    file_id = raw_update.sticker.file_id
                elif raw_update.video:
                    media_type = "video"
                    file_id = raw_update.video.file_id
                elif raw_update.animation:
                    media_type = "animation"
                    file_id = raw_update.animation.file_id
                elif raw_update.voice:
                    media_type = "voice"
                    file_id = raw_update.voice.file_id
                
                if media_type:
                    return self.create_event("SEND_MEDIA", uid, payload={
                        "media_type": media_type,
                        "file_id": file_id,
                        "caption": raw_update.caption
                    })

        return None

    async def render_state(self, user_id: str, state: str, payload: Optional[Dict[str, Any]] = None) -> bool:
        """Standardized Telegram rendering. Returns True for Render-ACK."""
        try:
            uid = int(user_id)
            mid = payload.get("match_id") if payload else "global"

            # ── Generic Engine-Driven Rendering ───────────────────────────
            if payload and payload.get("text"):
                text = payload["text"]
                markup = payload.get("reply_markup")
                
                # If markup is a list of dicts, convert to InlineKeyboardMarkup
                if isinstance(markup, list):
                    from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
                    rows = []
                    for btn in markup:
                        rows.append([InlineKeyboardButton(btn["title"], callback_data=btn["payload"])])
                    markup = InlineKeyboardMarkup(rows)
                
                # Use query.edit_message_text if this is a callback response, 
                # but since render_state is usually called async via _rehydrate_ui, 
                # we just send a new message or we need to track the last message ID.
                # For now, we'll send a new message to keep it simple and avoid crashes.
                sent = await self.client.send_message(uid, text, reply_markup=markup)
                
                from state.match_state import match_state
                await match_state.track_ui_message(uid, sent.id)
                return True

            if state == UnifiedState.HOME:
                await self.client.send_message(
                    uid,
                    "\U0001f3e0 **Main Menu**\nWelcome back! Tap below to start.",
                    reply_markup=get_home_keyboard()
                )
                # Silently swap Reply Keyboard back to home layout
                # Use a subtle '.' to avoid 'MESSAGE_EMPTY' error from Telegram
                await self.client.send_message(uid, ".", reply_markup=persistent_home_menu(), disable_notification=True)

            elif state == UnifiedState.PREFERENCES:
                await self.client.send_message(
                    uid,
                    "\U0001f50d **Matchmaking Preferences**\n\nWho are you looking for today?",
                    reply_markup=get_preferences_keyboard()
                )

            elif state == UnifiedState.SEARCHING:
                await self.client.send_message(
                    uid,
                    "\u23f3 **Searching...**\nFinding someone for you. Use the options below while you wait.",
                    reply_markup=get_searching_keyboard()
                )

            elif state == UnifiedState.CHAT_ACTIVE:
                await self.client.send_message(
                    uid,
                    "\U0001f389 **Connected!**\nYou are now chatting anonymously.",
                    reply_markup=get_chat_keyboard(mid)
                )
                # Silently swap Reply Keyboard to chat layout
                await self.client.send_message(uid, ".", reply_markup=persistent_chat_menu(), disable_notification=True)

            elif state == UnifiedState.VOTING:
                # 1. Extract Stats for Summary
                from utils.ui_formatters import format_session_summary
                stats = payload.get("payload", {}) if payload else {}
                summary_text = ""
                if stats:
                    summary_text = "\U0001f4ca **Session Summary**\n" + format_session_summary(stats, is_user1=True, coins_balance=stats.get("coins_balance", 0)) + "\n\n"

                # 2. Determine Voting Step
                signals = payload.get("signals", {}) if payload else {}
                mid = mid or "global"
                if not signals.get("reputation"):
                    await self.client.send_message(
                        uid,
                        f"{summary_text}\U0001f5f3 **Feedback Required**\nHow was your experience with this partner?",
                        reply_markup=get_voting_keyboard(mid, "reputation")
                    )
                elif not signals.get("identity"):
                    await self.client.send_message(
                        uid,
                        f"\U0001f5f3 **Identity Hint**\nOne more thing: What was their gender?",
                        reply_markup=get_voting_keyboard(mid, "identity")
                    )
                else:
                    # All votes done — push to Home
                    await self.client.send_message(
                        uid,
                        "\U0001f3e0 **Back to Main Menu**\nReady for another chat?",
                        reply_markup=get_home_keyboard()
                    )
                    await self.client.send_message(uid, "\u200b", reply_markup=persistent_home_menu())
            return True
        except Exception as e:
            from utils.logger import logger
            logger.error(f"Telegram Render Failed: {e}")
            return False

    async def send_error(self, user_id: str, error_msg: str):
        """Send an error message with recovery buttons so user is never stuck."""
        await self.client.send_message(
            int(user_id),
            f"\u26a0\ufe0f **Error:** {error_msg}\n\n_Use the buttons below to recover._",
            reply_markup=get_error_keyboard()
        )
