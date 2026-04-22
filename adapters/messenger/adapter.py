from utils.logger import logger
# adapters/messenger/adapter.py


from typing import Dict, Any, Optional
from adapters.base import BaseAdapter
from adapters.messenger.ui_factory import *
from core.engine.state_machine import UnifiedState
from messenger_api import send_message, send_quick_replies, send_generic_template

class MessengerAdapter(BaseAdapter):
    """Messenger UI Platform Adapter."""

    async def translate_event(self, raw_update: Any) -> Optional[Dict[str, Any]]:
        """Maps Messenger webhook payload to Event Contract."""
        # raw_update would be the messenger 'entry' or 'messaging' object
        msg = raw_update.get("message", {})
        postback = raw_update.get("postback", {})
        psid = raw_update.get("sender", {}).get("id")
        uid = f"msg_{psid}"

        data = msg.get("quick_reply", {}).get("payload") or postback.get("payload")
        
        if data:
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
            elif action == "TOOLS_MENU":
                # This doesn't trigger a core action, just UI re-render
                await self.render_tools(psid, mid)
                return None

            # Non-engine events return None to fallback
            return None

        elif msg.get("text"):
            text = msg.get("text").strip().lower()
            if text in ["/start", "menu"]:
                return self.create_event("CMD_START", uid)

        return None

    async def render_state(self, user_id: str, state: str, payload: Optional[Dict[str, Any]] = None) -> bool:
        """Standardized Messenger rendering. Returns True for Render-ACK."""
        try:
            # Robust PSID resolution: Handle msg_ prefix, and resolve virtual IDs via DB
            psid = str(user_id)
            if psid.startswith("msg_"):
                psid = psid[4:]
            
            # If psid is a virtual ID (10^15 range), resolve it to real PSID from DB
            if psid.isdigit() and 10**15 <= int(psid) < 2*10**15:
                from database.repositories.user_repository import UserRepository
                u = await UserRepository.get_by_telegram_id(int(psid))
                if u and u.get("username", "").startswith("msg_"):
                    psid = u["username"][4:]
            
            mid = payload.get("match_id") if payload else "global"

            res = None
            if state == UnifiedState.HOME:
                res = send_quick_replies(psid, "🏠 **Main Menu**\nWelcome! Tap below to start meeting people.", get_messenger_home_buttons())
            elif state == UnifiedState.PREFERENCES:
                res = send_quick_replies(psid, "🔍 Who are you looking for today?", get_messenger_preferences_buttons())
            elif state == UnifiedState.SEARCHING:
                res = send_quick_replies(psid, "⏳ **Searching...**\nFinding your partner. Stay close!", [{"title": "❌ Cancel", "payload": "STOP_SEARCH"}])
            elif state == UnifiedState.CHAT_ACTIVE:
                res = send_quick_replies(psid, "🎉 **Connected!**\nChat anonymously. Tap 'Tools' for icebreakers.", get_messenger_chat_buttons(mid))
            elif state == UnifiedState.VOTING:
                from utils.ui_formatters import format_session_summary
                stats = payload.get("payload", {}) if payload else {}
                summary_text = ""
                if stats:
                    summary_text = "📊 Session Summary\n" + format_session_summary(stats, is_user1=True) + "\n\n"

                signals = payload.get("signals", {}) if payload else {}
                if not signals.get("reputation"):
                    res = send_generic_template(psid, [get_messenger_vote_card(mid, "reputation")])
                    if summary_text: send_message(psid, summary_text)
                elif not signals.get("identity"):
                    res = send_generic_template(psid, [get_messenger_vote_card(mid, "identity")])
                    if summary_text: send_message(psid, summary_text)
            
            # Check if API call returned an error
            if res and "error" in res:
                logger.error(f"Messenger API Error during render: {res['error']}")
                return False
            return True
        except Exception as e:
            logger.error(f"Messenger Render Failed for {user_id}: {e}")
            return False


    async def render_tools(self, psid: str, match_id: str):
        """Messenger-only: Progressive disclosure of tools."""
        send_quick_replies(psid, "🛠 **Companion Tools**", get_messenger_tools_buttons(match_id))

    async def send_error(self, user_id: str, error_msg: str):
        psid = user_id[4:] if user_id.startswith("msg_") else user_id
        send_message(psid, f"⚠️ Error: {error_msg}")
