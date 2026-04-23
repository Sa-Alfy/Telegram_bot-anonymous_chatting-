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
            elif action in {"CMD_PROFILE", "PROFILE_MENU", "EDIT_PROFILE"}:
                return self.create_event("SHOW_PROFILE", uid)
            elif action in {"CMD_STATS", "STATS"}:
                return self.create_event("SHOW_STATS", uid)
            elif action in {"CMD_REPORT", "REPORT_PARTNER"}:
                return self.create_event("REPORT_USER", uid)
            elif action in {"CMD_BLOCK", "BLOCK_PARTNER"}:
                return self.create_event("BLOCK_USER", uid)
            elif action == "CMD_HELP":
                return self.create_event("SHOW_HELP", uid)
            elif action == "DELETE_DATA_CONFIRM":
                return self.create_event("DELETE_USER_DATA", uid)
            elif action in {"SEASONAL_SHOP", "SHOP_MENU"}:
                return self.create_event("SHOW_SHOP", uid)
            elif action in {"BUY_VIP", "BUY_OG", "BUY_WHALE"}:
                return self.create_event("PURCHASE_ITEM", uid, payload={"item_id": action})
            elif action == "REVEAL":
                return self.create_event("REVEAL_IDENTITY", uid)
            elif action == "ICEBREAKER":
                return self.create_event("SEND_ICEBREAKER", uid)
            elif action.startswith("CONFIRM_REVEAL"):
                # Format is CONFIRM_REVEAL_15
                parts = action.split("_")
                cost = int(parts[-1]) if parts[-1].isdigit() else 15
                return self.create_event("CONFIRM_REVEAL", uid, payload={"cost": cost})
            elif action in {"CMD_START", "BACK_HOME", "HOME_MENU"}:
                return self.create_event("SET_STATE", uid, payload={"new_state": "HOME"})
            elif action in {"START_ONBOARDING", "REG_START"}:
                return self.create_event("START_ONBOARDING", uid)
            elif action == "SET_GENDER":
                return self.create_event("SUBMIT_ONBOARDING", uid, payload={"field": "gender", "value": target_str})
            elif action == "TOOLS_MENU":
                # This doesn't trigger a core action, just UI re-render
                await self.render_tools(psid, mid)
                return None

            # Non-engine events return None to fallback
            return None

        elif msg.get("attachments"):
            from services.distributed_state import distributed_state
            from database.repositories.user_repository import UserRepository
            virtual_id = UserRepository._sanitize_id(uid)
            state = await distributed_state.get_user_state(virtual_id)
            if state == UnifiedState.CHAT_ACTIVE:
                att = msg["attachments"][0]
                m_type = att.get("type", "image")
                url = att.get("payload", {}).get("url")
                caption = msg.get("text", "").strip()
                return self.create_event("SEND_MEDIA", uid, payload={"media_type": m_type, "url": url, "caption": caption})

        elif msg.get("text"):
            from services.distributed_state import distributed_state
            from database.repositories.user_repository import UserRepository
            virtual_id = UserRepository._sanitize_id(uid)
            state = await distributed_state.get_user_state(virtual_id)
            text = msg.get("text").strip()
            
            if state in {UnifiedState.REG_INTERESTS, UnifiedState.REG_LOCATION, UnifiedState.REG_BIO}:
                return self.create_event("SUBMIT_ONBOARDING", uid, payload={"value": text})

            t_lower = text.lower()
            if t_lower in ["/start", "menu"]:
                return self.create_event("CMD_START", uid)
            elif t_lower == "/report":
                return self.create_event("REPORT_USER", uid)
            elif t_lower == "/block":
                return self.create_event("BLOCK_USER", uid)
            elif t_lower == "/help":
                return self.create_event("SHOW_HELP", uid)
            elif t_lower == "/delete":
                return self.create_event("DELETE_USER_DATA", uid)
            elif t_lower == "/shop":
                return self.create_event("SHOW_SHOP", uid)

            if state == UnifiedState.CHAT_ACTIVE and not t_lower.startswith("/"):
                return self.create_event("SEND_MESSAGE", uid, payload={"text": text})
            
            if not t_lower.startswith("/"):
                logger.info(f"DROPPED message from {uid} because state={state}")

        return None

    async def render_state(self, user_id: str, state: str, payload: Optional[Dict[str, Any]] = None) -> bool:
        """Standardized Messenger rendering. Returns True for Render-ACK."""
        try:
            # Robust PSID resolution: Handle msg_ prefix, and resolve virtual IDs via DB
            psid = str(user_id)
            if psid.startswith("msg_"):
                psid = psid[4:]
            
            # If psid is a virtual ID (10^15 range), resolve it to real PSID from DB
            from database.repositories.user_repository import UserRepository
            if psid.isdigit() and 10**15 <= int(psid) < 2*10**15:
                u = await UserRepository.get_by_telegram_id(int(psid))
                if u and u.get("username", "").startswith("msg_"):
                    psid = u["username"][4:]
            
            mid = payload.get("match_id") if payload else "global"
            vid = int(payload.get("vid")) if payload and payload.get("vid") else None
            
            # Fetch user context defensively
            user = await UserRepository.get_by_telegram_id(UserRepository._sanitize_id(user_id))

            # ── Economy / Shop Logic ──────────────────────────────────────
            if payload and payload.get("show_shop"):
                send_message(psid, "🛍 **Seasonal Shop**\nUse your coins to buy exclusive badges!")
                from adapters.messenger.ui_factory import get_shop_carousel
                send_generic_template(psid, get_shop_carousel())
                return True
                
            if payload and payload.get("item_name"):
                from database.repositories.user_repository import UserRepository
                from adapters.messenger.ui_factory import get_start_menu_buttons
                # The engine already updated the DB, we just confirm
                user = await UserRepository.get_by_telegram_id(int(user_id.replace("msg_", ""))) if user_id.replace("msg_", "").isdigit() else None
                coins = user.get("coins", 0) if user else 0
                send_quick_replies(
                    psid,
                    f"✅ **Purchase Successful!**\n\n🎁 {payload['item_name']} activated!\n💰 Balance: {coins} coins",
                    get_start_menu_buttons(state)
                )
                return True

            if payload and payload.get("response"):
                # Bridge: Handle legacy response dict from Economy/Matching handlers
                resp = payload["response"]
                if not resp: return True
                
                if "text" in resp:
                    from messenger_handlers import _map_reply_markup
                    buttons = _map_reply_markup(resp.get("reply_markup"))
                    if buttons: send_quick_replies(psid, resp["text"], buttons)
                    else: send_message(psid, resp["text"])
                elif "alert" in resp:
                    send_message(psid, resp["alert"])
                return True

            logger.info(f"[RENDER] User:{user_id} State:{state} Payload:{payload}")
            res = None
            if state == UnifiedState.HOME:
                match_id = payload.get("match_id") if payload else None
                if match_id:
                    from adapters.messenger.ui_factory import get_messenger_post_chat_buttons
                    res = send_quick_replies(psid, "🏁 **Chat Ended**\nHow was your experience? You can also start a new search immediately.", get_messenger_post_chat_buttons(match_id))
                else:
                    res = send_quick_replies(psid, "🏠 **Main Menu**\nWelcome! Tap below to start meeting people.", get_messenger_home_buttons())
            elif state == UnifiedState.PROFILE:
                user_data = payload.get("user_data") if payload else None
                if not user_data:
                    user_data = user or await UserRepository.get_by_telegram_id(UserRepository._sanitize_id(psid))
                
                if user_data:
                    res = send_generic_template(psid, get_profile_dashboard_card(user_data, UnifiedState.PROFILE))
                else:
                    res = send_message(psid, "⚠️ Profile data not found. Please try /start.")

            elif state == UnifiedState.STATS:
                user_data = payload.get("user_data") if payload else None
                if not user_data:
                    user_data = user or await UserRepository.get_by_telegram_id(UserRepository._sanitize_id(psid))
                
                if user_data:
                    res = send_generic_template(psid, get_stats_card(user_data, UnifiedState.STATS))
                else:
                    res = send_message(psid, "⚠️ Stats data not found. Please try /start.")
            elif state == UnifiedState.REG_GENDER:
                from adapters.messenger.ui_factory import get_gender_buttons
                res = send_quick_replies(psid, "🚻 **Step 1: Gender**\nHow do you identify? This helps us find better matches.", get_gender_buttons(UnifiedState.REG_GENDER))
            elif state == UnifiedState.REG_INTERESTS:
                from adapters.messenger.ui_factory import get_interests_skip_buttons
                res = send_quick_replies(psid, "🎨 **Step 2: Interests**\nWhat do you like? (e.g. Anime, Gaming, Travel)\nType them below or skip.", get_interests_skip_buttons(UnifiedState.REG_INTERESTS))
            elif state == UnifiedState.REG_LOCATION:
                from adapters.messenger.ui_factory import get_location_skip_buttons
                res = send_quick_replies(psid, "📍 **Step 3: Location**\nWhere are you from? (City/Country)\nType it below or skip.", get_location_skip_buttons(UnifiedState.REG_LOCATION))
            elif state == UnifiedState.REG_BIO:
                from adapters.messenger.ui_factory import get_bio_skip_buttons
                res = send_quick_replies(psid, "📝 **Step 4: Bio**\nTell us a bit about yourself!\nType a short bio below or skip.", get_bio_skip_buttons(UnifiedState.REG_BIO))
            elif state == UnifiedState.PREFERENCES:
                res = send_quick_replies(psid, "🔍 Who are you looking for today?", get_messenger_preferences_buttons())
            elif state == UnifiedState.SEARCHING:
                res = send_quick_replies(psid, "⏳ **Searching...**\nFinding your partner. Stay close!", [{"title": "❌ Cancel", "payload": "STOP_SEARCH"}])
            elif state == UnifiedState.CHAT_ACTIVE:
                res = send_quick_replies(psid, "🎉 **Connected!**\nChat anonymously. Tap 'Tools' for icebreakers.", get_messenger_chat_buttons(mid))
            elif state == UnifiedState.VOTING:
                from utils.ui_formatters import format_session_summary
                from adapters.messenger.ui_factory import get_messenger_post_chat_buttons
                
                stats = payload.get("payload") if payload else None
                summary_text = ""
                if stats and isinstance(stats, dict):
                    summary_text = "📊 Session Summary\n" + format_session_summary(stats, is_user1=True, coins_balance=stats.get("coins_balance", 0)) + "\n\n"

                signals = payload.get("signals") if payload else None
                if not isinstance(signals, dict): signals = {}
                
                mid = mid or "global"
                if not signals.get("reputation"):
                    res = send_generic_template(psid, [get_messenger_vote_card(mid, "reputation")])
                    if summary_text: 
                        send_message(psid, summary_text)
                    else:
                        send_message(psid, "🏁 **Chat ended by stranger.**")
                    send_quick_replies(psid, "Or jump straight back in:", get_messenger_post_chat_buttons(mid))
                elif not signals.get("identity"):
                    res = send_generic_template(psid, [get_messenger_vote_card(mid, "identity")])
                    send_quick_replies(psid, "Or jump straight back in:", get_messenger_post_chat_buttons(mid))
                else:
                    res = send_quick_replies(psid, "🏠 **Back to Main Menu**\nReady for another chat?", get_messenger_home_buttons())
            
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
