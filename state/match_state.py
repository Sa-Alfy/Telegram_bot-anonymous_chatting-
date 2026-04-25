"""
===============================================================================
File: state/match_state.py
Description: The state coordinator bridging memory, Redis, and business logic.

How it works:
MatchState is the central hub for real-time user tracking. It provides a 
high-level API for:
1. State Transitions: Validating moves between states (e.g., HOME to SEARCHING).
2. UI Tracking: Managing Telegram message IDs to allow for clean UI updates 
   without spamming the user's chat history.
3. Redis Integration: Most state lookups (partner ID, current state) are 
   delegated to the DistributedState (Redis) layer for cross-platform sync.

Architecture & Patterns:
- Singleton Pattern: Ensures a single point of truth for state lookups.
- Bridge Pattern: Maintains compatibility between legacy Telegram logic and the
  new Unified Engine architecture.
- Deterministic FSM: Leverages UnifiedState.TRANSITIONS to prevent invalid
  system states.

How to modify:
- To add a new state alias: Update the UserState class.
- To track new UI metadata: Add a tracking dictionary to the MatchState class
  initialization and create a corresponding getter/setter.
- IMPORTANT: For persistent session logic, always modify DistributedState 
  first; MatchState should primarily act as the coordinator.
===============================================================================
"""

import asyncio
import time
from typing import Dict, List, Set, Optional, Tuple, Any
from utils.logger import logger
from services.distributed_state import distributed_state
from core.engine.state_machine import UnifiedState

class UserState:
    """
    User-facing state aliases and transition validation rules.
    """
    HOME            = UnifiedState.HOME
    SEARCHING       = UnifiedState.SEARCHING
    MATCHED_PENDING = UnifiedState.MATCHED
    CHATTING        = UnifiedState.CHAT_ACTIVE
    VOTING          = UnifiedState.VOTING
    PROFILE_EDIT    = "PROFILE_EDIT"
    CONTENT_REVIEW  = "CONTENT_REVIEW"

    # Define strict allowed transitions (Source of Truth: UnifiedState)
    ALLOWED_TRANSITIONS = UnifiedState.TRANSITIONS
    
    @staticmethod
    def can_transition(current: str, target: str) -> bool:
        if current not in UserState.ALLOWED_TRANSITIONS:
            return False
        return target in UserState.ALLOWED_TRANSITIONS[current]

    @staticmethod
    def is_client_settable(state: str) -> bool:
        return UnifiedState.is_client_settable(state)


