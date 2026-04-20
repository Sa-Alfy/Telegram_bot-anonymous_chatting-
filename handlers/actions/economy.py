import time
from typing import Dict, Any, Optional
from pyrogram import Client, types
from database.repositories.user_repository import UserRepository
from database.repositories.session_repository import SessionRepository
from services.user_service import UserService
from services.economy_service import EconomyService
from utils.keyboard import start_menu, priority_pack_menu, booster_menu, confirm_reveal_menu, chat_menu, peek_menu, seasonal_shop_menu
from handlers.start import get_start_text

class EconomyHandler:
    @staticmethod
    async def handle_priority_search(client: Client, user_id: int) -> Dict[str, Any]:
        """Handles priority matchmaking initiation."""
        user = await UserRepository.get_by_telegram_id(user_id)
        if not user:
            return {"alert": "Error fetching user.", "show_alert": True}

        # Check for active priority packs or available priority matches
        timed_pack = user.get("priority_pack", {})
        is_timed_active = timed_pack.get("active") and timed_pack.get("expires_at", 0) > time.time()
        has_matches = user.get("priority_matches", 0) > 0
        
        if is_timed_active or has_matches or await UserService.deduct_coins(user_id, 5):
            if is_timed_active:
                alert = "⚡ Using your Unlimited Priority Pack!"
            elif has_matches:
                await UserRepository.update(user_id, priority_matches=user["priority_matches"] - 1)
                alert = "⚡ Using 1 Priority Match from your pack!"
            else:
                alert = "⚡ Priority activated! (5 coins deducted)"
                
            from services.matchmaking import MatchmakingService
            from utils.keyboard import search_menu, chat_menu
            success = await MatchmakingService.add_to_queue(user_id, gender_pref="Any")
            if not success:
                return {"alert": "You are already in a chat!", "show_alert": True}
            partner_id = await MatchmakingService.find_partner(client, user_id)
            from utils.renderer import Renderer
            if partner_id:
                # Notify partner is handled by initialize_match usually, but for Priority we do it here too
                return Renderer.render_match_found("telegram", partner_id, is_rematch=False, show_safety=True)
            
            response = Renderer.render_searching_ui("telegram", UserState.HOME)
            response["start_animation"] = True
            return response
        else:
            return {"alert": "❌ Not enough coins for Priority Match (5 coins required)!", "show_alert": True}

    @staticmethod
    async def handle_buy_pack(client: Client, user_id: int, count: int) -> Dict[str, Any]:
        """Handles purchasing priority match packs."""
        prices = {5: 20, 15: 50, 50: 150}
        price = prices.get(count)
        if not price:
            return {"alert": "❌ Invalid pack count!", "show_alert": True}
            
        if await UserService.deduct_coins(user_id, price):
            user = await UserRepository.get_by_telegram_id(user_id)
            new_count = (user.get("priority_matches", 0) or 0) + count
            await UserRepository.update(user_id, priority_matches=new_count)
            return {
                "alert": f"✅ Purchased {count} Priority Matches!",
                "show_alert": True,
                "text": get_start_text(user["coins"] - price, user.get("is_guest", 1)),
                "reply_markup": start_menu(user.get("is_guest", 1))
            }
        else:
            return {"alert": "❌ Not enough coins!", "show_alert": True}

    @staticmethod
    async def handle_reveal(client: Client, user_id: int) -> Dict[str, Any]:
        """Initiates the identity reveal confirm dialog."""
        from state.match_state import match_state
        partner_id = await match_state.get_partner(user_id)
        if not partner_id:
            return {"alert": "❌ Partner disconnected!", "show_alert": True}
            
        cost = await EconomyService.get_dynamic_cost(user_id, "identity_reveal", partner_id)
        user = await UserRepository.get_by_telegram_id(user_id)
        partner = await UserRepository.get_by_telegram_id(partner_id)
        
        if user.get("is_guest", 1):
            return {"alert": "❌ You must create a profile to unmask others!", "show_alert": True}
            
        if user["coins"] < cost:
            return {"alert": f"❌ You need {cost} coins to unmask this partner!", "show_alert": True}
            
        return {
            "text": f"🔍 **Unmask Partner**\n\nThis will reveal your partner's identity to you for **{cost} coins**.\n"
                    f"(Cost based on partner's Level {partner.get('level', 1)}{' + VIP' if partner.get('vip_status') else ''})\n\nContinue?",
            "reply_markup": confirm_reveal_menu(cost, partner_id, UserState.CHATTING)
        }

    @staticmethod
    async def handle_confirm_reveal(client: Client, user_id: int, cost: int) -> Dict[str, Any]:
        """Performs the identity reveal."""
        from state.match_state import match_state
        partner_id = await match_state.get_partner(user_id)
        if not partner_id:
            return {"alert": "❌ Partner disconnected!", "show_alert": True}
            
        if await UserService.deduct_coins(user_id, cost):
            partner = await UserRepository.get_by_telegram_id(partner_id)
            
            if not partner:
                if partner_id == 1:
                    reveal_text = (
                        f"🌟 **Identity Unmasked!** 🌟\n"
                        f"━━━━━━━━━━━━━━━━━━\n"
                        f"🆔 **ID:** `1`\n"
                        f"🏷 **Name:** System AI (Echo)\n"
                        f"📍 **Location:** Motherboard Core\n"
                        f"**Bio:** I am a simple diagnostic reflection of your own thoughts. I don't eat, sleep, or feel cold."
                    )
                else:
                    return {"alert": "❌ Profile data not found.", "show_alert": True}
            else:
                age = partner.get('age', 'Unknown')
                goal = partner.get('looking_for', 'Unknown')
                interests = partner.get('interests', 'None specified')
                gender = partner.get('gender', 'Secret')
                reveal_text = (
                    f"🌟 **Identity Unmasked!** 🌟\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"🆔 **ID:** `{partner_id}`\n"
                    f"🏷 **Name:** {partner.get('first_name')}\n"
                    f"👩‍🦰 **Gender:** {gender}\n"
                    f"🎂 **Age:** {age}\n"
                    f"🎯 **Goal:** {goal}\n"
                    f"🎮 **Interests:** {interests}\n"
                    f"📍 **Location:** {partner.get('location', 'Secret')}\n"
                    f"**Bio:** {partner.get('bio', 'No bio provided.')}"
                )
            
            # Log to reveal history
            if partner_id != 1:
                from database.repositories.reveal_repository import RevealRepository
                await RevealRepository.log_reveal(user_id, partner_id, "full", cost)
            
            return {
                "text": "✅ Partner identity revealed above!",
                "reply_markup": chat_menu(UserState.CHATTING, partner_id),
                "special_action": "send_photo",
                "photo": partner.get("profile_photo") if partner else None,
                "caption": reveal_text,
                "notify_partner": {
                    "target_id": partner_id,
                    "text": "⚠️ **Someone just unmasked your identity!**\nThey have seen your profile details (Name, Location, Bio)."
                } if partner_id != 1 else None
            }
        else:
            return {"alert": "❌ Not enough coins!", "show_alert": True}
    @staticmethod
    async def handle_priority_packs(client: Client, user_id: int) -> Dict[str, Any]:
        """Shows the priority packs menu."""
        return {
            "text": "📦 **Priority Match Packs**\n\nChoose a pack to skip the queue and find partners instantly:",
            "reply_markup": priority_pack_menu()
        }

    @staticmethod
    async def handle_booster_menu(client: Client, user_id: int) -> Dict[str, Any]:
        """Shows the coin booster menu."""
        return {
            "text": "🚀 **Coin Boosters**\n\nDouble your earnings with these active boosters:",
            "reply_markup": booster_menu()
        }

    @staticmethod
    async def handle_buy_booster(client: Client, user_id: int, type_id: int) -> Dict[str, Any]:
        """Handles purchasing coin boosters."""
        costs = {1: 50, 3: 120} # 1h, 3h
        cost = costs.get(type_id, 50)
        
        if await UserService.deduct_coins(user_id, cost):
            # Log booster in user profile (Assumption: economy_service handles duration)
            await EconomyService.activate_booster(user_id, "coin", type_id * 3600)
            return {"alert": f"🚀 {type_id}h Coin Booster Activated!", "show_alert": True}
        return {"alert": "❌ Not enough coins!", "show_alert": True}

    @staticmethod
    async def handle_buy_timed_priority(client: Client, user_id: int, hours: int) -> Dict[str, Any]:
        """Handles purchasing unlimited priority for a duration."""
        costs = {1: 30, 3: 75, 24: 200}
        cost = costs.get(hours, 30)
        
        if await UserService.deduct_coins(user_id, cost):
            await EconomyService.activate_booster(user_id, "priority", hours * 3600)
            return {"alert": f"⚡ {hours}h Unlimited Priority Activated!", "show_alert": True}
        return {"alert": "❌ Not enough coins!", "show_alert": True}

    @staticmethod
    async def handle_seasonal_shop(client: Client, user_id: int) -> Dict[str, Any]:
        """Displays the seasonal shop."""
        from utils.keyboard import seasonal_shop_menu
        user = await UserRepository.get_by_telegram_id(user_id)
        coins = user.get("coins", 0) if user else 0
        return {
            "text": f"🛍 **Seasonal Profile Shop**\n\nStand out by purchasing exclusive Profile Badges that others will see when they unmask you!\n\n💰 **Your Balance:** {coins} coins",
            "reply_markup": seasonal_shop_menu(coins)
        }

    @staticmethod
    async def handle_buy_shop_badge(client: Client, user_id: int, badge_type: str) -> Dict[str, Any]:
        """Handles purchasing a cosmetic badge or VIP subscription."""
        prices = {"vip": 500, "og": 300, "whale": 1000}
        badge_names = {"vip": "👑 30-Day VIP", "og": "🔥 OG", "whale": "🐋 Whale"}
        
        cost = prices.get(badge_type)
        if not cost:
            return {"alert": "❌ Invalid item!", "show_alert": True}

        user = await UserRepository.get_by_telegram_id(user_id)
        if user["coins"] < cost:
            return {"alert": "❌ Not enough coins!", "show_alert": True}

        # Check if they already own it
        owned_badges = user.get("badges", [])
        if badge_type in owned_badges and badge_type != "vip":
            return {"alert": "📦 You already own this badge!", "show_alert": True}

        if await UserService.deduct_coins(user_id, cost):
            if badge_type not in owned_badges:
                owned_badges.append(badge_type)
                
            updates = {"badges": owned_badges}
            # Special case for VIP logic
            if badge_type == "vip":
                import time
                updates["vip_status"] = True
                updates["vip_expires_at"] = int(time.time()) + (30 * 86400) # 30 Days expiration

            await UserRepository.update(user_id, **updates)
            
            from utils.renderer import Renderer
            return {
                "alert": f"🎉 Unlocked: {badge_names[badge_type]}!", 
                "show_alert": True,
                **Renderer.render_profile_menu("telegram", user.get("state", "HOME")) # Re-render dashboard
            }
        return {"alert": "❌ Transaction failed.", "show_alert": True}
