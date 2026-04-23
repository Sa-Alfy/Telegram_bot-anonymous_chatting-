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
                    if media_type == "image":
                        send_image(psid, media_url)
                    else:
                        send_message(psid, f"[\U0001f4ce {media_type.capitalize()}] {media_url}")

                # 2. Handle Text + Buttons
                buttons = []
                if reply_markup is not None:
                    str_markup = str(reply_markup)
                    if "Next" in str_markup and "Stop" in str_markup:
                        buttons = get_chat_menu_buttons(UserState.CHATTING)
                    elif "My Stats" in str_markup and "Find Partner" in str_markup:
                        buttons = get_start_menu_buttons(UserState.HOME)
                    elif "Find New" in str_markup and "My Stats" in str_markup:
                        buttons = get_end_menu_buttons(UserState.HOME)
                    elif "Female" in str_markup and "Male" in str_markup:
                        buttons = get_search_pref_buttons(UserState.HOME)
                    elif "Reply" in str_markup or "msg_friend_" in str_markup:
                        import re
                        match = re.search(r"msg_friend_(\d+)", str_markup)
                        if match:
                            target_friend_id = match.group(1)
                            buttons = [{"title": "\u26a1 Reply", "payload": f"msg_friend_{target_friend_id}"}]
                
                try:
                    if text or buttons:
                        if buttons:
                            send_quick_replies(psid, text or "💬 Message:", buttons)
                        else:
                            send_message(psid, text)
                    return True
                except Exception as e:
                    logger.error(f"Messenger API Error for {psid}: {e}")
                    return False
            return False
        else:
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
