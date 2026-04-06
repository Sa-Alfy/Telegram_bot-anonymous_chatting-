import time
from typing import Dict, Any, Optional
from database.repositories.user_repository import UserRepository
from services.event_manager import get_active_event
from services.user_service import UserService

# Configuration for seasonal shop items
SHOP_ITEMS = {
    "exp_boost_3h": {"name": "✨ 3h XP Booster", "cost": 100, "duration": 10800, "type": "booster"},
    "coin_boost_3h": {"name": "💰 3h Coin Booster", "cost": 150, "duration": 10800, "type": "booster"},
    "priority_1h": {"name": "⚡ 1h Priority Match", "cost": 250, "duration": 3600, "type": "priority"},
    "badge_seasonal": {"name": "🏅 Seasonal Badge", "cost": 500, "type": "cosmetic"}
}

class EconomyService:
    @staticmethod
    async def get_dynamic_cost(user_id: int, feature_type: str, partner_id: int = None) -> int:
        """Calculates the dynamic cost of a feature based on user and partner profiles."""
        user = await UserRepository.get_by_telegram_id(user_id)
        if not user:
            return 15 # Default safe cost
            
        active_event = get_active_event()
        base_costs = {"identity_reveal": 15, "priority_match": 5, "peek_stats": 5}
        
        if feature_type == "identity_reveal" and partner_id:
            partner = await UserRepository.get_by_telegram_id(partner_id)
            if partner:
                # Cost: 15 base + Level/2 + 10 if VIP
                cost = 15 + (partner.get("level", 1) // 2)
                if partner.get("vip_status"):
                    cost += 10
                return int(cost)
                
        cost = base_costs.get(feature_type, 10)
        
        # 1. Level Scaling: +5% cost per 5 levels
        level_multiplier = 1 + (user.get("level", 1) // 5) * 0.05
        cost *= level_multiplier
        
        # 2. VIP Discount: -50% exclusively for identity reveals
        if user.get("vip_status") and feature_type == "identity_reveal":
            cost *= 0.5
            
        # 3. Global Event Multiplier: e.g., "Economy Crash" event triples costs
        if active_event.get("multiplier", 1.0) > 1.0 and active_event.get("type") == "mini":
            if active_event["name"] == "💰 Coin Rush":
                cost *= 0.5 # 50% off during Coin Rush!
                
        return max(1, int(cost))

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
            update_data["coin_booster"] = {
                "active": True,
                "expires_at": time.time() + item["duration"]
            }
        elif item["type"] == "priority":
            update_data["priority_pack"] = {
                "active": True,
                "expires_at": time.time() + item["duration"]
            }
        elif item["type"] == "cosmetic":
            purchases = user.get("coin_shop_purchases", [])
            purchases.append(item_key)
            update_data["coin_shop_purchases"] = purchases
            
        await UserRepository.update(user_id, **update_data)
        return {"success": True, "message": f"Successfully bought {item['name']}!"}
