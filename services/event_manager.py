import asyncio
import time
import random
from pyrogram import Client
from utils.logger import logger
from state.persistence import user_profiles, save_profiles

# Global state for current active event
active_event = {
    "id": None,
    "type": None,
    "name": "No Active Event",
    "multiplier": 1.0,
    "ends_at": 0
}

async def start_event_manager(app: Client):
    """Background task to manage global events."""
    logger.info("📅 Event Manager started.")
    while True:
        try:
            current_time = time.time()
            
            # 1. Check if current event expired
            if active_event["id"] and current_time > active_event["ends_at"]:
                await end_current_event(app)
            
            # 2. Random Chance to start a Mini-Event (Daily) if none active
            if not active_event["id"]:
                # 10% chance every check (check happens every 5 mins)
                if random.random() < 0.1:
                    await start_mini_event(app)
                elif is_new_week():
                    await start_weekly_tournament(app)
            
            await asyncio.sleep(300) # Check every 5 minutes
        except Exception as e:
            logger.error(f"Error in event manager: {e}")
            await asyncio.sleep(60)

def is_new_week():
    """Simple check for tournament rotation (e.g., every Monday)."""
    # For simulation, we'll check if it's been > 7 days since last tournament in state
    # In a real bot, we'd use datetime.now().weekday()
    return False # Handled manually or via scheduler later

async def start_mini_event(app: Client):
    """Starts a short-term global buff."""
    global active_event
    event_id = f"mini_{int(time.time())}"
    duration = 3600 # 1 hour
    multiplier = random.choice([1.5, 2.0])
    name = random.choice(["🔥 Happy Hour", "💰 Coin Rush", "✨ XP Frenzy"])
    
    active_event = {
        "id": event_id,
        "type": "mini",
        "name": name,
        "multiplier": multiplier,
        "ends_at": time.time() + duration
    }
    
    logger.info(f"Event Started: {name} ({multiplier}x)")
    # Notify all active users or just log for now
    # We'll implement a broadcast later if needed

async def start_weekly_tournament(app: Client):
    """Starts a long-term competitive event."""
    global active_event
    event_id = f"week_{int(time.time())}"
    duration = 604800 # 1 week
    
    active_event = {
        "id": event_id,
        "type": "tournament",
        "name": "🏆 Weekly Grand Match",
        "multiplier": 1.1,
        "ends_at": time.time() + duration
    }
    
    # Reset event points for all users
    for profile in user_profiles.values():
        profile["seasonal_events"]["event_points"] = 0
        profile["seasonal_events"]["current_event_id"] = event_id
        
    await save_profiles()
    logger.info("Tournament Started: Weekly Grand Match")

async def end_current_event(app: Client):
    """Cleans up after an event finishes."""
    global active_event
    logger.info(f"Event Ended: {active_event['name']}")
    
    # If it was a tournament, we could distribute rewards here
    if active_event["type"] == "tournament":
        # logic for top 10 rewards...
        pass
        
    active_event = {
        "id": None,
        "type": None,
        "name": "No Active Event",
        "multiplier": 1.0,
        "ends_at": 0
    }

def get_active_event() -> dict:
    """Helper to access event data from other services."""
    return active_event

def add_event_points(user_id: int, points: int):
    """Adds points to a user's seasonal score."""
    if not active_event["id"] or active_event["type"] != "tournament":
        return
        
    from services.user_service import get_user_profile
    profile = get_user_profile(user_id)
    profile["seasonal_events"]["event_points"] += points
    profile["seasonal_events"]["participation_count"] += 1
