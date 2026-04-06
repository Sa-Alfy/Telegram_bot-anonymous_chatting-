import asyncio
import time
from pyrogram import Client

from state.match_state import match_state
from database.repositories.user_repository import UserRepository
from services.matchmaking import MatchmakingService
from utils.keyboard import end_menu
from utils.helpers import update_user_ui
from utils.logger import logger
from utils.ui_formatters import get_progression_text

async def start_session_manager(client: Client):
    """Background task to automatically disconnect inactive chat pairs."""
    logger.info("Session Manager started.")
    
    while True:
        try:
            # Check every 60 seconds
            await asyncio.sleep(60)
            
            now = int(time.time())
            inactivity_limit = 5 * 60 # 5 minutes
            
            # Identify pairs where both users are inactive
            to_disconnect = []
            processed_users = set()
            
            # Use MatchState to get active chats safely
            async with match_state._lock:
                chats_snapshot = list(match_state.active_chats.items())
            
            for user_id, partner_id in chats_snapshot:
                if user_id in processed_users:
                    continue
                
                u1 = await UserRepository.get_by_telegram_id(user_id)
                u2 = await UserRepository.get_by_telegram_id(partner_id)
                
                if not u1 or not u2:
                    continue

                u1_idle = now - u1.get("last_active", 0)
                u2_idle = now - u2.get("last_active", 0)
                
                # If BOTH users have been inactive for more than the limit
                if u1_idle >= inactivity_limit and u2_idle >= inactivity_limit:
                    to_disconnect.append((user_id, partner_id))
                    processed_users.add(user_id)
                    processed_users.add(partner_id)
            
            for u1, u2 in to_disconnect:
                logger.info(f"Auto-disconnecting {u1} and {u2} for inactivity.")
                
                # Perform disconnect (updates coins and total chat time)
                stats = await MatchmakingService.disconnect(u1)
                
                # Notify users
                if stats:
                    duration = stats['duration_minutes']
                    
                    for uid, is_u1 in [(u1, True), (u2, False)]:
                        earned = stats['coins_earned'] if is_u1 else stats['u2_coins_earned']
                        xp = stats['xp_earned'] if is_u1 else stats['u2_xp_earned']
                        
                        msg = (
                            f"❌ **Chat ended due to inactivity.**\n"
                            f"⏱ **Session Summary**\n───────────────\n"
                            f"⌛ **Duration:** {duration} min\n"
                            f"💰 **Coins Earned:** +{earned}\n"
                            f"📈 **XP Gained:** +{xp}\n"
                            f"────────────────"
                        )
                        msg += get_progression_text(stats, is_u1)
                        
                        try:
                            await update_user_ui(client, uid, msg, end_menu())
                        except:
                            pass
                    
        except Exception as e:
            logger.error(f"Session manager encountered an error: {e}")
            await asyncio.sleep(10) # Recovery delay
