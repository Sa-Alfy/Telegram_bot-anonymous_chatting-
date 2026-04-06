import asyncio
import time
from pyrogram import Client
from state.memory import active_chats
from services.matchmaking import disconnect
from services.user_service import get_user_profile
from utils.keyboard import end_menu
from utils.helpers import update_user_ui
from utils.logger import logger

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
            
            # Snapshots of the chats to avoid 'dictionary changed size during iteration'
            chats_snapshot = list(active_chats.items())
            
            for user_id, partner_id in chats_snapshot:
                if user_id in processed_users:
                    continue
                
                u1_profile = get_user_profile(user_id)
                u2_profile = get_user_profile(partner_id)
                
                u1_idle = now - u1_profile.get("last_active", 0)
                u2_idle = now - u2_profile.get("last_active", 0)
                
                # If BOTH users have been inactive for more than the limit
                if u1_idle >= inactivity_limit and u2_idle >= inactivity_limit:
                    to_disconnect.append((user_id, partner_id))
                    processed_users.add(user_id)
                    processed_users.add(partner_id)
            
            for u1, u2 in to_disconnect:
                logger.info(f"Auto-disconnecting {u1} and {u2} for inactivity.")
                
                # Perform disconnect (updates coins and total chat time)
                stats = await disconnect(u1)
                
                # Notify users
                if stats:
                    duration = stats['duration_minutes']
                    earned = stats['coins_earned']
                    
                    # Import progression formatter
                    from handlers.callback import get_progression_text
                    
                    u1_earned = stats['coins_earned']
                    u1_xp = stats['xp_earned']
                    
                    msg1 = (
                        f"❌ **Chat ended due to inactivity.**\n"
                        f"⏱ **Session Summary**\n───────────────\n"
                        f"⌛ **Duration:** {duration} min\n"
                        f"💰 **Coins Earned:** +{u1_earned}\n"
                        f"📈 **XP Gained:** +{u1_xp}\n"
                        f"────────────────"
                    )
                    msg1 += get_progression_text(stats, True)
                    
                    msg2 = (
                        f"❌ **Chat ended due to inactivity.**\n"
                        f"⏱ **Session Summary**\n───────────────\n"
                        f"⌛ **Duration:** {duration} min\n"
                        f"💰 **Coins Earned:** +{u1_earned}\n"
                        f"📈 **XP Gained:** +{u1_xp}\n"
                        f"────────────────"
                    )
                    msg2 += get_progression_text(stats, False)
                    
                    try:
                        await update_user_ui(client, u1, msg1, end_menu())
                    except Exception:
                        pass
                        
                    try:
                        await update_user_ui(client, u2, msg2, end_menu())
                    except Exception:
                        pass
                    
        except Exception as e:
            logger.error(f"Session manager encountered an error: {e}")
            await asyncio.sleep(10) # Recovery delay
