# ═══════════════════════════════════════════════════════════════════════
# FILE: services/economy_service.py  (PATCHED)
# PURPOSE: Economy logic — adding missing activate_booster method
# STATUS: MODIFIED (added activate_booster)
# ═══════════════════════════════════════════════════════════════════════

import time
from typing import Dict, Any, Optional
from database.repositories.user_repository import UserRepository
from services.event_manager import get_active_event
from services.user_service import UserService

# Configuration for seasonal shop items
SHOP_ITEMS = {
    "exp_boost_3h":   {"name": "✨ 3h XP Booster",     "cost": 100,  "duration": 10800, "type": "booster", "key": "xp_booster"},
    "coin_boost_3h":  {"name": "💰 3h Coin Booster",    "cost": 150,  "duration": 10800, "type": "booster", "key": "coin_booster"},
    "priority_1h":    {"name": "⚡ 1h Priority Match",  "cost": 250,  "duration": 3600,  "type": "priority", "key": "priority_pack"},
    "badge_seasonal": {"name": "🏅 Seasonal Badge",      "cost": 500,                     "type": "cosmetic"}
}

# Configuration for social gifts
GIFT_TYPES = {
    "rose": {"name": "🌹 Rose", "cost": 10, "effect": "karma_1", "desc": "+1 Karma for the receiver."},
    "diamond": {"name": "💎 Diamond", "cost": 100, "effect": "xp_boost", "desc": "2x XP for 1 hour for both of you."},
    "treasure": {"name": "👑 Treasure Chest", "cost": 500, "effect": "treasure_boost", "desc": "2x Coins for 3 hours + Reveals their Bio & Location to you!"}
}

