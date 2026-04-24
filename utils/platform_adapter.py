from pyrogram import Client
from utils.logger import logger
from typing import Any, Dict, Optional

class PlatformAdapter:
    @staticmethod
    async def render_state(user_id: str, state: str, payload: Optional[Dict[str, Any]] = None) -> bool:
        """Routes the render command to the correct platform adapter."""
        is_messenger = False
        if isinstance(user_id, str):
            is_messenger = user_id.startswith("msg_") or (user_id.isdigit() and int(user_id) >= 10**15)
        elif isinstance(user_id, int):
            is_messenger = user_id >= 10**15

        if is_messenger:
            from adapters.messenger.adapter import MessengerAdapter
            adapter = MessengerAdapter()
            return await adapter.render_state(str(user_id), state, payload)
        else:
            import app_state
            from adapters.telegram.adapter import TelegramAdapter
            adapter = TelegramAdapter(app_state.telegram_app)
            return await adapter.render_state(str(user_id), state, payload)

    @staticmethod
    async def send_cross_platform(client: Client, target_id: Any, text: str, reply_markup=None, media_type: str = None, media_url: str = None):
        # Determine platform robustly
        is_messenger = False
        if isinstance(target_id, str):
            is_messenger = target_id.startswith("msg_") or (target_id.isdigit() and int(target_id) >= 10**15)
        elif isinstance(target_id, int):
            is_messenger = target_id >= 10**15

        if is_messenger:
            from database.repositories.user_repository import UserRepository
            user = await UserRepository.get_by_telegram_id(target_id)
            if user:
                # Priority 1: Use the username column (contains msg_<PSID>)
                username = user.get("username", "")
                if username and username.startswith("msg_"):
                    psid = username[4:]
                else:
                    # Priority 2: Fallback to the target_id if it's already a PSID
                    target_str = str(target_id)
                    psid = target_str[4:] if target_str.startswith("msg_") else target_str
                
                # Validation: If the psid looks like a hashed ID (>= 10^15), 
                # it means we failed to find the real PSID.
                if psid.isdigit() and int(psid) >= 10**15 and (not username or not username.startswith("msg_")):
                    logger.error(f"Failed to resolve real PSID for {target_id}. Cannot send message.")
                    return False
                
                from messenger_api import send_quick_replies, send_message, send_image
                from adapters.messenger.ui_factory import (
                    get_chat_menu_buttons, get_end_menu_buttons,
                    get_start_menu_buttons, get_search_pref_buttons
                )
                from state.match_state import UserState

                # 1. Handle Media First
                if media_url:
                    # Messenger requires a public URL for media attachments.
                    # Telegram file_ids will NOT work here.
                    is_url = str(media_url).startswith("http")
                    
                    if media_type == "image" and is_url:
                        send_image(psid, media_url)
                    elif is_url:
                        send_message(psid, f"[\U0001f4ce {media_type.capitalize()}] {media_url}")
                    else:
                        # Fallback for Telegram native media (file_id)
                        text = f"[\U0001f4ce {media_type.capitalize()} received] (View on Telegram)\n\n{text or ''}"

                # 2. Handle Text + Buttons
                buttons = []
                
                # Need the user's current unified state
                from database.repositories.user_repository import UserRepository
                from services.distributed_state import distributed_state
                from core.engine.state_machine import UnifiedState
                from state.match_state import match_state
                
                # Resolve the correct Platform ID for Redis state lookup
                redis_uid = str(target_id) # Could be int or string
                virtual_id = int(target_id) if str(target_id).isdigit() else 0
                
                if not redis_uid.startswith("msg_") and is_messenger:
                    # If it's a numeric ID but on Messenger platform, we need the raw PSID/msg_ prefix
                    if username and username.startswith("msg_"):
                        redis_uid = username
                    else:
                        # Final fallback: if target_id is a PSID string without prefix
                        if not redis_uid.startswith("10"): # Not a virtual ID
                             redis_uid = f"msg_{redis_uid}"

                if not virtual_id and redis_uid.startswith("msg_"):
                    # Derive virtual_id from PSID if we only have the string
                    from messenger.utils import _raw
                    psid = _raw(redis_uid)
                    import hashlib
                    psid_hash = int(hashlib.sha256(psid.encode()).hexdigest(), 16)
                    virtual_id = (psid_hash % (10**15)) + 10**15

                current_state = await distributed_state.get_user_state(redis_uid)
                
                # Fetch match_id if in chat or voting
                match_id = "global"
                if current_state in {UnifiedState.CHAT_ACTIVE, UnifiedState.VOTING}:
                    # Match state uses integer ID for user
                    partner_id = await match_state.get_partner(virtual_id)
                    if partner_id:
                        u1, u2 = (str(virtual_id), str(partner_id))
                        match_id = f"m_{min(u1, u2)}_{max(u1, u2)}"

                if reply_markup is not None:
                    str_markup = str(reply_markup)
                    if "Next" in str_markup and "Stop" in str_markup:
                        from adapters.messenger.ui_factory import get_messenger_chat_buttons
                        buttons = get_messenger_chat_buttons(match_id)
                    elif "My Stats" in str_markup and "Find Partner" in str_markup:
                        from adapters.messenger.ui_factory import get_messenger_home_buttons
                        buttons = get_messenger_home_buttons()
                    elif "Find New" in str_markup and "My Stats" in str_markup:
                        from adapters.messenger.ui_factory import get_messenger_post_chat_buttons
                        buttons = get_messenger_post_chat_buttons(match_id)
                    elif "Female" in str_markup and "Male" in str_markup:
                        from adapters.messenger.ui_factory import get_messenger_preferences_buttons
                        buttons = get_messenger_preferences_buttons()
                    elif "Reply" in str_markup or "msg_friend_" in str_markup:
                        import re
                        match = re.search(r"msg_friend_(\d+)", str_markup)
                        if match:
                            target_friend_id = match.group(1)
                            buttons = [{"title": "\u26a1 Reply", "payload": f"msg_friend_{target_friend_id}"}]
                
                # Fallback: if no buttons could be derived from reply_markup, use the user's current state
                if not buttons:
                    from adapters.messenger.ui_factory import (
                        get_messenger_home_buttons, get_messenger_chat_buttons,
                        get_messenger_post_chat_buttons, get_messenger_preferences_buttons,
                        get_gender_buttons, get_interests_skip_buttons,
                        get_location_skip_buttons, get_bio_skip_buttons
                    )
                    from utils.renderer import StateBoundPayload
                    if current_state == UnifiedState.CHAT_ACTIVE:
                        buttons = get_messenger_chat_buttons(match_id)
                    elif current_state == UnifiedState.VOTING:
                        buttons = get_messenger_post_chat_buttons(match_id)
                    elif current_state == UnifiedState.SEARCHING:
                        buttons = [{"title": "❌ Cancel", "payload": StateBoundPayload.encode("STOP_SEARCH", "0", UnifiedState.SEARCHING)}]
                    elif current_state == UnifiedState.PREFERENCES:
                        buttons = get_messenger_preferences_buttons()
                    elif current_state == UnifiedState.REG_GENDER:
                        buttons = get_gender_buttons(UnifiedState.REG_GENDER)
                    elif current_state == UnifiedState.REG_INTERESTS:
                        buttons = get_interests_skip_buttons(UnifiedState.REG_INTERESTS)
                    elif current_state == UnifiedState.REG_LOCATION:
                        buttons = get_location_skip_buttons(UnifiedState.REG_LOCATION)
                    elif current_state == UnifiedState.REG_BIO:
                        buttons = get_bio_skip_buttons(UnifiedState.REG_BIO)
                    else:
                        buttons = get_messenger_home_buttons()
                
                try:
                    result = None
                    if text or buttons:
                        if buttons:
                            result = send_quick_replies(psid, text or "💬 Message:", buttons)
                        else:
                            result = send_message(psid, text)
                    
                    if result and "error" in result:
                        logger.error(f"Messenger delivery failed for {psid}: {result['error']}")
                        return False
                    return True
                except Exception as e:
                    logger.error(f"Messenger API Exception for {psid}: {e}")
                    return False
            return False
        else:
            # 3. Handle Telegram delivery
            # Safety: Ensure target_id is likely a valid Telegram ID or username
            if not str(target_id).replace("-", "").isdigit() and not str(target_id).startswith("@"):
                logger.warning(f"Aborting TG send: target_id '{target_id}' is not a valid identifier.")
                return False
            try:
                if media_url:
                    if media_type == "image":
                        await client.send_photo(chat_id=target_id, photo=media_url, caption=text, reply_markup=reply_markup)
                    elif media_type == "video":
                        await client.send_video(chat_id=target_id, video=media_url, caption=text, reply_markup=reply_markup)
                    else:
                        await client.send_document(chat_id=target_id, document=media_url, caption=text, reply_markup=reply_markup)
                else:
                    await client.send_message(chat_id=target_id, text=text, reply_markup=reply_markup)
                return True
            except Exception as e:
                logger.error(f"Telegram API Error for {target_id}: {e}")
                return False
