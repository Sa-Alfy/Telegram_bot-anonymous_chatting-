from typing import Dict, Any, List, Optional
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

class StateBoundPayload:
    @staticmethod
    def encode(action: str, target: str, state: str) -> str:
        """Encodes state into callback data. Max 64 bytes for Telegram."""
        return f"{action}:{target}:{state}"
        
    @staticmethod
    def decode(data: str) -> tuple[str, str, str]:
        """Decodes state payload into (action, target, expected_state)."""
        parts = data.split(":")
        if len(parts) >= 3:
            return parts[0], parts[1], parts[2]
        return data, "", "HOME" # Fallback for old payloads

class Renderer:
    """Unified cross-platform renderer to guarantee state-bound lists and escape routes."""
    
    @staticmethod
    def render_profile_menu(platform: str, state: str) -> Dict[str, Any]:
        """Renders the main profile or HOME menu safely."""
        if platform == "telegram":
            buttons = [
                [InlineKeyboardButton("🔍 Find Partner", callback_data=StateBoundPayload.encode("search", "0", state))],
                [InlineKeyboardButton("👤 Edit Profile", callback_data=StateBoundPayload.encode("onboarding_start", "0", state))]
            ]
            return {
                "text": "🏠 **Dashboard**\nWhat would you like to do?",
                "reply_markup": InlineKeyboardMarkup(buttons)
            }
        else: # Messenger
            return {
                "text": "🏠 Welcome back! What would you like to do?",
                "quick_replies": [
                    {"title": "🔍 Find Partner", "payload": StateBoundPayload.encode("search", "0", state)},
                    {"title": "👤 Edit Profile", "payload": StateBoundPayload.encode("onboarding_start", "0", state)}
                ]
            }

    @staticmethod
    def render_searching_ui(platform: str, state: str) -> Dict[str, Any]:
        """Searching UI with escape routes."""
        if platform == "telegram":
            buttons = [
                [InlineKeyboardButton("❌ Cancel", callback_data=StateBoundPayload.encode("cancel_search", "0", state))]
            ]
            return {
                "text": "🔍 **Searching for a match...**\n*Please wait...*",
                "reply_markup": InlineKeyboardMarkup(buttons)
            }
        else:
            return {
                "text": "🔍 Looking for someone... (I'll ping you when found)",
                "quick_replies": [
                    {"title": "❌ Cancel", "payload": StateBoundPayload.encode("cancel_search", "0", state)}
                ]
            }
            
    @staticmethod
    def render_list(platform: str, state: str, items: List[dict], item_action: str) -> Dict[str, Any]:
        """
        Renders a generic list (e.g. Interests or Leaderboard) ensuring NO dead ends.
        items: list of dicts with 'id' and 'name'
        """
        if platform == "telegram":
            buttons = []
            for item in items:
                buttons.append([InlineKeyboardButton(item['name'], callback_data=StateBoundPayload.encode(item_action, str(item['id']), state))])
            
            # Always append escape route
            buttons.append([InlineKeyboardButton("🔙 Back", callback_data=StateBoundPayload.encode("back_home", "0", state))])
            
            return {
                "text": "📋 **Select an option:**",
                "reply_markup": InlineKeyboardMarkup(buttons)
            }
        else: # Messenger (Max 13 quick replies)
            replies = []
            for item in items[:10]: # Safe limit
                replies.append({"title": item['name'], "payload": StateBoundPayload.encode(item_action, str(item['id']), state)})
                
            replies.append({"title": "🔙 Back", "payload": StateBoundPayload.encode("back_home", "0", state)})
            
            return {
                "text": "📋 Select an option:",
                "quick_replies": replies
            }

    @staticmethod
    def render_match_found(platform: str, partner_id: int, is_rematch: bool = False, show_safety: bool = False) -> Dict[str, Any]:
        """Renders the match found announcement across platforms."""
        from utils.ui_formatters import get_match_found_text
        from utils.keyboard import chat_menu, UserState
        
        text = get_match_found_text(is_rematch=is_rematch, include_safety=show_safety)
        
        if platform == "telegram":
            return {
                "text": text,
                "reply_markup": chat_menu(UserState.CHATTING, partner_id)
            }
        else: # Messenger
            # For Messenger we might want to return structured data or use quick replies
            return {
                "text": text,
                "quick_replies": [
                    {"title": "🛑 Stop", "payload": StateBoundPayload.encode("stop", "0", f"{UserState.CHATTING}_{partner_id}")},
                    {"title": "⏭ Next", "payload": StateBoundPayload.encode("next", "0", f"{UserState.CHATTING}_{partner_id}")}
                ]
            }

    @staticmethod
    def render_preferences_menu(platform: str, state: str) -> Dict[str, Any]:
        """Renders the matchmaking preferences menu."""
        if platform == "telegram":
            from utils.keyboard import search_pref_menu
            return {
                "text": "🔍 **Matchmaking Preferences**\n\nWho are you looking for today?",
                "reply_markup": search_pref_menu()
            }
        else:
            return {
                "text": "🔍 Who are you looking for?",
                "quick_replies": [
                    {"title": "👫 Anyone", "payload": StateBoundPayload.encode("search_pref_any", "0", state)},
                    {"title": "👨 Male", "payload": StateBoundPayload.encode("search_pref_male", "0", state)},
                    {"title": "👩 Female", "payload": StateBoundPayload.encode("search_pref_female", "0", state)}
                ]
            }
