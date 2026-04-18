"""
DEPRECATED MODULE — state/memory.py

All state has been migrated to state/match_state.MatchState
which is backed by services/distributed_state.DistributedState (Redis + fallback).

If you are importing from this module, update your import to use:
    from state.match_state import match_state

This file is kept to prevent ImportError from any legacy path, but the
variables below are stubs that will NOT be kept in sync with the live system.
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