class MatchState:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(MatchState, cls).__new__(cls)
            cls._instance._init_state()
        return cls._instance

    def _init_state(self):
        # Authoritative state is now in Redis/DistributedState.
        # Local state is only for per-instance utility (rate limiting, UI history).
        self.rematch_requests: Dict[int, int] = {}
        self.user_ui_messages: Dict[int, int] = {}
        self.ui_history: Dict[int, List[dict]] = {}
        self.last_button_time: Dict[int, float] = {}
        self.last_message_time: Dict[int, float] = {}
        self.spam_count: Dict[int, int] = {}
        self.mute_until: Dict[int, float] = {}
        self._lock = asyncio.Lock()

    # --- ID Sanitization Helper ---
    def _c_uid(self, user_id: Any) -> int:
        from database.repositories.user_repository import UserRepository
        return UserRepository._sanitize_id(user_id)

    # --- Core State Accessors (Authoritative via DistributedState) ---
    async def get_user_state(self, user_id: Any) -> str:
        # Try RAW ID first (preserves msg_ prefix for Redis keys)
        state = await distributed_state.get_user_state(str(user_id))
        if state: return state
        
        # Fallback to sanitized integer
        c_uid = self._c_uid(user_id)
        if str(c_uid) != str(user_id):
            state = await distributed_state.get_user_state(c_uid)
        
        return state or UnifiedState.HOME

    async def set_user_state(self, user_id: Any, state: str):
        # Use RAW ID for Redis keys
        raw_id = str(user_id)
        old_state = await self.get_user_state(raw_id)
        
        from core.telemetry import EventLogger, TelemetryEvent, InvariantEngine
        partner_id = await self.get_partner(raw_id)
        
        # We still sanitize for Telemetry/Logging to keep DB IDs consistent
        c_uid = self._c_uid(user_id)
        InvariantEngine.check_state_transition(c_uid, old_state, state, partner_id)
        
        EventLogger.log_event(
            event=TelemetryEvent.STATE_CHANGE, layer="state_machine", status=TelemetryEvent.INFO,
            user_id=c_uid, data={"old_state": old_state, "new_state": state}
        )
        
        await distributed_state.set_user_state(raw_id, state)

    async def get_partner(self, user_id: Any) -> Optional[Any]:
        # Try RAW ID first
        raw_id = str(user_id)
        partner = await distributed_state.get_partner(raw_id)
        if partner: return partner
        
        # Fallback to sanitized integer
        c_uid = self._c_uid(user_id)
        if str(c_uid) != raw_id:
            partner = await distributed_state.get_partner(c_uid)
            
        return partner

    async def set_partner(self, user1: Any, user2: Any):
        # Always use Raw IDs for Redis partnership keys
        await distributed_state.set_partner(str(user1), str(user2))

    async def clear_partner(self, user_id: Any):
        # Clear both Raw and Sanitized (to be safe during migration)
        raw_id = str(user_id)
        await distributed_state.clear_partner(raw_id)
        
        c_uid = self._c_uid(user_id)
        if str(c_uid) != raw_id:
            await distributed_state.clear_partner(c_uid)

    async def disconnect(self, user_id: Any) -> dict:
        """Atomic Disconnect logic."""
        c_uid = self._c_uid(user_id)
        return await distributed_state.atomic_disconnect(c_uid)

    async def is_in_chat(self, user_id: Any) -> bool:
        c_uid = self._c_uid(user_id)
        return await distributed_state.is_in_chat(c_uid)

    # --- Matchmaking Queue Methods ---
    async def add_to_queue(self, user_id: int, priority: bool = False, gender: str = None, pref: str = 'Any', score: float = 50.0) -> bool:
        c_uid = self._c_uid(user_id)
        data = {
            'pref': pref,
            'gender': gender or 'Not specified',
            'score': score,
            'priority': priority
        }
        success = await distributed_state.add_to_queue(c_uid, priority=priority, data=data)
        logger.info(f"⏳ User {c_uid} added to queue. (Pref: {pref}, Priority: {priority})")
        return success

    async def remove_from_queue(self, user_id: int):
        c_uid = self._c_uid(user_id)
        await distributed_state.remove_from_queue(c_uid)

    async def get_queue_candidates(self) -> List[int]:
        candidates = await distributed_state.get_queue_candidates()
        if candidates: 
            return [int(c) for c in candidates if str(c).isdigit()]
        return []

    async def validate_target(self, target_id: Any) -> Tuple[bool, str]:
        """Validates that a target user exists and is not banned."""
        if not target_id or target_id == 0:
            return True, "OK"
        
        from database.repositories.user_repository import UserRepository
        user = await UserRepository.get_by_telegram_id(target_id)
        if not user:
            return False, "Target user no longer exists."
        if user.get("is_banned"):
            return False, "Target user is no longer available."
        return True, "OK"

    async def get_user_preference(self, user_id: int) -> str:
        c_uid = self._c_uid(user_id)
        data = await distributed_state.get_user_queue_data(c_uid)
        return data.get('pref', 'Any') if data else 'Any'

    async def track_ui_message(self, user_id: int, message_id: int):
        """Tracks the latest UI message for editing/deletion."""
        c_uid = self._c_uid(user_id)
        self.user_ui_messages[c_uid] = message_id
        if c_uid not in self.ui_history:
            self.ui_history[c_uid] = []
        self.ui_history[c_uid].append({"id": message_id, "time": time.time()})

    async def clear_all(self):
        """Clears global and local state."""
        async with self._lock:
            await distributed_state.clear_all()
            self.rematch_requests.clear()
            self.user_ui_messages.clear()
            self.ui_history.clear()
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
        return time.time()

    async def get_stats(self) -> Dict[str, int]:
        if distributed_state.redis:
            keys = await distributed_state.redis.keys("sm:partner:*")
            active_count = len(keys) // 2
            queue_len = len(await distributed_state.get_queue_candidates())
        else:
            # For local testing without Redis
            active_count = 0
            queue_len = 0
        return {"active_chats": active_count, "in_queue": queue_len}

# Global Singleton
match_state = MatchState()
