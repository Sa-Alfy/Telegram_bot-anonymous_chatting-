import asyncio
import time
import random
from pyrogram import Client
from utils.logger import logger
from database.repositories.user_repository import UserRepository

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
            if active_event["id"] and current_time > active_event["ends_at"]:
                await end_current_event(app)
            
            if not active_event["id"]:
                if random.random() < 0.1:
                    await start_mini_event(app)
                # Weekly tournament check (optional)
            
            await asyncio.sleep(300) 
        except Exception as e:
            logger.error(f"Error in event manager: {e}")
            await asyncio.sleep(60)

async def start_mini_event(app: Client):
    """Starts a short-term global buff."""
    global active_event
    event_id = f"mini_{int(time.time())}"
    duration = 3600
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

async def start_weekly_tournament(app: Client):
    """Starts a long-term competitive event."""
    global active_event
    event_id = f"week_{int(time.time())}"
    duration = 604800
    
    active_event = {
        "id": event_id,
        "type": "tournament",
        "name": "🏆 Weekly Grand Match",
        "multiplier": 1.1,
        "ends_at": time.time() + duration
    }
    
    # Reset event points for all users (This requires a repository method)
    # Reset event points for all users using PostgreSQL JSONB operations
    from database.connection import db
    query = """
    UPDATE users 
    SET json_data = jsonb_set(
        COALESCE(NULLIF(json_data, ''), '{}')::jsonb, 
        '{seasonal_events}', 
        jsonb_build_object('event_points', 0, 'current_event_id', $1)::jsonb
    )::text
    """
    await db.execute(query, (event_id,))
    
    logger.info("Tournament Started: Weekly Grand Match")

async def end_current_event(app: Client):
    """Cleans up after an event finishes."""
    global active_event
    logger.info(f"Event Ended: {active_event['name']}")
    
    active_event = {
        "id": None,
        "type": None,
        "name": "No Active Event",
        "multiplier": 1.0,
        "ends_at": 0
    }

def get_active_event() -> dict:
    return active_event

async def add_event_points(user_id: int, points: int):
    """Adds points to a user's seasonal score."""
    if not active_event["id"] or active_event["type"] != "tournament":
        return
        
    user = await UserRepository.get_by_telegram_id(user_id)
    if not user: return
    
    events = user.get("seasonal_events", {})
    events["event_points"] = events.get("event_points", 0) + points
    events["participation_count"] = events.get("participation_count", 0) + 1
    
    await UserRepository.update(user_id, seasonal_events=events)
