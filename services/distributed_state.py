import os
import time
import asyncio
import json
from typing import Optional
from utils.logger import logger

class DistributedState:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(DistributedState, cls).__new__(cls)
            cls._instance._init_state()
        return cls._instance

    def _init_state(self):
        self.redis = None
        self._fallback_store = {} # Memory fallback if Redis not configured
        self._lock = asyncio.Lock()          # General fallback store lock
        self._action_lock = asyncio.Lock()   # Separate lock for action lock ops (M1 fix)
        
    async def connect(self):
        redis_url = os.getenv("REDIS_URL")
        if redis_url:
            try:
                import redis.asyncio as redis
                self.redis = redis.from_url(redis_url, decode_responses=True)
                await self.redis.ping()
                logger.info("Redis connected successfully for DistributedState.")
            except ImportError:
                logger.warning("redis-py not installed. Falling back to memory state.")
                self.redis = None
            except Exception as e:
                logger.error(f"Redis connection failed: {e}. Falling back to memory state.")
                self.redis = None
        else:
            logger.info("REDIS_URL not set. DistributedState using memory fallback.")

    async def get_partner(self, user_id: int) -> Optional[int]:
        if self.redis:
            val = await self.redis.get(f"chat:{user_id}")
            return int(val) if val else None
        else:
            async with self._lock:
                return self._fallback_store.get(f"chat:{user_id}")

    async def set_partner(self, user1: int, user2: int):
        if self.redis:
            await self.redis.set(f"chat:{user1}", user2)
            await self.redis.set(f"chat:{user2}", user1)
        else:
            async with self._lock:
                self._fallback_store[f"chat:{user1}"] = user2
                self._fallback_store[f"chat:{user2}"] = user1

    async def clear_partner(self, user_id: int) -> Optional[int]:
        partner_id = await self.get_partner(user_id)
        if self.redis:
            await self.redis.delete(f"chat:{user_id}")
            if partner_id:
                partner_await = await self.redis.get(f"chat:{partner_id}")
                if partner_await and int(partner_await) == user_id:
                    await self.redis.delete(f"chat:{partner_id}")
        else:
            async with self._lock:
                self._fallback_store.pop(f"chat:{user_id}", None)
                if partner_id and self._fallback_store.get(f"chat:{partner_id}") == user_id:
                    self._fallback_store.pop(f"chat:{partner_id}", None)
        return partner_id

    async def is_in_chat(self, user_id: int) -> bool:
        partner = await self.get_partner(user_id)
        return partner is not None

    # ─────────────────────────────────────────────────────────────────────
    # MATCHMAKING QUEUE: Global queue shared across all server workers
    # ─────────────────────────────────────────────────────────────────────

    async def add_to_queue(self, user_id: int, priority: bool = False, data: dict = None):
        """Add a user to the global matchmaking queue."""
        if self.redis:
            # 1. Store preferences/metadata in a hash
            if data:
                await self.redis.hset(f"match:pref:{user_id}", mapping={k: str(v) for k, v in data.items()})
                await self.redis.expire(f"match:pref:{user_id}", 3600) # Auto-cleanup after 1hr
            
            # 2. Add to waiting list (LPUSH for priority, RPUSH for normal)
            # Remove first to prevent duplicates
            await self.redis.lrem("queue:waiting", 0, str(user_id))
            if priority:
                await self.redis.lpush("queue:waiting", str(user_id))
            else:
                await self.redis.rpush("queue:waiting", str(user_id))
        else:
            async with self._lock:
                # Fallback to local memory (existing behavior)
                # Note: MatchState handles its own local list for now, 
                # but we provide this hook for consistency.
                pass

    async def remove_from_queue(self, user_id: int):
        """Remove a user from the global matchmaking queue."""
        if self.redis:
            await self.redis.lrem("queue:waiting", 0, str(user_id))
            await self.redis.delete(f"match:pref:{user_id}")
        else:
            pass

    async def get_queue_candidates(self) -> list[int]:
        """Fetch all user IDs currently in the queue."""
        if self.redis:
            members = await self.redis.lrange("queue:waiting", 0, -1)
            return [int(m) for m in members]
        return []

    async def get_user_queue_data(self, user_id: int) -> dict:
        """Fetch preference/metadata for a user in the queue."""
        if self.redis:
            data = await self.redis.hgetall(f"match:pref:{user_id}")
            if data:
                # Convert string scores/etc back to float/int where possible
                processed = {}
                for k, v in data.items():
                    try:
                        if "." in v: processed[k] = float(v)
                        else: processed[k] = int(v)
                    except: processed[k] = v
                return processed
        return {}

    async def clear_queue(self):
        """Wipe the entire global queue (admin action)."""
        if self.redis:
            keys = await self.redis.keys("match:pref:*")
            if keys: await self.redis.delete(*keys)
            await self.redis.delete("queue:waiting")

    async def get_user_state(self, user_id: int) -> Optional[str]:
        if self.redis:
            return await self.redis.get(f"state:{user_id}")
        else:
            async with self._lock:
                return self._fallback_store.get(f"state:{user_id}")

    async def set_user_state(self, user_id: int, state: Optional[str]):
        if self.redis:
            if state is None:
                await self.redis.delete(f"state:{user_id}")
            else:
                await self.redis.set(f"state:{user_id}", state)
        else:
            async with self._lock:
                if state is None:
                    self._fallback_store.pop(f"state:{user_id}", None)
                else:
                    self._fallback_store[f"state:{user_id}"] = state

    async def is_duplicate_message(self, message_id: str) -> bool:
        """Deduplicate Messenger messages atomically. Returns True if duplicate."""
        if not message_id:
            return False
        if self.redis:
            # SET NX EX is a single atomic command — no GET+SET race condition (C3 fix)
            result = await self.redis.set(f"msg_id:{message_id}", "1", nx=True, ex=300)
            return result is None  # None = key already existed = duplicate
        else:
            async with self._lock:
                key = f"msg_id:{message_id}"
                now = time.time()
                if key in self._fallback_store:
                    if now - self._fallback_store[key] < 300:
                        return True
                self._fallback_store[key] = now
                # Cleanup stale entries
                stale = [k for k, v in self._fallback_store.items()
                         if k.startswith("msg_id:") and now - v > 300]
                for k in stale:
                    del self._fallback_store[k]
                return False
                
    async def is_duplicate_interaction(self, user_id: int, action_key: str, ttl: int = 5) -> bool:
        """Deduplicate generic actions/interactions within a TTL window (C4 fix: atomic)."""
        key = f"interact:{user_id}:{action_key}"
        if self.redis:
            # Atomic SET NX EX — no race between GET and SET
            result = await self.redis.set(key, "1", nx=True, ex=ttl)
            return result is None  # None = already existed = duplicate
        else:
            async with self._lock:
                now = time.time()
                if key in self._fallback_store:
                    if now - self._fallback_store[key] < ttl:
                        return True
                self._fallback_store[key] = now
                return False

    # ─────────────────────────────────────────────────────────────────────
    # CONCURRENCY: Action Locking (prevents double-click / race conditions)
    # ─────────────────────────────────────────────────────────────────────

    async def acquire_action_lock(self, user_id: int, ttl: int = 3) -> bool:
        """Try to acquire an exclusive action lock for a user (M1 fix: separate lock).
        Returns True if acquired (safe to proceed), False if already locked.
        TTL auto-expires the lock to prevent deadlocks.
        """
        key = f"action_lock:{user_id}"
        if self.redis:
            # SET NX EX is atomic — safe for concurrent Redis calls
            result = await self.redis.set(key, "1", nx=True, ex=ttl)
            return result is not None
        else:
            async with self._action_lock:  # Use separate lock, not shared _lock
                now = time.time()
                existing = self._fallback_store.get(key)
                if existing and now - existing < ttl:
                    return False
                self._fallback_store[key] = now
                return True

    async def release_action_lock(self, user_id: int):
        """Release action lock early (after handler completes)."""
        key = f"action_lock:{user_id}"
        if self.redis:
            await self.redis.delete(key)
        else:
            async with self._action_lock:  # Use separate lock
                self._fallback_store.pop(key, None)

    # ─────────────────────────────────────────────────────────────────────
    # SESSION STATE: Pair-level state (not per-user) for matched chats
    # ─────────────────────────────────────────────────────────────────────

    @staticmethod
    def _session_key(user1: int, user2: int) -> str:
        """Canonical session key (order-independent)."""
        return f"session:{min(user1, user2)}:{max(user1, user2)}"

    async def set_session_state(self, user1: int, user2: int, state: str):
        """Set pair-level session state. Authoritative for chat lifecycle."""
        key = self._session_key(user1, user2)
        if self.redis:
            await self.redis.set(key, state)
        else:
            async with self._lock:
                self._fallback_store[key] = state

    async def get_session_state(self, user1: int, user2: Optional[int] = None) -> Optional[str]:
        """Get pair-level session state. If user2 unknown, looks up partner first."""
        if user2 is None:
            user2 = await self.get_partner(user1)
        if user2 is None:
            return None
        key = self._session_key(user1, user2)
        if self.redis:
            return await self.redis.get(key)
        else:
            async with self._lock:
                return self._fallback_store.get(key)

    async def clear_session_state(self, user1: int, user2: int):
        """Clear pair-level session state on chat end."""
        key = self._session_key(user1, user2)
        if self.redis:
            await self.redis.delete(key)
        else:
            async with self._lock:
                self._fallback_store.pop(key, None)

    # ─────────────────────────────────────────────────────────────────────
    # SESSION TIMING: Redis-backed chat start times (C5/C6 fix)
    # ─────────────────────────────────────────────────────────────────────

    async def set_chat_start(self, user_id: int, ts: float):
        """Store chat start timestamp in Redis so any worker can read it."""
        key = f"chat_start:{user_id}"
        if self.redis:
            await self.redis.set(key, str(ts), ex=86400)  # auto-expire after 24h
        else:
            async with self._lock:
                self._fallback_store[key] = ts

    async def pop_chat_start(self, user_id: int) -> float:
        """Retrieve and delete chat start timestamp. Returns now() if not found."""
        key = f"chat_start:{user_id}"
        if self.redis:
            val = await self.redis.getdel(key)
            return float(val) if val else time.time()
        else:
            async with self._lock:
                return self._fallback_store.pop(key, time.time())

    # ─────────────────────────────────────────────────────────────────────
    # ATOMIC MATCH CLAIM: Lua script prevents double-matching (C7 fix)
    # ─────────────────────────────────────────────────────────────────────

    # Lua script: atomically removes both users from queue and sets partner keys
    # Returns 0 if either user was already gone (snatched by another worker)
    _MATCH_CLAIM_LUA = """
        local queue = KEYS[1]
        local uid   = ARGV[1]
        local pid   = ARGV[2]
        local r1 = redis.call('LREM', queue, 0, uid)
        local r2 = redis.call('LREM', queue, 0, pid)
        if r1 == 0 or r2 == 0 then
            -- At least one was already claimed by another worker
            if r1 > 0 then redis.call('RPUSH', queue, uid) end
            if r2 > 0 then redis.call('RPUSH', queue, pid) end
            return 0
        end
        redis.call('SET', 'chat:'..uid, pid)
        redis.call('SET', 'chat:'..pid, uid)
        return 1
    """

    async def atomic_claim_match(self, user_id: int, partner_id: int) -> bool:
        """Atomically claim a match via Lua. Returns True only if both were in queue."""
        if self.redis:
            result = await self.redis.eval(
                self._MATCH_CLAIM_LUA,
                1,              # number of KEYS
                "queue:waiting",  # KEYS[1]
                str(user_id),     # ARGV[1]
                str(partner_id)   # ARGV[2]
            )
            return int(result) == 1
        # Fallback: single-worker, existing lock-based logic is fine
        return True

distributed_state = DistributedState()
