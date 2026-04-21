import asyncio
import time
from typing import Dict, List, Set, Optional, Tuple
from utils.logger import logger
from services.distributed_state import distributed_state

class UserState:
    HOME = "HOME"
    SEARCHING = "SEARCHING"
    MATCHED_PENDING = "MATCHED_PENDING"
    CHATTING = "CHAT_ACTIVE"
    VOTING = "VOTING"
    PROFILE_EDIT = "PROFILE_EDIT"
    CONTENT_REVIEW = "CONTENT_REVIEW"

    # Define strict allowed transitions
    ALLOWED_TRANSITIONS = {
        HOME: {SEARCHING, PROFILE_EDIT, HOME},
        SEARCHING: {HOME, MATCHED_PENDING, SEARCHING},
        MATCHED_PENDING: {HOME, CHATTING, SEARCHING},
        CHATTING: {VOTING},
        VOTING: {HOME},
        PROFILE_EDIT: {HOME, PROFILE_EDIT, SEARCHING},  # H8: allow direct search from profile edit
        CONTENT_REVIEW: {HOME}
    }
    
    @staticmethod
    def is_valid_transition(current_state: str, new_state: str) -> bool:
        if current_state not in UserState.ALLOWED_TRANSITIONS:
            current_state = UserState.HOME
        return new_state in UserState.ALLOWED_TRANSITIONS.get(current_state, {UserState.HOME})

    # States that ONLY the server/backend may set — never from a client payload.
    SYSTEM_ONLY_STATES = {MATCHED_PENDING, CHATTING, VOTING, CONTENT_REVIEW}

    @staticmethod
    def is_client_settable(new_state: str) -> bool:
        return new_state not in UserState.SYSTEM_ONLY_STATES

    class Session:
        ACTIVE = "ACTIVE"
        ENDED = "ENDED"

