from typing import Dict, List, Set
import asyncio

# In-memory queue of user IDs waiting for a partner
waiting_queue: List[int] = []

# Mapping of user_id -> partner_id
active_chats: Dict[int, int] = {}

# Mapping of user_id -> UI message ID
user_ui_messages: Dict[int, int] = {}

# User action timestamps for cooldown (user_id -> timestamp)
user_cooldowns: Dict[int, float] = {}

# Mapping of user_id -> chat start timestamp
chat_start_times: Dict[int, float] = {}

# Set of users currently in the matching animation loop
searching_users: Set[int] = set()

# Mapping of user_id -> partner_id they want a rematch with
rematch_requests: Dict[int, int] = {}

# Mutex for thread-safe/async-safe matchmaking
queue_lock = asyncio.Lock()
