from typing import Dict, Any
from pyrogram import Client
from database.repositories.user_repository import UserRepository
from utils.keyboard import gender_menu, location_skip_menu, bio_skip_menu, start_menu
from utils.logger import logger

class OnboardingHandler:
    @staticmethod
    async def handle_start(client: Client, user_id: int) -> Dict[str, Any]:
        """Initiates the profile creation flow."""
        return {
            "text": "👤 **Create Your Profile**\n\nTo enhance your matchmaking experience, let's set up your profile. First, select your gender:",
            "reply_markup": gender_menu()
        }

    @staticmethod
    async def handle_skip(client: Client, user_id: int) -> Dict[str, Any]:
        """Skips the onboarding process for now."""
        user = await UserRepository.get_by_telegram_id(user_id)
        return {
            "text": "⏩ **Onboarding Skipped**\n\nYou can always complete your profile later from the Stats menu.",
            "reply_markup": start_menu(user['is_guest'] if user else True)
        }

    @staticmethod
    async def handle_set_gender(client: Client, user_id: int, gender: str) -> Dict[str, Any]:
        """Sets the user's gender and moves to the location step."""
        await UserRepository.update(user_id, gender=gender)
        return {
            "text": f"✅ **Gender set to {gender.capitalize()}!**\n\nNext, tell us your location (City/Country) or skip this step:",
            "reply_markup": location_skip_menu(),
            "set_state": "awaiting_location" # State handled in handlers/chat.py
        }

    @staticmethod
    async def handle_location_skip(client: Client, user_id: int) -> Dict[str, Any]:
        """Skips the location step and moves to the bio step."""
        await UserRepository.update(user_id, location="Unknown")
        return {
            "text": "📍 **Location Skipped!**\n\nFinally, write a short bio about yourself (max 100 chars) or skip this step:",
            "reply_markup": bio_skip_menu(),
            "set_state": "awaiting_bio"
        }

    @staticmethod
    async def handle_bio_skip(client: Client, user_id: int) -> Dict[str, Any]:
        """Completes the onboarding by skipping the bio step."""
        await UserRepository.update(user_id, bio="No bio provided.")
        user = await UserRepository.get_by_telegram_id(user_id)
        return {
            "text": "✨ **Profile Setup Complete!**\n\nYou are now ready to find anonymous partners.",
            "reply_markup": start_menu(user['is_guest'] if user else True),
            "set_state": "idle"
        }