class MatchState:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(MatchState, cls).__new__(cls)
            cls._instance._init_state()
        return cls._instance

    def _init_state(self):
        # Create per-instance lock so tests (each with their own event loop) get a fresh lock
        self._lock = asyncio.Lock()
        # Queues and Active Chats (Local fallbacks / legacy support)
        # Note: Production now uses DistributedState (Redis) for these.
        self.waiting_queue: List[int] = []
        self.user_preferences: Dict[int, Dict[str, str]] = {}
        self.active_chats: Dict[int, int] = {}  # user_id -> partner_id
        
        # Transient ID-based tracking (Preserved for backward compatibility with tests/handlers)
        self.user_ui_messages: Dict[int, int] = {}
        self.ui_history: Dict[int, List[int]] = {} # Tracks multiple message IDs for bulk cleanup
        self.searching_users: Set[int] = set()
        self.rematch_requests: Dict[int, int] = {}
        self.user_states: Dict[int, str] = {}
        self.last_button_time: Dict[int, float] = {}
        self.last_message_time: Dict[int, float] = {}
        self.spam_count: Dict[int, int] = {}
        self.mute_until: Dict[int, float] = {}
        
        # Internal state
        self.chat_start_times: Dict[int, float] = {}
        self.bot_start_time = time.time()

    async def add_to_queue(self, user_id: int, priority: bool = False, gender: str = "Not specified", pref: str = "Any", score: float = 50.0) -> bool:
        """Safe add to global queue (Redis-backed)."""
        if await distributed_state.is_in_chat(user_id):
            return False
        
        # Data for sorting/filtering
        match_data = {"gender": gender, "pref": pref, "score": score}
        
        if distributed_state.redis:
            await distributed_state.add_to_queue(user_id, priority=priority, data=match_data)
        else:
            async with self._lock:
                if user_id in self.waiting_queue: self.waiting_queue.remove(user_id)
                self.user_preferences[user_id] = match_data
                if priority: self.waiting_queue.insert(0, user_id)
                else: self.waiting_queue.append(user_id)
                
        logger.info(f"{'⚡' if priority else '⏳'} User {user_id} added to queue. (Pref: {pref})")
        return True

    async def remove_from_queue(self, user_id: int):
        """Safe remove from global queue."""
        if distributed_state.redis:
            await distributed_state.remove_from_queue(user_id)
        else:
            async with self._lock:
                if user_id in self.waiting_queue:
                    self.waiting_queue.remove(user_id)
                    self.user_preferences.pop(user_id, None)
        logger.info(f"🚫 User {user_id} removed from queue.")

    async def find_match(self, user_id: int) -> Optional[int]:
        """Distributed matchmaking attempt — scans global Redis queue if possible."""
        # 1. PRE-LOCK: Fetch candidates and metadata outside the lock to minimize contention
        if distributed_state.redis:
            candidates = await distributed_state.get_queue_candidates()
            if user_id not in candidates: return None
            u_data = await distributed_state.get_user_queue_data(user_id)
        else:
            candidates = [c for c in self.waiting_queue]
            if user_id not in candidates: return None
            u_data = self.user_preferences.get(user_id, {})

        u_gender = u_data.get("gender", "Not specified")
        u_pref = u_data.get("pref", "Any")
        
        for partner_id in candidates:
            if partner_id == user_id: continue
            
            if distributed_state.redis:
                p_data = await distributed_state.get_user_queue_data(partner_id)
            else:
                p_data = self.user_preferences.get(partner_id, {})
            
            p_gender = p_data.get("gender", "Not specified")
            p_pref = p_data.get("pref", "Any")
            
            u_likes_p = (u_pref.lower() == "any") or (u_pref.lower() == p_gender.lower())
            p_likes_u = (p_pref.lower() == "any") or (p_pref.lower() == u_gender.lower())
            
            if u_likes_p and p_likes_u:
                # 2. PRE-LOCK: External DB check (Expensive round-trip)
                try:
                    from database.repositories.blocked_repository import BlockedRepository
                    if await BlockedRepository.is_mutually_blocked(user_id, partner_id):
                        continue
                except Exception as e:
                    logger.warning(f"Block check failed: {e}")
                    continue

                # 3. CRITICAL SECTION: Minimal lock duration for atomic operation
                async with self._lock:
                    if distributed_state.redis:
                        # Redis handles atomic removal/state change via Lua
                        success, reason = await distributed_state.atomic_claim_match(user_id, partner_id)
                        if not success:
                            logger.info(f"Match claim failed during lock: {reason}")
                            continue # Race lost, try next candidate
                    else:
                        # Local Fallback Invariant Check
                        if user_id not in self.waiting_queue or partner_id not in self.waiting_queue:
                            continue
                        
                        self.waiting_queue.remove(user_id)
                        self.user_preferences.pop(user_id, None)
                        self.waiting_queue.remove(partner_id)
                        self.user_preferences.pop(partner_id, None)
                        
                        await distributed_state.set_partner(user_id, partner_id)
                        await distributed_state.set_user_state(user_id, UserState.CHATTING)
                        await distributed_state.set_user_state(partner_id, UserState.CHATTING)

                    # Update local/distributed start times
                    now = time.time()
                    if not distributed_state.redis:
                        await distributed_state.set_chat_start(user_id, now)
                        await distributed_state.set_chat_start(partner_id, now)
                    
                    self.chat_start_times[user_id] = now
                    self.chat_start_times[partner_id] = now
                    
                    logger.info(f"🎉 GLOBAL Match Created: {user_id} <-> {partner_id}")
                    return partner_id
        return None

    async def disconnect(self, user_id: int) -> Optional[Tuple[int, int]]:
        """Disconnects a user and returns (partner_id, duration_seconds)."""
        async with self._lock:
            partner_id = await distributed_state.get_partner(user_id)
            if partner_id:
                if distributed_state.redis:
                    success, start_u, start_p = await distributed_state.atomic_disconnect(user_id, partner_id)
                    if not success:
                        return None
                    # We use start_u as the authoritative snapshot
                    start_time = start_u
                else:
                    partner_id = await distributed_state.clear_partner(user_id)
                    if not partner_id:
                        return None
                    start_time = self.chat_start_times.get(user_id, time.time())
                    await distributed_state.set_user_state(user_id, UserState.HOME)
                    await distributed_state.set_user_state(partner_id, UserState.HOME)

                duration = int(time.time() - start_time)
                
                self.rematch_requests.pop(user_id, None)
                self.rematch_requests.pop(partner_id, None)
                self.chat_start_times.pop(user_id, None)
                self.chat_start_times.pop(partner_id, None)
                
                logger.info(f"💔 Match Ended: {user_id} | {partner_id} after {duration}s")
                return partner_id, duration

            # No active chat — remove from queue inline (lock already held)
            if not distributed_state.redis:
                if user_id in self.waiting_queue:
                    self.waiting_queue.remove(user_id)
                    self.user_preferences.pop(user_id, None)
            else:
                await distributed_state.remove_from_queue(user_id)
            return None

    async def set_rematch(self, user_id: int, partner_id: int) -> tuple[bool, int]:
        """Sets a rematch request via atomic Lua claim. Returns (success, code)."""
        if distributed_state.redis:
            code, reason = await distributed_state.atomic_rematch(user_id, partner_id)
            if code == 1:
                # Sync local start times for consistency if needed (legacy compat)
                now = time.time()
                self.chat_start_times[user_id] = now
                self.chat_start_times[partner_id] = now
                logger.info(f"🔄 Rematch Successful: {user_id} <-> {partner_id}")
                return True, code
            return False, code
        else:
            # Single-worker fallback — original in-memory logic
            async with self._lock:
                self.rematch_requests[user_id] = partner_id
                if self.rematch_requests.get(partner_id) == user_id:
                    if await distributed_state.is_in_chat(partner_id) or await distributed_state.is_in_chat(user_id):
                        return False
                    await distributed_state.set_partner(user_id, partner_id)
                    now = time.time()
                    self.chat_start_times[user_id] = now
                    self.chat_start_times[partner_id] = now
                    # FIX: set both users to CHATTING
                    await distributed_state.set_user_state(user_id, UserState.CHATTING)
                    await distributed_state.set_user_state(partner_id, UserState.CHATTING)
                    self.rematch_requests.pop(user_id, None)
                    self.rematch_requests.pop(partner_id, None)
                    logger.info(f"🔄 Rematch Successful: {user_id} <-> {partner_id}")
                    return True
                return False

    async def add_to_chat(self, user_id: int, partner_id: int):
        async with self._lock:
            if partner_id != 1: await distributed_state.set_partner(user_id, partner_id)
            else: self.active_chats[user_id] = partner_id
            now = time.time()
            # C6: Store in Redis for cross-worker visibility
            await distributed_state.set_chat_start(user_id, now)
            self.chat_start_times[user_id] = now
            if partner_id != 1:
                await distributed_state.set_chat_start(partner_id, now)
                self.chat_start_times[partner_id] = now
            if user_id in self.waiting_queue:
                self.waiting_queue.remove(user_id)
                self.user_preferences.pop(user_id, None)

    async def clear_all(self):
        """Clears global and local state."""
        async with self._lock:
            await distributed_state.clear_queue()
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

    async def is_in_chat(self, user_id: int) -> bool:
        return await distributed_state.is_in_chat(user_id)

    async def get_partner(self, user_id: int) -> Optional[int]:
        partner = await distributed_state.get_partner(user_id)
        if partner is not None: return partner
        return self.active_chats.get(user_id)

    async def get_chat_start(self, user_id: int) -> float:
        """Returns chat start time without removing it (Snapshot)."""
        if distributed_state.redis:
            val = await distributed_state.redis.get(f"sm:chat_start:{user_id}")
            return float(val) if val else time.time()
        return self.chat_start_times.get(user_id, time.time())

    async def set_user_state(self, user_id: int, state: Optional[str]):
        """Engine-Aware State Setter: Increments sm:ver and triggers rehydration."""
        import app_state
        if app_state.engine:
            uid = f"msg_{user_id}" if user_id >= 10**15 else str(user_id)
            await app_state.engine.process_event({
                "event_type": "SET_STATE",
                "user_id": uid,
                "payload": {"new_state": state or "HOME"}
            })
        else:
            # Fallback for startup/pre-init
            await distributed_state.set_user_state(user_id, state)

    async def get_user_state(self, user_id: int) -> Optional[str]:
        return await distributed_state.get_user_state(user_id)

    async def get_stats(self) -> Dict[str, int]:
        active_count = 0
        if distributed_state.redis:
            keys = await distributed_state.redis.keys("chat:*")
            active_count = len(keys) // 2
            queue_len = len(await distributed_state.get_queue_candidates())
        else:
            async with distributed_state._lock:
                active_count = len([k for k in distributed_state._fallback_store if k.startswith("chat:")]) // 2
                queue_len = len(self.waiting_queue)
        
        return {
            "active_chats": active_count,
            "queue_length": queue_len,
            "searching_count": len(self.searching_users)
        }

    async def validate_target(self, target_id: int):
        """C2: Validate that a target user exists and is not blocked.
        Returns (is_valid: bool, reason: str).
        """
        # Echo AI or system placeholders are always valid
        if target_id == 0:
            return True, ""
            
        try:
            from database.repositories.user_repository import UserRepository
            user = await UserRepository.get_by_telegram_id(target_id)
            if not user:
                return False, "Target user no longer exists."
            if user.get("is_banned"):
                return False, "Target user is no longer available."
            return True, ""
        except Exception as e:
            logger.warning(f"validate_target({target_id}) failed: {e}")
            return True, ""  # Fail-open: don't break unrelated flows on DB blip

    async def track_ui_message(self, user_id: int, message_id: int):
        """Adds a message ID to the user's cleanup history."""
        if user_id not in self.ui_history:
            self.ui_history[user_id] = []
        self.ui_history[user_id].append(message_id)
        # Keep local backward compatibility
        self.user_ui_messages[user_id] = message_id

    async def get_ui_history(self, user_id: int) -> List[int]:
        """Returns the list of message IDs to clean up."""
        return self.ui_history.get(user_id, [])

    async def clear_ui_history(self, user_id: int):
        """Clears the tracked history for a user."""
        self.ui_history[user_id] = []

match_state = MatchState()
