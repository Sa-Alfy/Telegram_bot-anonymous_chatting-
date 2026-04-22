# ═══════════════════════════════════════════════════════════════════════
# FILE: messenger/handlers/matchmaking.py
# PURPOSE: Messenger matchmaking operations (search, stop, next, cancel)
# ═══════════════════════════════════════════════════════════════════════

from messenger_api import send_quick_replies, send_message
from adapters.messenger.ui_factory import (
    get_search_pref_buttons, get_start_menu_buttons, 
    get_retry_search_buttons, get_chat_menu_buttons
)
from state.match_state import match_state, UserState
from utils.rate_limiter import rate_limiter
from utils.renderer import StateBoundPayload
from utils.ui_formatters import get_match_found_text

# Import global shared logic
from handlers.actions.matching import MatchingHandler
from utils.behavior_tracker import behavior_tracker

# Local import to avoid circular dependencies
def _get_execute_action():
    from messenger_handlers import _execute_action
    return _execute_action

async def handle_search(psid: str, virtual_id: int, user: dict):
    """Show gender-preference menu freely — Smart Cooldown Strategy (Async)."""
    current_state = await match_state.get_user_state(virtual_id) or UserState.HOME
    
    # Check if already searching or chatting to prevent redundant UI actions
    if current_state == UserState.SEARCHING:
        text = "🔍 Looking for someone... (I'll ping you when found)"
        buttons = [{"title": "❌ Cancel", "payload": StateBoundPayload.encode("cancel_search", "0", current_state)}]
        # Note: We append extra context for redundant hits
        send_quick_replies(psid, f"⚠️ Already searching!\n{text}", buttons)
        return
    
    if current_state == UserState.CHATTING:
        partner_id = await match_state.get_partner(virtual_id)
        text = get_match_found_text(is_rematch=False, include_safety=False)
        buttons = get_chat_menu_buttons(UserState.CHATTING, partner_id)
        send_quick_replies(psid, f"❌ Already in a chat!\n{text}", buttons)
        return

    # No cooldown gate here — allow opening the menu freely!
    # Protection only applies when they actually pick a preference button.
    text = "🔍 Who are you looking for?"
    buttons = get_search_pref_buttons(current_state)
    send_quick_replies(psid, text, buttons)


async def handle_search_with_pref(psid: str, virtual_id: int, user: dict, pref: str):
    """Add user to queue (Async). Cooldown protection happens here."""
    _execute_action = _get_execute_action()
    await _execute_action(psid, virtual_id, MatchingHandler.handle_search_with_pref, pref)


async def handle_stop(psid: str, virtual_id: int):
    """Disconnect from current chat (Async).
    Note: behavior_tracker.record_disconnect is called inside MatchmakingService.disconnect()
    via behavior_engine.record_disconnect() — do NOT call it again here (H1 fix).
    """
    _execute_action = _get_execute_action()
    await _execute_action(psid, virtual_id, MatchingHandler.handle_stop)


async def handle_next(psid: str, virtual_id: int, user: dict):
    """Skip to next partner (Async)."""
    _execute_action = _get_execute_action()
    await _execute_action(psid, virtual_id, MatchingHandler.handle_next)


async def handle_cancel_search(psid: str, virtual_id: int):
    """Cancel active queue search (Async)."""
    _execute_action = _get_execute_action()
    await _execute_action(psid, virtual_id, MatchingHandler.handle_cancel)
