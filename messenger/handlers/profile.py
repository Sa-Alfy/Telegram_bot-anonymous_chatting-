# ═══════════════════════════════════════════════════════════════════════
# FILE: messenger/handlers/profile.py
# PURPOSE: Messenger profile management, onboarding, and GDPR actions
# ═══════════════════════════════════════════════════════════════════════

from messenger_api import send_message, send_quick_replies, send_button_template, send_generic_template
from adapters.messenger.ui_factory import (
    CONSENT_BUTTONS, get_gender_buttons, get_age_buttons, get_goal_buttons,
    get_interests_skip_buttons, get_start_menu_buttons, get_profile_dashboard_card
)
from database.repositories.user_repository import UserRepository
from state.match_state import match_state, UserState

# We import _send_hero_start and _notify_user locally where needed to avoid circular import

# ─────────────────────────────────────────────────────────────────────
# Consent Flow
# ─────────────────────────────────────────────────────────────────────

def show_consent_screen(psid: str):
    """Display privacy/ToS consent screen to new users using a persistent button template."""
    text = (
        "🎭 Welcome to Neonymo!\n\n"
        "Before you begin, please review our policies:\n\n"
        "🛡️ Privacy: /privacy\n"
        "📋 Terms: /terms\n\n"
        "By tapping 'I Accept', you agree to our policies."
    )
    # Button Templates support up to 3 buttons. We'll use 2: Accept and Decline.
    buttons = [
        {"type": "postback", "title": "✅ I Accept", "payload": "CONSENT_ACCEPT:0:HOME"},
        {"type": "postback", "title": "❌ Decline",  "payload": "CONSENT_DECLINE:0:HOME"}
    ]
    send_button_template(psid, text, buttons)

def handle_terms(psid: str):
    """Show the full Terms of Service text."""
    text = (
        "⚖️ Terms of Service\n\n"
        "1. You must be 18+ years old.\n"
        "2. No harassment, bullying, or hate speech.\n"
        "3. No spam, advertisements, or scams.\n"
        "4. No illegal content or solicitation.\n"
        "5. We reserve the right to ban users who violate these rules.\n\n"
        "For the full legal text, visit: https://neonymo-chat.onrender.com/terms"
    )
    send_message(psid, text)

def handle_privacy(psid: str):
    """Show the Privacy Policy text."""
    text = (
        "🛡️ Privacy Policy\n\n"
        "1. We do not store your real identity.\n"
        "2. Messages are relayed in real-time and not logged permanently.\n"
        "3. We use a hashed ID to manage your session and stats.\n"
        "4. You can delete your data anytime via Settings.\n\n"
        "For the full legal text, visit: https://neonymo-chat.onrender.com/privacy"
    )
    send_message(psid, text)


async def handle_consent_accept(psid: str, virtual_id: int, user: dict):
    """Record user consent and proceed to main menu (Async)."""
    # Import locally to avoid circular import with messenger_handlers
    from messenger_handlers import _send_hero_start
    await UserRepository.set_consent(virtual_id)
    _send_hero_start(psid, user.get("coins", 0), user.get("is_guest", True))


def handle_consent_decline(psid: str):
    """Handle consent decline."""
    send_message(
        psid,
        "We respect your decision. You won't be able to use the service without accepting our policies."
    )


# ─────────────────────────────────────────────────────────────────────
# Profile Setup & Onboarding
# ─────────────────────────────────────────────────────────────────────

async def handle_profile_setup(psid: str, virtual_id: int):
    """Route: Show dashboard for existing users, onboarding for guests (Async)."""
    user = await UserRepository.get_by_telegram_id(virtual_id)
    is_guest = user.get("is_guest", True) if user else True
    
    if is_guest:
        # New user → start onboarding from gender selection
        await _start_onboarding(psid, virtual_id)
    else:
        # Existing user → show profile dashboard card
        await _show_profile_dashboard(psid, virtual_id, user)


async def _show_profile_dashboard(psid: str, virtual_id: int, user: dict):
    """Show the rich profile dashboard card for existing users (Async)."""
    current_state = await match_state.get_user_state(virtual_id) or UserState.HOME
    card = get_profile_dashboard_card(user, current_state)
    send_generic_template(psid, card)


