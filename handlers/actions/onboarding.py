from typing import Dict, Any
from pyrogram import Client
from database.repositories.user_repository import UserRepository
from utils.keyboard import gender_menu, age_menu, goal_menu, interests_skip_menu, location_skip_menu, bio_skip_menu, start_menu
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
        """Sets the user's gender and moves to the age step."""
        gender = gender.strip().capitalize()
        await UserRepository.update(user_id, gender=gender, is_guest=False)
        return {
            "text": f"✅ **Gender set to {gender}!**\n\nNow, please select your age bracket:",
            "reply_markup": age_menu()
        }

    @staticmethod
    async def handle_set_age(client: Client, user_id: int, age: str) -> Dict[str, Any]:
        """Sets the user's age and moves to the goal step."""
        await UserRepository.update(user_id, age=age)
        return {
            "text": f"✅ **Age group {age} selected!**\n\nWhat are you hoping to find here?",
            "reply_markup": goal_menu()
        }

    @staticmethod
    async def handle_set_goal(client: Client, user_id: int, goal: str) -> Dict[str, Any]:
        """Sets the user's goal and moves to the interests step."""
        await UserRepository.update(user_id, looking_for=goal)
        return {
            "text": f"✅ **Got it!**\n\nWhat are your hobbies or interests?\n(Type them in the chat below, e.g., 'Gaming, Travel, Music')",
            "reply_markup": interests_skip_menu(),
            "set_state": "awaiting_interests"
        }

    @staticmethod
    async def handle_interests_skip(client: Client, user_id: int) -> Dict[str, Any]:
        """Skips interests and moves to location."""
        await UserRepository.update(user_id, interests="None specified")
        return {
            "text": "⏩ **Interests Skipped!**\n\nNext, tell us your location (City/Country) or skip this step:",
            "reply_markup": location_skip_menu(),
            "set_state": "awaiting_location"
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
