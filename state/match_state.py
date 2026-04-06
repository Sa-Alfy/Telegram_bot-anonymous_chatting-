import asyncio
import time
from typing import Dict, List, Set, Optional, Tuple
from utils.logger import logger

class MatchState:
    _instance = None
    _lock = asyncio.Lock()

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(MatchState, cls).__new__(cls)
            cls._instance._init_state()
        return cls._instance

    def _init_state(self):
        # Queues and Active Chats
        self.waiting_queue: List[int] = []
        self.user_preferences: Dict[int, Dict[str, str]] = {}
        self.active_chats: Dict[int, int] = {}  # user_id -> partner_id
        
        # Transient UI State
        self.user_ui_messages: Dict[int, int] = {}
        self.searching_users: Set[int] = set()
        self.rematch_requests: Dict[int, int] = {}
        self.user_states: Dict[int, str] = {}
        
        # Timing and Rate Limiting
        self.chat_start_times: Dict[int, float] = {}
        self.last_button_time: Dict[int, float] = {}
        self.last_message_time: Dict[int, float] = {}
        self.spam_count: Dict[int, int] = {}
        self.mute_until: Dict[int, float] = {}
        
        # Metadata
        self.bot_start_time = time.time()

    async def add_to_queue(self, user_id: int, priority: bool = False, gender: str = "Not specified", pref: str = "Any") -> bool:
        """Safe add to queue with priority support and filtering."""
        async with self._lock:
            if user_id in self.active_chats:
                return False
            
            if user_id in self.waiting_queue:
                self.waiting_queue.remove(user_id)
                
            self.user_preferences[user_id] = {"gender": gender, "pref": pref}
            
            if priority:
                self.waiting_queue.insert(0, user_id)
                logger.info(f"⚡ User {user_id} added to priority queue. (Pref: {pref})")
            else:
                self.waiting_queue.append(user_id)
                logger.info(f"⏳ User {user_id} added to queue. (Pref: {pref})")
            return True

    async def remove_from_queue(self, user_id: int):
        """Safe remove from queue."""
        async with self._lock:
            if user_id in self.waiting_queue:
                self.waiting_queue.remove(user_id)
                self.user_preferences.pop(user_id, None)
                logger.info(f"🚫 User {user_id} removed from queue.")

    async def find_match(self, user_id: int) -> Optional[int]:
        """Attempt to find a partner for the user, respecting filters."""
        async with self._lock:
            if user_id not in self.waiting_queue:
                return None
                
            user_data = self.user_preferences.get(user_id, {"gender": "Not specified", "pref": "Any"})
            u_gender = user_data["gender"]
            u_pref = user_data["pref"]
            
            for partner_id in self.waiting_queue:
                if partner_id != user_id:
                    p_data = self.user_preferences.get(partner_id, {"gender": "Not specified", "pref": "Any"})
                    p_gender = p_data["gender"]
                    p_pref = p_data["pref"]
                    
                    # Check mutual compatibility
                    u_likes_p = (u_pref == "Any") or (u_pref == p_gender)
                    p_likes_u = (p_pref == "Any") or (p_pref == u_gender)
                    
                    if u_likes_p and p_likes_u:
                        # Match Found!
                        self.waiting_queue.remove(user_id)
                        self.waiting_queue.remove(partner_id)
                        self.user_preferences.pop(user_id, None)
                        self.user_preferences.pop(partner_id, None)
                        
                        self.active_chats[user_id] = partner_id
                        self.active_chats[partner_id] = user_id
                        
                        now = time.time()
                        self.chat_start_times[user_id] = now
                        self.chat_start_times[partner_id] = now
                        
                        logger.info(f"🤝 Match Created: {user_id} <-> {partner_id}")
                        return partner_id
            return None

    async def disconnect(self, user_id: int) -> Optional[Tuple[int, int]]:
        """Disconnects a user and returns (partner_id, duration_seconds)."""
        async with self._lock:
            partner_id = self.active_chats.pop(user_id, None)
            if partner_id:
                self.active_chats.pop(partner_id, None)
                
                start_time = self.chat_start_times.pop(user_id, time.time())
                self.chat_start_times.pop(partner_id, None)
                
                duration = int(time.time() - start_time)
                
                # Cleanup other transient state
                self.rematch_requests.pop(user_id, None)
                self.rematch_requests.pop(partner_id, None)
                
                logger.info(f"💔 Match Ended: {user_id} | {partner_id} after {duration}s")
                return partner_id, duration
            
            # Also ensure they are removed from queue
            if user_id in self.waiting_queue:
                self.waiting_queue.remove(user_id)
            
            return None

    async def set_rematch(self, user_id: int, partner_id: int) -> bool:
        """Sets a rematch request and checks for a mutual match."""
        async with self._lock:
            self.rematch_requests[user_id] = partner_id
            
            if self.rematch_requests.get(partner_id) == user_id:
                # Mutual Rematch!
                if partner_id in self.active_chats or user_id in self.active_chats:
                    return False
                
                # Move to active chats
                self.active_chats[user_id] = partner_id
                self.active_chats[partner_id] = user_id
                
                now = time.time()
                self.chat_start_times[user_id] = now
                self.chat_start_times[partner_id] = now
                
                # Cleanup rematch requests
                self.rematch_requests.pop(user_id, None)
                self.rematch_requests.pop(partner_id, None)
                
                logger.info(f"🔄 Rematch Successful: {user_id} <-> {partner_id}")
                return True
            return False

    async def add_to_chat(self, user_id: int, partner_id: int):
        """Directly adds a user to a chat (used for debug/echo mode)."""
        async with self._lock:
            self.active_chats[user_id] = partner_id
            if partner_id != 1:  # Don't track virtual echo partner
                self.active_chats[partner_id] = user_id
            now = time.time()
            self.chat_start_times[user_id] = now
            if partner_id != 1:
                self.chat_start_times[partner_id] = now
            # Remove from queue if present
            if user_id in self.waiting_queue:
                self.waiting_queue.remove(user_id)

    async def clear_all(self):
        """Clears all active chats, queues, and transient state."""
        async with self._lock:
            self.waiting_queue.clear()
            self.active_chats.clear()
            self.chat_start_times.clear()
            self.searching_users.clear()
            self.rematch_requests.clear()
            self.user_states.clear()
            self.last_button_time.clear()
            self.last_message_time.clear()
            logger.info("🔄 All state cleared.")

    def is_in_chat(self, user_id: int) -> bool:
        return user_id in self.active_chats

    def get_partner(self, user_id: int) -> Optional[int]:
        return self.active_chats.get(user_id)

    def set_user_state(self, user_id: int, state: Optional[str]):
        if state is None:
            self.user_states.pop(user_id, None)
        else:
            self.user_states[user_id] = state

    def get_user_state(self, user_id: int) -> Optional[str]:
        return self.user_states.get(user_id)

# Global instance
match_state = MatchState()
