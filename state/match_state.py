import asyncio
import time
from typing import Dict, List, Set, Optional, Tuple, Any
from utils.logger import logger
from services.distributed_state import distributed_state

from core.engine.state_machine import UnifiedState

class UserState:
    HOME            = UnifiedState.HOME
    SEARCHING       = UnifiedState.SEARCHING
    MATCHED_PENDING = UnifiedState.MATCHED
    CHATTING        = UnifiedState.CHAT_ACTIVE
    VOTING          = UnifiedState.VOTING
    PROFILE_EDIT    = "PROFILE_EDIT"
    CONTENT_REVIEW  = "CONTENT_REVIEW"

    # Define strict allowed transitions
    ALLOWED_TRANSITIONS = UnifiedState.TRANSITIONS
    
    @staticmethod
    def can_transition(current: str, target: str) -> bool:
        if current not in UserState.ALLOWED_TRANSITIONS:
            return False
        return target in UserState.ALLOWED_TRANSITIONS[current]


class MatchState:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(MatchState, cls).__new__(cls)
            cls._instance._init_state()
        return cls._instance

    def _init_state(self):
        self.waiting_queue: List[int] = []
        self.active_chats: Dict[int, int] = {}
        self.user_preferences: Dict[int, str] = {}
        self.rematch_requests: Dict[int, int] = {}
        self.chat_start_times: Dict[int, float] = {}
        self.searching_users: Set[int] = set()
        self.user_ui_messages: Dict[int, List[int]] = {}
        self.ui_history: Dict[int, List[dict]] = {}
        self.user_states: Dict[int, str] = {}
        self.last_button_time: Dict[int, float] = {}
        self.last_message_time: Dict[int, float] = {}
        self.spam_count: Dict[int, int] = {}
        self.mute_until: Dict[int, float] = {}
        self._lock = asyncio.Lock()

    # --- ID Sanitization Helper ---
    def _c_uid(self, user_id: Any) -> int:
        from database.repositories.user_repository import UserRepository
        return UserRepository._sanitize_id(user_id)

    # --- Core State Accessors ---
    async def get_user_state(self, user_id: Any) -> str:
        c_uid = self._c_uid(user_id)
        state = self.user_states.get(c_uid)
        if not state:
            state = await distributed_state.get_user_state(c_uid)
        return state or UnifiedState.HOME

    async def set_user_state(self, user_id: Any, state: str):
        c_uid = self._c_uid(user_id)
        self.user_states[c_uid] = state
        await distributed_state.set_user_state(c_uid, state)

    async def get_partner(self, user_id: Any) -> Optional[int]:
        c_uid = self._c_uid(user_id)
        partner = await distributed_state.get_partner(c_uid)
        if partner: 
            try: return int(partner) if str(partner).isdigit() else partner
            except: return partner
        return self.active_chats.get(c_uid)

    async def set_partner(self, user1: Any, user2: Any):
        u1 = self._c_uid(user1)
        u2 = self._c_uid(user2)
        self.active_chats[u1] = u2
        self.active_chats[u2] = u1
        await distributed_state.set_partner(u1, u2)

    async def clear_partner(self, user_id: Any):
        c_uid = self._c_uid(user_id)
        partner_id = await distributed_state.clear_partner(c_uid)
        self.active_chats.pop(c_uid, None)
        if partner_id:
            p_id = self._c_uid(partner_id)
            self.active_chats.pop(p_id, None)

    async def disconnect(self, user_id: Any) -> Optional[Tuple[Any, float]]:
        """Atomic Disconnect logic."""
        c_uid = self._c_uid(user_id)
        partner_id = await self.get_partner(c_uid)
        if not partner_id: return None
        
        c_pid = self._c_uid(partner_id)
        start_time = await self.get_chat_start(c_uid)
        duration = time.time() - start_time
        
        await self.clear_partner(c_uid)
        await self.set_user_state(c_uid, UnifiedState.VOTING)
        await self.set_user_state(c_pid, UnifiedState.VOTING)
        
        logger.info(f"💔 Match Ended: {c_uid} | {c_pid} after {int(duration)}s")
        return partner_id, duration

    async def is_in_chat(self, user_id: Any) -> bool:
        c_uid = self._c_uid(user_id)
        return await distributed_state.is_in_chat(c_uid)

    # --- Matchmaking Queue Methods ---
    async def add_to_queue(self, user_id: int, priority: bool = False, gender: str = None, pref: str = 'Any', score: float = 50.0):
        async with self._lock:
            c_uid = self._c_uid(user_id)
            if c_uid not in self.waiting_queue:
                self.waiting_queue.append(c_uid)
                self.user_preferences[c_uid] = pref
                data = {
                    'pref': pref,
                    'gender': gender or 'Not specified',
                    'score': score,
                    'priority': priority
                }
                await distributed_state.add_to_queue(c_uid, priority=priority, data=data)
                logger.info(f"⏳ User {c_uid} added to queue. (Pref: {pref}, Priority: {priority})")

    async def remove_from_queue(self, user_id: int):
        async with self._lock:
            await self._remove_from_queue_internal(user_id)

    async def _remove_from_queue_internal(self, user_id: int):
        """Internal helper without lock."""
        c_uid = self._c_uid(user_id)
        if c_uid in self.waiting_queue:
            self.waiting_queue.remove(c_uid)
            self.user_preferences.pop(c_uid, None)
            await distributed_state.remove_from_queue(c_uid)

    async def get_queue_candidates(self) -> List[int]:
        candidates = await distributed_state.get_queue_candidates()
        if candidates: return [int(c) for c in candidates if str(c).isdigit()]
        return self.waiting_queue

    async def get_user_preference(self, user_id: int) -> str:
        c_uid = self._c_uid(user_id)
        pref = self.user_preferences.get(c_uid)
        if not pref:
            data = await distributed_state.get_user_queue_data(c_uid)
            pref = data.get('pref', 'Any') if data else 'Any'
        return pref

    # --- Match Lifecycle ---
    async def find_match(self, user_id: int) -> Optional[int]:
        """Atomic Matchmaking."""
        async with self._lock:
            c_uid = self._c_uid(user_id)
            pref = await self.get_user_preference(c_uid)
            candidates = await self.get_queue_candidates()
            
            for candidate in candidates:
                candidate = int(candidate)
                if candidate == c_uid: continue
                
                cand_pref = await self.get_user_preference(candidate)
                if pref != 'Any' and cand_pref != 'Any' and pref != cand_pref:
                    continue
                
                # Check if distributed state has claim logic
                if hasattr(distributed_state, "atomic_claim_match"):
                    success, _ = await distributed_state.atomic_claim_match(c_uid, candidate)
                    if success:
                        await self._remove_from_queue_internal(c_uid)
                        await self._remove_from_queue_internal(candidate)
                        logger.info(f"🎉 GLOBAL Match Created: {c_uid} <-> {candidate}")
                        return candidate
                else:
                    # Memory fallback
                    await self._add_to_chat_internal(c_uid, candidate)
                    return candidate
            return None

    async def add_to_chat(self, user_id: int, partner_id: int):
        async with self._lock:
            await self._add_to_chat_internal(user_id, partner_id)

    async def _add_to_chat_internal(self, user_id: int, partner_id: int):
        """Internal helper without lock."""
        u1, u2 = self._c_uid(user_id), self._c_uid(partner_id)
        await self.set_partner(u1, u2)
        now = time.time()
        await distributed_state.set_chat_start(u1, now)
        self.chat_start_times[u1] = now
        await distributed_state.set_chat_start(u2, now)
        self.chat_start_times[u2] = now
        await self._remove_from_queue_internal(u1)
        await self._remove_from_queue_internal(u2)

    async def clear_all(self):
        """Clears global and local state."""
        async with self._lock:
            await distributed_state.clear_all()
            self.waiting_queue.clear()
            self.active_chats.clear()
            self.chat_start_times.clear()
            self.searching_users.clear()
            self.rematch_requests.clear()
            self.user_ui_messages.clear()
            self.ui_history.clear()
            self.user_states.clear()
            self.last_button_time.clear()
            self.last_message_time.clear()
            self.spam_count.clear()
            self.mute_until.clear()
            logger.info("🔄 Global State Cleared.")

    async def get_chat_start(self, user_id: Any) -> float:
        c_uid = self._c_uid(user_id)
        if distributed_state.redis:
            val = await distributed_state.redis.get(f"sm:chat_start:{c_uid}")
            return float(val) if val else time.time()
        return self.chat_start_times.get(c_uid, time.time())

    async def get_stats(self) -> Dict[str, int]:
        active_count = 0
        if distributed_state.redis:
            keys = await distributed_state.redis.keys("sm:partner:*")
            active_count = len(keys) // 2
            queue_len = len(await distributed_state.get_queue_candidates())
        else:
            active_count = len(self.active_chats) // 2
            queue_len = len(self.waiting_queue)
        return {"active_chats": active_count, "in_queue": queue_len}

# Global Singleton
match_state = MatchState()