class EconomyService:
    @staticmethod
    async def get_dynamic_cost(user_id: int, feature_type: str, partner_id: int = None) -> int:
        """Calculates the dynamic cost of a feature based on user and partner profiles."""
        user = await UserRepository.get_by_telegram_id(user_id)
        if not user:
            return 15  # Default safe cost

        active_event = get_active_event()
        base_costs = {"identity_reveal": 15, "priority_match": 5, "peek_stats": 5}
        if feature_type == "identity_reveal" and partner_id:
            from services.distributed_state import distributed_state
            msg_count = await distributed_state.get_message_count(user_id, partner_id)
            
            # Tiered base cost based on engagement
            if msg_count < 50:
                return -1 # Locked
            elif msg_count < 200:
                base = 10 # Tier 1
            elif msg_count < 500:
                base = 25 # Tier 2
            else:
                base = 50 # Tier 3
            
            partner = await UserRepository.get_by_telegram_id(partner_id)
            cost = base + (partner.get("level", 1) // 2)
            if partner.get("vip_status"):
                cost += 10
        else:
            cost = base_costs.get(feature_type, 10)

        # Level scaling: +5% cost per 5 levels
        level_multiplier = 1 + (user.get("level", 1) // 5) * 0.05
        cost *= level_multiplier

        # VIP discount: -50% on identity reveals
        if user.get("vip_status") and feature_type == "identity_reveal":
            cost *= 0.5

        # Event discount: "Coin Rush" halves prices
        if active_event.get("multiplier", 1.0) > 1.0 and active_event.get("type") == "mini":
            if active_event["name"] == "💰 Coin Rush":
                cost *= 0.5

        return max(1, int(cost))

    @staticmethod
    async def activate_booster(user_id: int, booster_type: str, duration_seconds: int) -> bool:
        """Activates a timed booster (coin multiplier or priority queue) for a user.

        Args:
            user_id: The Telegram user ID.
            booster_type: 'coin' for 2x coin earnings, 'priority' for priority queue.
            duration_seconds: How many seconds the booster remains active.

        Returns:
            True on success, False if user not found.
        """
        user = await UserRepository.get_by_telegram_id(user_id)
        if not user:
            return False

        current_booster = user.get("coin_booster", {}) if booster_type == "coin" else user.get("priority_pack", {})
        current_expires = current_booster.get("expires_at", 0)
        base_time = max(time.time(), current_expires)
        expires_at = base_time + duration_seconds

        if booster_type == "coin":
            await UserRepository.update(user_id, coin_booster={
                "active": True,
                "expires_at": expires_at
            })
        elif booster_type == "priority":
            await UserRepository.update(user_id, priority_pack={
                "active": True,
                "expires_at": expires_at
            })

        return True

    @staticmethod
    async def buy_shop_item(user_id: int, item_key: str) -> Dict[str, Any]:
        """Handles purchase logic for seasonal shop."""
        if item_key not in SHOP_ITEMS:
            return {"success": False, "message": "Item not found."}

        item = SHOP_ITEMS[item_key]
        user = await UserRepository.get_by_telegram_id(user_id)

        if not user or user["coins"] < item["cost"]:
            return {"success": False, "message": "Insufficient coins."}

        # Deduct coins
        await UserRepository.increment_coins(user_id, -item["cost"])

        # Apply perk
        update_data = {}
        if item["type"] == "booster":
            b_key = item["key"]
            current = user.get(b_key, {})
            base = max(time.time(), current.get("expires_at", 0))
            update_data[b_key] = {
                "active": True,
                "expires_at": base + item["duration"]
            }
        elif item["type"] == "priority":
            b_key = item.get("key", "priority_pack")
            current = user.get(b_key, {})
            base = max(time.time(), current.get("expires_at", 0))
            update_data[b_key] = {
                "active": True,
                "expires_at": base + item["duration"]
            }
        elif item["type"] == "cosmetic":
            purchases = user.get("coin_shop_purchases", [])
            purchases.append(item_key)
            update_data["coin_shop_purchases"] = purchases

        await UserRepository.update(user_id, **update_data)
        return {"success": True, "message": f"Successfully bought {item['name']}!"}

    @staticmethod
    async def send_gift(sender_id: int, receiver_id: int, gift_key: str) -> Dict[str, Any]:
        """Handles sending a gift to another user and applying effects."""
        from database.repositories.gift_repository import GiftRepository
        
        if gift_key not in GIFT_TYPES:
            return {"success": False, "message": "Invalid gift type."}
            
        gift = GIFT_TYPES[gift_key]
        sender = await UserRepository.get_by_telegram_id(sender_id)
        
        if not sender or sender.get("coins", 0) < gift["cost"]:
            return {"success": False, "message": "Insufficient coins."}
            
        # Deduct coins from sender
        if not await UserService.deduct_coins(sender_id, gift["cost"]):
            return {"success": False, "message": "Transaction failed."}
            
        # Log the gift
        await GiftRepository.log_gift(sender_id, receiver_id, gift_key, gift["cost"])
        
        # Apply effects
        effect = gift["effect"]
        reveal_data = None
        
        if effect == "karma_1":
            # Add 1 karma to receiver
            receiver = await UserRepository.get_by_telegram_id(receiver_id)
            if receiver:
                new_karma = receiver.get("karma", 0) + 1
                await UserRepository.update(receiver_id, karma=new_karma)
                
        elif effect == "xp_boost":
            # 2x XP for 1 hour (3600s) for both
            await EconomyService.activate_booster(sender_id, "xp", 3600)
            await EconomyService.activate_booster(receiver_id, "xp", 3600)
            
        elif effect == "treasure_boost":
            # 2x Coins for 3 hours (10800s) for both
            await EconomyService.activate_booster(sender_id, "coin", 10800)
            await EconomyService.activate_booster(receiver_id, "coin", 10800)
            
            # Reveal Bio and Location to sender
            receiver = await UserRepository.get_by_telegram_id(receiver_id)
            if receiver:
                reveal_data = {
                    "bio": receiver.get("bio", "No bio provided."),
                    "location": receiver.get("location", "Secret")
                }
                from database.repositories.reveal_repository import RevealRepository
                await RevealRepository.log_reveal(sender_id, receiver_id, "gift_treasure", gift["cost"])
                
        # Update generosity for sender
        new_generosity = sender.get("generosity", 0) + gift["cost"]
        await UserRepository.update(sender_id, generosity=new_generosity)
        
        return {
            "success": True, 
            "message": f"Successfully sent {gift['name']}!",
            "reveal_data": reveal_data
        }

# ═══════════════════════════════════════════════════════════════════════
# END OF economy_service.py
# ═══════════════════════════════════════════════════════════════════════