async def _start_onboarding(psid: str, virtual_id: int):
    """Start gender-selection flow for new users (Async)."""
    current_state = await match_state.get_user_state(virtual_id) or UserState.HOME
    send_quick_replies(
        psid,
        "👤 Create Your Profile\n\nTo enhance your matchmaking experience, select your gender:",
        get_gender_buttons(current_state)
    )


async def handle_edit_profile(psid: str, virtual_id: int):
    """Re-enter onboarding flow for existing users who want to edit (Async)."""
    current_state = await match_state.get_user_state(virtual_id) or UserState.HOME
    send_quick_replies(
        psid,
        "✏️ Edit Profile\n\nLet's update your info. Select your gender:",
        get_gender_buttons(current_state)
    )


async def handle_set_photo_prompt(psid: str, virtual_id: int):
    """Prompt user to send a photo for their profile (Async)."""
    await match_state.set_user_state(virtual_id, "awaiting_photo")
    send_message(
        psid,
        "📷 **Set Profile Photo**\n\n"
        "Send me a photo and I'll set it as your profile picture.\n"
        "This photo will be shown if you choose to reveal your identity.\n\n"
        "💡 Just send an image in this chat!"
    )


async def handle_set_gender(psid: str, virtual_id: int, gender: str):
    """Save gender and ask for age (Async)."""
    await UserRepository.update(virtual_id, gender=gender, is_guest=False)
    current_state = await match_state.get_user_state(virtual_id) or UserState.HOME
    send_quick_replies(
        psid,
        f"✅ Gender set to {gender.capitalize()}!\n\nNow, select your age bracket:",
        get_age_buttons(current_state)
    )


async def handle_set_age(psid: str, virtual_id: int, age: str):
    """Save age and ask for goal (Async)."""
    await UserRepository.update(virtual_id, age=age)
    current_state = await match_state.get_user_state(virtual_id) or UserState.HOME
    send_quick_replies(
        psid,
        f"✅ Age group {age} selected!\n\nWhat are you hoping to find here?",
        get_goal_buttons(current_state)
    )


async def handle_set_goal(psid: str, virtual_id: int, goal: str):
    """Save goal and ask for interests (Async)."""
    await UserRepository.update(virtual_id, looking_for=goal)
    await match_state.set_user_state(virtual_id, "awaiting_interests")
    current_state = await match_state.get_user_state(virtual_id) or UserState.HOME
    send_quick_replies(
        psid,
        f"✅ Got it!\n\nWhat are your hobbies?\n(Type them in the chat below)",
        get_interests_skip_buttons(current_state)
    )


async def handle_interests_skip(psid: str, virtual_id: int):
    """Skip interests and ask for location (Async)."""
    await UserRepository.update(virtual_id, interests="None specified")
    await match_state.set_user_state(virtual_id, "awaiting_location")
    send_message(psid, "📍 Where are you from?\n(Type your location in the chat below)")


# ─────────────────────────────────────────────────────────────────────
# Data Deletion (GDPR)
# ─────────────────────────────────────────────────────────────────────

def handle_delete_data(psid: str, virtual_id: int):
    """User-initiated data deletion."""
    send_quick_replies(
        psid,
        "⚠️ Delete Your Data\n\nPermanently erase your profile and stats?",
        [
            {"title": "🗑 Yes, Delete", "payload": "CONFIRM_DELETE:0:HOME"},
            {"title": "❌ Cancel", "payload": "CMD_START:0:HOME"},
        ]
    )


async def handle_confirm_delete(psid: str, virtual_id: int):
    """Execute user data deletion (Async)."""
    partner_id = await match_state.get_partner(virtual_id)
    if partner_id:
        from services.matchmaking import MatchmakingService
        from messenger_handlers import _notify_user
        await MatchmakingService.disconnect(virtual_id)
        await _notify_user(partner_id, "💔 Your chat partner has disconnected.")

    await match_state.remove_from_queue(virtual_id)
    await UserRepository.soft_delete_user_data(virtual_id)

    send_message(psid, "✅ Data Deleted.")
