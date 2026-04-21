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

        payload = msg.get("quick_reply", {}).get("payload") or postback.get("payload")
        
        if payload:
            if payload == "START_SEARCH":
                return self.create_event("SHOW_PREFS", uid)
            elif payload == "STOP_SEARCH":
                return self.create_event("STOP_SEARCH", uid)
            elif payload.startswith("SEARCH_PREF:"):
                pref = payload.split(":")[1]
                return self.create_event("START_SEARCH", uid, payload={"pref": pref})
            elif payload.startswith("END_CHAT:"):
                mid = payload.split(":")[1]
                return self.create_event("END_CHAT", uid, mid)
            elif payload.startswith("NEXT_MATCH:"):
                mid = payload.split(":")[1]
                return self.create_event("NEXT_MATCH", uid, mid)
            elif payload.startswith("VOTE:"):
                parts = payload.split(":")
                sig = parts[1]
                val = parts[2]
                mid = parts[3]
                return self.create_event("SUBMIT_VOTE", uid, mid, {"type": sig, "value": val})
            elif payload.startswith("TOOLS_MENU:"):
                mid = payload.split(":")[1]
                # This doesn't trigger a core action, just UI re-render
                await self.render_tools(psid, mid)
                return None

        elif msg.get("text"):
            text = msg.get("text").strip().lower()
            if text in ["/start", "menu"]:
                return self.create_event("CMD_START", uid)

        return None

    async def render_state(self, user_id: str, state: str, payload: Optional[Dict[str, Any]] = None) -> bool:
        """Standardized Messenger rendering. Returns True for Render-ACK."""
        try:
            psid = user_id[4:] if user_id.startswith("msg_") else user_id
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
                signals = payload.get("signals", {}) if payload else {}
                if not signals.get("reputation"):
                    res = send_generic_template(psid, [get_messenger_vote_card(mid, "reputation")])
                elif not signals.get("identity"):
                    res = send_generic_template(psid, [get_messenger_vote_card(mid, "identity")])
            
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
