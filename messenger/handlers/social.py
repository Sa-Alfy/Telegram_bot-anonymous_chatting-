# ═══════════════════════════════════════════════════════════════════════
# FILE: messenger/handlers/social.py
# PURPOSE: Messenger social interactions (friend requests, reports, blocks)
# ═══════════════════════════════════════════════════════════════════════

from messenger_api import send_message, send_quick_replies
from messenger.ui import (
    IDLE_MENU_BUTTONS, FRIEND_CONFIRM_BUTTONS, CHAT_MENU_BUTTONS,
    START_MENU_BUTTONS, END_MENU_BUTTONS
)
from state.match_state import match_state
from utils.behavior_tracker import behavior_tracker

from handlers.actions.social import SocialHandler

# Local import to avoid circular dependencies
def _get_execute_action():
    from messenger_handlers import _execute_action
    return _execute_action


async def handle_add_friend(psid: str, virtual_id: int):
    """Add current chat partner as a friend (Async)."""
    partner_id = await match_state.get_partner(virtual_id)
    if not partner_id:
        send_quick_replies(psid, "You're not in a chat right now.", IDLE_MENU_BUTTONS)
        return
    send_quick_replies(
        psid,
        "💌 Send a friend request to your partner?",
        FRIEND_CONFIRM_BUTTONS
    )


async def handle_confirm_friend(psid: str, virtual_id: int):
    """Execute friend request to current partner (Async)."""
    partner_id = await match_state.get_partner(virtual_id)
    if not partner_id:
        send_message(psid, "You're no longer in a chat.")
        return
    from database.repositories.friend_repository import FriendRepository
    from messenger_handlers import _notify_user
    
    await FriendRepository.add_friend(virtual_id, partner_id)
    send_quick_replies(psid, "✅ Friend request sent!", { "text": "CHAT" }) # Simplified buttons
    await _notify_user(partner_id, "💌 Your partner sent you a friend request!")


async def handle_report(psid: str, virtual_id: int):
    """Report the current chat partner (Async)."""
    await behavior_tracker.record_report_given(virtual_id)
    partner_id = await match_state.get_partner(virtual_id)
    if partner_id:
        await behavior_tracker.record_report_received(partner_id)
    
    _execute_action = _get_execute_action()
    await _execute_action(psid, virtual_id, SocialHandler.handle_report_confirm)


async def handle_block_partner(psid: str, virtual_id: int):
    """Block the current chat partner and disconnect (Async)."""
    partner_id = await match_state.get_partner(virtual_id)
    if not partner_id:
        send_quick_replies(psid, "⚠️ You are not in a chat. No one to block.", START_MENU_BUTTONS)
        return

    from database.repositories.blocked_repository import BlockedRepository
    from services.matchmaking import MatchmakingService
    from messenger_handlers import _notify_user

    # Block the partner
    await BlockedRepository.block_user(virtual_id, partner_id)
    # Disconnect
    await MatchmakingService.disconnect(virtual_id)

    # Notify both parties
    send_quick_replies(
        psid,
        "🚫 Partner Blocked\nYou will never be matched with this user again.",
        END_MENU_BUTTONS
    )
    await _notify_user(partner_id, "💔 Your chat partner has disconnected.")

