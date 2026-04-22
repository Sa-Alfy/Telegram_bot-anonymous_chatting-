from pyrogram import Client
from utils.logger import logger
from typing import Any

class PlatformAdapter:
    @staticmethod
    async def send_cross_platform(client: Client, target_id: Any, text: str, reply_markup=None):
        # Determine platform robustly
        is_messenger = False
        if isinstance(target_id, str):
            is_messenger = target_id.startswith("msg_")
        elif isinstance(target_id, int):
            is_messenger = target_id >= 10**15

        if is_messenger:
            from database.repositories.user_repository import UserRepository
            user = await UserRepository.get_by_telegram_id(target_id)
            if user:
                psid = user.get("username", "")[4:] if user.get("username", "").startswith("msg_") else target_id[4:]
                from messenger_api import send_quick_replies, send_message
                from adapters.messenger.ui_factory import (
                    get_chat_menu_buttons, get_end_menu_buttons,
                    get_start_menu_buttons, get_search_pref_buttons
                )
                from state.match_state import UserState

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
                        # Map to a quick reply for Messenger if it's a friend message reply
                        import re
                        match = re.search(r"msg_friend_(\d+)", str_markup)
                        if match:
                            target_friend_id = match.group(1)
                            buttons = [{"title": "⚡ Reply", "payload": f"msg_friend_{target_friend_id}"}]
                
                try:
                    if buttons:
                        send_quick_replies(psid, text, buttons)
                    else:
                        send_message(psid, text)
                    return True
                except Exception as e:
                    logger.error(f"Messenger API Error for {psid}: {e}")
                    return False
            return False
        else:
            try:
                await client.send_message(chat_id=target_id, text=text, reply_markup=reply_markup)
                return True
            except Exception as e:
                logger.error(f"Telegram API Error for {target_id}: {e}")
                return False
