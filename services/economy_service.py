import time
from services.user_service import get_user_profile, add_coins, save_profiles
from services.event_manager import get_active_event

# Configuration for seasonal shop items
SHOP_ITEMS = {
    "exp_boost_3h": {"name": "✨ 3h XP Booster", "cost": 100, "duration": 10800, "type": "booster"},
    "coin_boost_3h": {"name": "💰 3h Coin Booster", "cost": 150, "duration": 10800, "type": "booster"},
    "priority_1h": {"name": "⚡ 1h Priority Match", "cost": 250, "duration": 3600, "type": "priority"},
    "badge_seasonal": {"name": "🏅 Seasonal Badge", "cost": 500, "type": "cosmetic"}
}

def get_dynamic_cost(user_id: int, feature_type: str, partner_id: int = None) -> int:
    """Calculates the cost of a feature based on Level, VIP, and Active Events."""
    profile = get_user_profile(user_id)
    active_event = get_active_event()
    
    # Base costs from profile dynamic_costs config
    base_costs = profile.get("dynamic_costs", {
        "identity_reveal": 15,
        "priority_match": 5,
        "peek_stats": 5
    })
    
    cost = base_costs.get(feature_type, 10)
    
    # 1. Level Scaling: +5% cost per 5 levels
    level_multiplier = 1 + (profile.get("level", 1) // 5) * 0.05
    cost *= level_multiplier
    
    # 2. VIP Discount: -20% cost for VIP users
    if profile.get("vip", False):
        cost *= 0.8
        
    # 3. Global Event Multiplier: e.g., "Economy Crash" event triples costs
    if active_event.get("multiplier", 1.0) > 1.0 and active_event.get("type") == "mini":
        # Some mini-events might actually lower costs
        if active_event["name"] == "💰 Coin Rush":
            cost *= 0.5 # 50% off during Coin Rush!
            
    # 4. Partner-based scaling (if applicable)
    if partner_id:
        partner = get_user_profile(partner_id)
        if partner.get("vip"):
            cost += 5 # Extra cost to reveal a VIP
            
    return max(1, int(cost))

async def buy_shop_item(user_id: int, item_key: str) -> dict:
    """Handles purchase logic for seasonal shop."""
    if item_key not in SHOP_ITEMS:
        return {"success": False, "message": "Item not found."}
        
    item = SHOP_ITEMS[item_key]
    profile = get_user_profile(user_id)
    
    if profile["coins"] < item["cost"]:
        return {"success": False, "message": "Insufficient coins."}
        
    # Deduct coins
    add_coins(user_id, -item["cost"])
    
    # Apply perk
    if item["type"] == "booster":
        profile["coin_booster"] = {
            "active": True,
            "expires_at": time.time() + item["duration"]
        }
    elif item["type"] == "priority":
        profile["priority_pack"] = {
            "active": True,
            "expires_at": time.time() + item["duration"]
        }
    elif item["type"] == "cosmetic":
        if "seasonal_purchases" not in profile:
            profile["coin_shop_purchases"] = []
        profile["coin_shop_purchases"].append(item_key)
        
    await save_profiles()
    return {"success": True, "message": f"Successfully bought {item['name']}!"}
