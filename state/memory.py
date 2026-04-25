"""
===============================================================================
File: state/memory.py
Description: [DEPRECATED] Legacy in-memory state storage.

How it works:
This module was used to store user states and queues in local RAM before the
system migrated to a distributed architecture. It now serves only as a 
placeholder to prevent ImportErrors during the refactoring process.

Architecture & Patterns:
- Legacy Stub: No longer used for live operations.
- Warning System: Issues a DeprecationWarning on import.

How to modify:
- DO NOT ADD NEW LOGIC HERE.
- All state management must happen in state/match_state.py or 
  services/distributed_state.py.
- If you find a file importing from here, refactor it to use MatchState.
===============================================================================
"""
import warnings
warnings.warn(
    "state.memory is deprecated. Use state.match_state.match_state instead.",
    DeprecationWarning,
    stacklevel=2
)

# Stub references (not live — for import compatibility only)
from typing import Dict, List, Set
import asyncio
import time

bot_start_time: float = time.time()
waiting_queue: List[int] = []
active_chats: Dict[int, int] = {}
user_ui_messages: Dict[int, int] = {}
last_message_time: Dict[int, float] = {}
last_button_time: Dict[int, float] = {}
chat_start_times: Dict[int, float] = {}
searching_users: Set[int] = set()
rematch_requests: Dict[int, int] = {}
queue_lock = asyncio.Lock()
user_states: Dict[int, str] = {}
