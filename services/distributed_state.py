import os
import time
import asyncio
import json
from typing import Optional, Any
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

    async def validate_session(self, user_id: Any, repair: bool = False) -> bool:
        """Validates state consistency (e.g. CHAT_ACTIVE must have a partner)."""
        state = await self.get_user_state(user_id)
        if state == "CHAT_ACTIVE":
            partner = await self.get_partner(user_id)
            if not partner:
                if repair:
                    await self.set_user_state(user_id, "HOME")
                return False
        return True

    async def acquire_action_lock(self, user_id: Any, ttl: int = 5) -> bool:
        """Atomic lock to prevent duplicate concurrent actions."""
        key = f"sm:lock:{user_id}"
        if self.redis:
            return bool(await self.redis.set(key, "1", ex=ttl, nx=True))
        else:
            async with self._lock:
                if key in self._fallback_store:
                    data = self._fallback_store[key]
                    if isinstance(data, dict) and time.time() < data.get("expiry", 0):
                        return False
                self._fallback_store[key] = {"val": "1", "expiry": time.time() + ttl}
                return True

    async def release_action_lock(self, user_id: Any):
        key = f"sm:lock:{user_id}"
        if self.redis:
            await self.redis.delete(key)
        else:
            async with self._lock:
                self._fallback_store.pop(key, None)

    async def set_session_state(self, u1: Any, u2: Any, state: str):
        """Sets a state for a shared session."""
        if not u2: return
        su1, su2 = str(u1), str(u2)
        key = f"sm:session:{min(su1, su2)}:{max(su1, su2)}"
        if self.redis:
            await self.redis.set(key, state, ex=3600)
        else:
            async with self._lock:
                self._fallback_store[key] = state

    async def get_session_state(self, u1: Any, u2: Any = None) -> Optional[str]:
        """Gets shared state."""
        if not u2:
            u2 = await self.get_partner(u1)
        if not u2: return None
        su1, su2 = str(u1), str(u2)
        key = f"sm:session:{min(su1, su2)}:{max(su1, su2)}"
        if self.redis:
            return await self.redis.get(key)
        else:
            async with self._lock:
                return self._fallback_store.get(key)

    async def clear_session_state(self, u1: Any, u2: Any):
        if not u2: return
        su1, su2 = str(u1), str(u2)
        key = f"sm:session:{min(su1, su2)}:{max(su1, su2)}"
        if self.redis:
            await self.redis.delete(key)
        else:
            async with self._lock:
                self._fallback_store.pop(key, None)
        
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

    async def clear_all(self):
        """Wipe all state (admin action or test cleanup)."""
        if self.redis:
            keys = await self.redis.keys("sm:*")
            if keys: await self.redis.delete(*keys)
        else:
            async with self._lock:
                self._fallback_store.clear()
            async with self._action_lock:
                pass

    async def get_partner(self, user_id: Any) -> Optional[Any]:
        u_str = str(user_id)
        if self.redis:
            val = await self.redis.get(f"sm:partner:{u_str}")
            if val and val.isdigit(): return int(val)
            return str(val) if val else None

        else:
            async with self._lock:
                val = self._fallback_store.get(f"sm:partner:{u_str}")
                if isinstance(val, str) and val.isdigit(): return int(val)
                return val

    async def set_partner(self, user1: Any, user2: Any):
        u1_str, u2_str = str(user1), str(user2)
        if self.redis:
            await self.redis.set(f"sm:partner:{u1_str}", u2_str)
            await self.redis.set(f"sm:partner:{u2_str}", u1_str)

        else:
            async with self._lock:
                self._fallback_store[f"sm:partner:{u1_str}"] = u2_str
                self._fallback_store[f"sm:partner:{u2_str}"] = u1_str

    async def clear_partner(self, user_id: Any) -> Optional[Any]:
        partner_id = await self.get_partner(user_id)
        u_str = str(user_id)
        p_str = str(partner_id) if partner_id else None

        if self.redis:
            await self.redis.delete(f"sm:partner:{u_str}")
            if p_str:
                partner_await = await self.redis.get(f"sm:partner:{p_str}")
                if partner_await and str(partner_await) == u_str:
                    await self.redis.delete(f"sm:partner:{p_str}")
        else:
            async with self._lock:
                self._fallback_store.pop(f"sm:partner:{u_str}", None)
                if p_str and str(self._fallback_store.get(f"sm:partner:{p_str}")) == u_str:
                    self._fallback_store.pop(f"sm:partner:{p_str}", None)
        return partner_id

    async def is_in_chat(self, user_id: Any) -> bool:
        u_str = str(user_id)
        # Guard: only truly "in chat" if state is CHAT_ACTIVE, not just any stale partner key
        if self.redis:
            state = await self.redis.get(f"sm:state:{u_str}")
        else:
            async with self._lock:
                state = self._fallback_store.get(f"sm:state:{u_str}")
        
        if state != "CHAT_ACTIVE":
            return False
            
        partner = await self.get_partner(user_id)
        return partner is not None

    # ─────────────────────────────────────────────────────────────────────
    # MATCHMAKING QUEUE: Global queue shared across all server workers
    # ─────────────────────────────────────────────────────────────────────

    async def add_to_queue(self, user_id: int, priority: bool = False, data: dict = None) -> bool:
        """Add a user to the global matchmaking queue."""
        u_str = str(user_id)
        if self.redis:
            # 1. Store preferences/metadata in a hash
            if data:
                await self.redis.hset(f"sm:match:pref:{user_id}", mapping={k: str(v) for k, v in data.items()})
                await self.redis.expire(f"sm:match:pref:{user_id}", 3600) # Auto-cleanup after 1hr
            
            # 2. Add to waiting list (LPUSH for priority, RPUSH for normal)
            # Remove first to prevent duplicates
            await self.redis.lrem("sm:queue", 0, u_str)
            if priority:
                await self.redis.lpush("sm:queue", u_str)
            else:
                await self.redis.rpush("sm:queue", u_str)
            return True
        else:
            async with self._lock:
                queue = self._fallback_store.get("sm:queue", [])
                if u_str in queue:
                    queue.remove(u_str)
                if priority:
                    queue.insert(0, u_str)
                else:
                    queue.append(u_str)
                self._fallback_store["sm:queue"] = queue
                if data:
                    self._fallback_store[f"sm:match:pref:{u_str}"] = data
                return True

    async def remove_from_queue(self, user_id: int):
        """Remove a user from the global matchmaking queue."""
        u_str = str(user_id)
        if self.redis:
            await self.redis.lrem("sm:queue", 0, u_str)
            await self.redis.delete(f"sm:match:pref:{user_id}")
        else:
            async with self._lock:
                queue = self._fallback_store.get("sm:queue", [])
                if u_str in queue:
                    queue.remove(u_str)
                self._fallback_store.pop(f"sm:match:pref:{u_str}", None)

    async def get_queue_candidates(self) -> list[str]:
        """Fetch all user IDs currently in the queue as strings."""
        if self.redis:
            members = await self.redis.lrange("sm:queue", 0, -1)
            return [m.decode() if isinstance(m, bytes) else str(m) for m in members]
        else:
            async with self._lock:
                return list(self._fallback_store.get("sm:queue", []))

    async def get_user_queue_data(self, user_id: Any) -> dict:
        """Fetch preference/metadata for a user in the queue."""
        u_str = str(user_id)
        if self.redis:
            data = await self.redis.hgetall(f"sm:match:pref:{user_id}")
            if data:
                # Convert string scores/etc back to float/int where possible
                processed = {}
                for k, v in data.items():
                    try:
                        if "." in v: processed[k] = float(v)
                        else: processed[k] = int(v)
                    except: processed[k] = v
                return processed
        else:
            async with self._lock:
                return self._fallback_store.get(f"sm:match:pref:{u_str}", {})
        return {}

    async def clear_queue(self):
        """Wipe the entire global queue (admin action)."""
        if self.redis:
            keys = await self.redis.keys("sm:match:pref:*")
            if keys: await self.redis.delete(*keys)
            await self.redis.delete("sm:queue")

    _VALIDATE_SESSION_LUA = """
        -- KEYS: 1:state:uA, 2:state:uB, 3:chat:uA, 4:chat:uB
        -- ARGV: 1:uA_id, 2:uB_id
        local stateA = redis.call("GET", KEYS[1])
        local stateB = redis.call("GET", KEYS[2])
        local partnerA = redis.call("GET", KEYS[3])
        local partnerB = redis.call("GET", KEYS[4])

        if stateA == "CHAT_ACTIVE" then
            if not partnerA or partnerA ~= ARGV[2] then return {0, "A_INVALID_PARTNER"} end
            if not stateB or stateB ~= "CHAT_ACTIVE" then return {0, "B_NOT_CHATTING"} end
        end
        if partnerA and partnerB then
            if partnerA ~= ARGV[2] or partnerB ~= ARGV[1] then return {0, "MISMATCH"} end
        end
        return {1, "OK"}
    """

    async def get_user_state(self, user_id: Any) -> Optional[str]:
        u_str = str(user_id)
        if self.redis:
            return await self.redis.get(f"sm:state:{u_str}")
        else:
            async with self._lock:
                return self._fallback_store.get(f"sm:state:{u_str}")


    async def set_user_state(self, user_id: Any, state: Optional[str]):
        u_str = str(user_id)
        if self.redis:
            if state is None:
                await self.redis.delete(f"sm:state:{u_str}")
            else:
                await self.redis.set(f"sm:state:{u_str}", state)
        else:
            async with self._lock:
                if state is None:
                    self._fallback_store.pop(f"sm:state:{u_str}", None)
                else:
                    self._fallback_store[f"sm:state:{u_str}"] = state


    async def is_duplicate_message(self, message_id: str) -> bool:
        """Deduplicate Messenger messages atomically. Returns True if duplicate."""
        if not message_id:
            return False
        if self.redis:
            # SET NX EX is a single atomic command — no GET+SET race condition (C3 fix)
            result = await self.redis.set(f"sm:msg_id:{message_id}", "1", nx=True, ex=300)
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
        key = f"sm:interact:{user_id}:{action_key}"
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
        key = f"sm:lock:action:{user_id}"
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
        key = f"sm:lock:action:{user_id}"
        if self.redis:
            await self.redis.delete(key)
        else:
            async with self._action_lock:  # Use separate lock
                self._fallback_store.pop(key, None)

    # ─────────────────────────────────────────────────────────────────────
    # ATOMIC LUA FOUNDATION (Production-Grade)
    # ─────────────────────────────────────────────────────────────────────

    _CLAIM_AND_INITIALIZE_LUA = """
        -- KEYS: 1:state:uA, 2:state:uB, 3:partner:uA, 4:partner:uB, 5:start:uA, 6:start:uB, 7:queue
        -- ARGV: 1:uA_id, 2:uB_id, 3:timestamp
        
        local uA = ARGV[1]
        local uB = ARGV[2]
        local now = ARGV[3]

        -- 1. PRECONDITION CHECKS
        if redis.call("GET", KEYS[1]) == "CHAT_ACTIVE" then return {0, "USER_A_BUSY"} end
        if redis.call("GET", KEYS[2]) == "CHAT_ACTIVE" then return {0, "USER_B_BUSY"} end
        if redis.call("EXISTS", KEYS[3]) == 1 then return {0, "USER_A_HAS_PARTNER"} end
        if redis.call("EXISTS", KEYS[4]) == 1 then return {0, "USER_B_HAS_PARTNER"} end

        -- 2. REMOVE FROM QUEUE (Standard sm:queue)
        redis.call("LREM", KEYS[7], 0, uA)
        redis.call("LREM", KEYS[7], 0, uB)

        -- 3. SET PARTNER MAPPING
        redis.call("SET", KEYS[3], uB)
        redis.call("SET", KEYS[4], uA)

        -- 4. SET STATE
        redis.call("SET", KEYS[1], "CHAT_ACTIVE")
        redis.call("SET", KEYS[2], "CHAT_ACTIVE")

        -- 5. SET SESSION START
        redis.call("SET", KEYS[5], now)
        redis.call("SET", KEYS[6], now)

        return {1, "MATCHED"}
    """

    _ATOMIC_DISCONNECT_LUA = """
        -- KEYS: 1:state:uA, 2:partner:uA, 3:start:uA
        -- ARGV: 1:uA_id

        local partnerA = redis.call("GET", KEYS[2])
        if not partnerA then
            return {0, "", ""}
        end

        local startA = redis.call("GET", KEYS[3])

        -- Keys for partner
        local stateBKey = "sm:state:" .. partnerA
        local partnerBKey = "sm:partner:" .. partnerA
        local startBKey = "sm:chat_start:" .. partnerA

        -- Clear mappings
        redis.call("DEL", KEYS[2])
        redis.call("DEL", partnerBKey)

        -- Reset states (only if currently chatting)
        local stateA = redis.call("GET", KEYS[1])
        local stateB = redis.call("GET", stateBKey)
        if stateA == "CHAT_ACTIVE" then redis.call("SET", KEYS[1], "VOTING") end
        if stateB == "CHAT_ACTIVE" then redis.call("SET", stateBKey, "VOTING") end

        -- Clear session data
        redis.call("DEL", KEYS[3])
        redis.call("DEL", startBKey)

        return {1, partnerA, startA or ""}
    """

    _FORCE_DISCONNECT_SINGLE_LUA = """
        -- KEYS: 1:state:user, 2:partner:user, 3:start:user
        redis.call("DEL", KEYS[2])
        redis.call("SET", KEYS[1], "HOME")
        redis.call("DEL", KEYS[3])
        return {1, "FORCE_RESET"}
    """

    _ATOMIC_REMATCH_LUA = """
        -- KEYS: 
        -- 1: sm:state:userA
        -- 2: sm:state:userB
        -- 3: sm:partner:userA
        -- 4: sm:partner:userB
        -- 5: sm:chat_start:userA
        -- 6: sm:chat_start:userB
        -- 7: rematch_key (sm:rematch:min:max)

        -- ARGV: 
        -- 1: userA_id (caller)
        -- 2: userB_id (target)
        -- 3: current_timestamp

        local caller = ARGV[1]
        local partner = ARGV[2]
        local now = ARGV[3]

        -- 1. Validate both users are HOME
        local sA = redis.call("GET", KEYS[1])
        local sB = redis.call("GET", KEYS[2])
        
        if sA and sA ~= "HOME" then return {0, "CALLER_NOT_HOME"} end
        if sB and sB ~= "HOME" then return {0, "PARTNER_NOT_HOME"} end

        -- 2. Check existing rematch intent
        local existing = redis.call("GET", KEYS[7])

        -- Case A: First click
        if not existing then
            redis.call("SET", KEYS[7], caller, "EX", 30)
            return {2, "WAITING_FOR_PARTNER"}
        end

        -- Case B: Same user clicking again
        if existing == caller then
            return {2, "ALREADY_WAITING"}
        end

        -- Case C: Mutual match detected
        if existing == partner then
            -- FINAL SAFETY CHECKS: Ensure they haven't been matched by someone else
            if redis.call("EXISTS", KEYS[3]) == 1 or redis.call("EXISTS", KEYS[4]) == 1 then
                return {0, "ALREADY_MATCHED"}
            end

            -- CREATE MATCH (ATOMIC)
            redis.call("SET", KEYS[3], partner)
            redis.call("SET", KEYS[4], caller)

            redis.call("SET", KEYS[1], "CHAT_ACTIVE")
            redis.call("SET", KEYS[2], "CHAT_ACTIVE")

            redis.call("SET", KEYS[5], now)
            redis.call("SET", KEYS[6], now)

            -- CLEANUP intent key
            redis.call("DEL", KEYS[7])

            return {1, "REMATCH_SUCCESS"}
        end

        -- Case D: Unexpected state
        redis.call("SET", KEYS[7], caller, "EX", 30)
        return {2, "RESET_WAITING"}
    """

    # ─────────────────────────────────────────────────────────────────────
    # SESSION STATE: Pair-level state (not per-user) for matched chats
    # ─────────────────────────────────────────────────────────────────────

    @staticmethod
    def _session_key(user1: int, user2: int) -> str:
        """Canonical session key (order-independent)."""
        return f"session:{min(user1, user2)}:{max(user1, user2)}"

    async def set_session_state(self, user1: int, user2: int, state: str):
        """Set pair-level session state. Authoritative for chat lifecycle."""
        key = f"sm:{self._session_key(user1, user2)}"
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
        key = f"sm:{self._session_key(user1, user2)}"
        if self.redis:
            return await self.redis.get(key)
        else:
            async with self._lock:
                return self._fallback_store.get(key)

    async def clear_session_state(self, user1: int, user2: int):
        """Clear pair-level session state on chat end."""
        key = f"sm:{self._session_key(user1, user2)}"
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
        key = f"sm:chat_start:{user_id}"
        if self.redis:
            await self.redis.set(key, str(ts), ex=86400)  # auto-expire after 24h
        else:
            async with self._lock:
                self._fallback_store[key] = ts

    async def pop_chat_start(self, user_id: int) -> float:
        """Retrieve and delete chat start timestamp. Returns now() if not found."""
        key = f"sm:chat_start:{user_id}"
        if self.redis:
            val = await self.redis.getdel(key)
            return float(val) if val else time.time()
        else:
            async with self._lock:
                return self._fallback_store.pop(key, time.time())

    # ─────────────────────────────────────────────────────────────────────
    # MESSAGE COUNTER: Track engagement for progression (C7 fix)
    # ─────────────────────────────────────────────────────────────────────

    async def increment_message_count(self, user1: Any, user2: Any):
        """Atomic increment for message counter in a session."""
        u1, u2 = str(user1), str(user2)
        # Canonical key
        key = f"sm:msg_count:{min(u1, u2)}:{max(u1, u2)}"
        if self.redis:
            await self.redis.incr(key)
            await self.redis.expire(key, 86400)
        else:
            async with self._lock:
                self._fallback_store[key] = self._fallback_store.get(key, 0) + 1

    async def get_message_count(self, user1: Any, user2: Any) -> int:
        """Retrieve current message count for a session."""
        u1, u2 = str(user1), str(user2)
        key = f"sm:msg_count:{min(u1, u2)}:{max(u1, u2)}"
        if self.redis:
            val = await self.redis.get(key)
            return int(val) if val else 0
        else:
            async with self._lock:
                return self._fallback_store.get(key, 0)

    async def clear_message_count(self, user1: Any, user2: Any):
        """Cleanup counter on session end."""
        u1, u2 = str(user1), str(user2)
        key = f"sm:msg_count:{min(u1, u2)}:{max(u1, u2)}"
        if self.redis:
            await self.redis.delete(key)
        else:
            async with self._lock:
                self._fallback_store.pop(key, None)

    async def atomic_claim_match(self, user_id: int, partner_id: int) -> tuple[bool, str]:
        """Atomically claim a match and initialize states via Lua."""
        from core.telemetry import EventLogger, TelemetryEvent
        EventLogger.log_event(
            event=TelemetryEvent.REDIS_CALL, layer="distributed_state", status=TelemetryEvent.INFO,
            user_id=user_id, peer_id=partner_id, data={"action": "atomic_claim_match"}
        )
        if self.redis:
            keys = [
                f"sm:state:{user_id}", f"sm:state:{partner_id}",
                f"sm:partner:{user_id}", f"sm:partner:{partner_id}",
                f"sm:chat_start:{user_id}", f"sm:chat_start:{partner_id}",
                "sm:queue"
            ]
            result = await self.redis.eval(
                self._CLAIM_AND_INITIALIZE_LUA,
                len(keys),
                *keys,
                str(user_id), str(partner_id), str(time.time())
            )
            success = int(result[0]) == 1
            EventLogger.log_event(
                event=TelemetryEvent.REDIS_RESULT, layer="distributed_state",
                status=TelemetryEvent.SUCCESS if success else TelemetryEvent.FAIL,
                user_id=user_id, peer_id=partner_id, expected="MATCHED", actual=result[1],
                data={"code": int(result[0])}
            )
            return success, result[1]
        # Memory Fallback
        await self.set_partner(user_id, partner_id)
        now = time.time()
        await self.set_chat_start(user_id, now)
        await self.set_chat_start(partner_id, now)
        return True, "FALLBACK_OK"

    async def atomic_disconnect(self, user_id: int) -> dict:
        """Atomically disconnect a user from their partner via Lua."""
        from core.telemetry import EventLogger, TelemetryEvent
        EventLogger.log_event(
            event=TelemetryEvent.REDIS_CALL, layer="distributed_state", status=TelemetryEvent.INFO,
            user_id=user_id, data={"action": "atomic_disconnect"}
        )
        now = time.time()
        if self.redis:
            keys = [
                f"sm:state:{user_id}",
                f"sm:partner:{user_id}",
                f"sm:chat_start:{user_id}"
            ]
            result = await self.redis.eval(
                self._ATOMIC_DISCONNECT_LUA,
                len(keys),
                *keys,
                str(user_id)
            )
            
            if int(result[0]) == 0:
                EventLogger.log_event(
                    event=TelemetryEvent.REDIS_RESULT, layer="distributed_state", status=TelemetryEvent.WARNING,
                    user_id=user_id, expected="DISCONNECT", actual="NO_PARTNER"
                )
                return {"partner_id": None, "duration": 0, "ended_at": now}
                
            partner_str = str(result[1])
            partner_id = int(partner_str) if partner_str.isdigit() else partner_str
            
            EventLogger.log_event(
                event=TelemetryEvent.REDIS_RESULT, layer="distributed_state", status=TelemetryEvent.SUCCESS,
                user_id=user_id, peer_id=partner_id, expected="DISCONNECT", actual="SUCCESS"
            )
            
            try:
                startA = float(result[2]) if result[2] else now
            except:
                startA = now
                
            return {
                "partner_id": partner_id,
                "duration": int(now - startA),
                "ended_at": now
            }
            
        # Memory Fallback
        partner_id = await self.get_partner(user_id)
        if not partner_id:
            return {"partner_id": None, "duration": 0, "ended_at": now}
            
        startA = await self.pop_chat_start(user_id)
        await self.pop_chat_start(partner_id)
        await self.clear_partner(user_id)
        
        return {
            "partner_id": partner_id,
            "duration": int(now - startA),
            "ended_at": now
        }

    async def force_disconnect_single(self, user_id: int):
        """Emergency reset for a single user via Lua."""
        if self.redis:
            keys = [f"sm:state:{user_id}", f"sm:partner:{user_id}", f"sm:chat_start:{user_id}"]
            await self.redis.eval(self._FORCE_DISCONNECT_SINGLE_LUA, len(keys), *keys)
        else:
            async with self._lock:
                self._fallback_store.pop(f"sm:partner:{user_id}", None)
                self._fallback_store[f"sm:state:{user_id}"] = "HOME"
                self._fallback_store.pop(f"sm:chat_start:{user_id}", None)

    async def validate_session(self, user_id: int, repair: bool = True) -> bool:
        """Strict invariant check: enforces bidirectional match integrity."""
        if not self.redis: return True

        state = await self.get_user_state(user_id)

        # Heal users permanently stuck in transient handshake states.
        # These states have no self-recovery path if the bot crashes mid-transition.
        if state in ("MATCHED", "CONNECTING", "CHAT_END"):
            if repair:
                logger.warning(f"validate_session: healing stuck state '{state}' for user {user_id}")
                await self.force_disconnect_single(user_id)
            return True  # Don't block the user — they've been healed, let them proceed

        if state != "CHAT_ACTIVE": return True
        
        partner_id = await self.get_partner(user_id)
        if not partner_id:
            logger.warning(f"Invariant Violation: User {user_id} CHAT_ACTIVE but NULL partner.")
            if repair: await self.force_disconnect_single(user_id)
            return False
            
        keys = [f"sm:state:{user_id}", f"sm:state:{partner_id}", f"sm:partner:{user_id}", f"sm:partner:{partner_id}"]
        result = await self.redis.eval(self._VALIDATE_SESSION_LUA, len(keys), *keys, str(user_id), str(partner_id))
        
        if int(result[0]) == 0:
            logger.warning(f"Invariant Violation: Pair {user_id}<->{partner_id} fail: {result[1]}")
            if repair: await self.force_disconnect_pair(user_id, partner_id)
            return False
        return True

    async def force_disconnect_pair(self, user1: int, user2: int):
        """Emergency reset for both parties to prevent ghost sessions."""
        logger.info(f"🚨 FORCE_DISCONNECT_PAIR: {user1} <-> {user2}")
        await self.force_disconnect_single(user1)
        await self.force_disconnect_single(user2)

    async def atomic_rematch(self, user_id: int, partner_id: int) -> tuple[int, str]:
        """Atomically claim a rematch via Lua."""
        from core.telemetry import EventLogger, TelemetryEvent
        EventLogger.log_event(
            event=TelemetryEvent.REDIS_CALL, layer="distributed_state", status=TelemetryEvent.INFO,
            user_id=user_id, peer_id=partner_id, data={"action": "atomic_rematch"}
        )
        if self.redis:
            # Canonical rematch key
            rkey = f"sm:rematch:{min(user_id, partner_id)}:{max(user_id, partner_id)}"
            keys = [
                f"sm:state:{user_id}", f"sm:state:{partner_id}",
                f"sm:partner:{user_id}", f"sm:partner:{partner_id}",
                f"sm:chat_start:{user_id}", f"sm:chat_start:{partner_id}",
                rkey
            ]
            result = await self.redis.eval(
                self._ATOMIC_REMATCH_LUA,
                len(keys),
                *keys,
                str(user_id), str(partner_id), str(time.time())
            )
            # return code, reason
            EventLogger.log_event(
                event=TelemetryEvent.REDIS_RESULT, layer="distributed_state", 
                status=TelemetryEvent.SUCCESS if int(result[0]) == 1 else TelemetryEvent.INFO,
                user_id=user_id, peer_id=partner_id, actual=result[1]
            )
            return int(result[0]), result[1]
        
        return 0, "REDIS_REQUIRED"

distributed_state = DistributedState()
