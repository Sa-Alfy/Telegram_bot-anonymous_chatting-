"""
Enhanced rate limiter — per-user daily caps, flood detection, cooldown feedback.
Distributed via Redis (C14/M1-adjacent fix).
"""

import time
import asyncio
from typing import Optional, List
from services.distributed_state import distributed_state
from utils.logger import logger

class RateLimiter:
    def __init__(self):
        # Fallback in-memory store for non-Redis environments
        self._last_message = {}
        self._last_matchmaking = {}
        self._last_report = {}
        self._daily_counts = {}     # user_id -> {"date": "YYYY-MM-DD", "count": int}
        self._spam_counts = {}      # user_id -> int
        self._mute_until = {}       # user_id -> float
        self._connect_times = {}    # user_id -> [timestamps] for flood detection
        self._lock = asyncio.Lock()

        # Limits
        self.MESSAGE_COOLDOWN = 1.0       # seconds between messages
        self.SPAM_WINDOW = 2.0            # window for rapid message tracking
        self.SPAM_THRESHOLD = 5           # messages before mute
        self.MUTE_DURATION = 15           # seconds
        
        self.MATCHMAKE_COOLDOWN = 3.0     # seconds between searches
        self.REPORT_COOLDOWN = 5.0        # seconds between reports
        self.DAILY_MESSAGE_CAP = 5000     # max messages per day
        self.FLOOD_WINDOW = 60            # seconds
        self.FLOOD_MAX_CONNECTS = 10      # max connect/disconnect cycles per window

    async def can_send_message(self, user_id: int) -> tuple[bool, str]:
        """Check message cooldown, daily cap, and spam status.
        Returns (success, reason).
        """
        now = time.time()
        
        if distributed_state.redis:
            # 0. Mute check
            mute_key = f"rl:mute:{user_id}"
            mute_ttl = await distributed_state.redis.ttl(mute_key)
            if mute_ttl > 0:
                return False, f"MUTED:{mute_ttl}"

            # 1. Cooldown check
            key = f"rl:msg:{user_id}"
            if await distributed_state.redis.exists(key):
                # Potential spam detection
                spam_key = f"rl:spam:{user_id}"
                count = await distributed_state.redis.incr(spam_key)
                await distributed_state.redis.expire(spam_key, int(self.SPAM_WINDOW))
                
                if count >= self.SPAM_THRESHOLD:
                    await distributed_state.redis.set(mute_key, "1", ex=self.MUTE_DURATION)
                    await distributed_state.redis.delete(spam_key)
                    return False, f"MUTED:{self.MUTE_DURATION}"
                
                return False, "COOLDOWN"
            
            # 2. Daily cap check
            today = time.strftime("%Y-%m-%d")
            daily_key = f"rl:daily:{user_id}:{today}"
            count = await distributed_state.redis.get(daily_key)
            if count and int(count) >= self.DAILY_MESSAGE_CAP:
                return False, "DAILY_CAP"
            
            # Update
            await distributed_state.redis.set(key, "1", ex=int(self.MESSAGE_COOLDOWN))
            # Atomic increment
            new_count = await distributed_state.redis.incr(daily_key)
            if new_count == 1:
                await distributed_state.redis.expire(daily_key, 86400) # 24h
            return True, "OK"
        else:
            async with self._lock:
                # Mute check
                mute_until = self._mute_until.get(user_id, 0)
                if now < mute_until:
                    return False, f"MUTED:{int(mute_until - now)}"

                last = self._last_message.get(user_id, 0)
                if now - last < self.MESSAGE_COOLDOWN:
                    count = self._spam_counts.get(user_id, 0) + 1
                    self._spam_counts[user_id] = count
                    if count >= self.SPAM_THRESHOLD:
                        self._mute_until[user_id] = now + self.MUTE_DURATION
                        self._spam_counts[user_id] = 0
                        return False, f"MUTED:{self.MUTE_DURATION}"
                    return False, "COOLDOWN"
                
                today = time.strftime("%Y-%m-%d")
                daily = self._daily_counts.get(user_id)
                if daily and daily["date"] == today:
                    if daily["count"] >= self.DAILY_MESSAGE_CAP:
                        return False, "DAILY_CAP"
                    daily["count"] += 1
                else:
                    self._daily_counts[user_id] = {"date": today, "count": 1}

                self._last_message[user_id] = now
                self._spam_counts[user_id] = 0
                return True, "OK"

    async def can_matchmake(self, user_id: int, update: bool = True) -> bool:
        """Check matchmaking search cooldown (Async)."""
        now = time.time()
        key = f"rl:mm:{user_id}"
        
        if distributed_state.redis:
            exists = await distributed_state.redis.exists(key)
            if exists:
                return False
            if update:
                await distributed_state.redis.set(key, "1", ex=int(self.MATCHMAKE_COOLDOWN))
            return True
        else:
            async with self._lock:
                last = self._last_matchmaking.get(user_id, 0)
                if now - last < self.MATCHMAKE_COOLDOWN:
                    return False
                if update:
                    self._last_matchmaking[user_id] = now
                return True

    async def can_report(self, user_id: int) -> bool:
        """Check report cooldown (Async)."""
        now = time.time()
        key = f"rl:rpt:{user_id}"
        
        if distributed_state.redis:
            if await distributed_state.redis.exists(key):
                return False
            await distributed_state.redis.set(key, "1", ex=int(self.REPORT_COOLDOWN))
            return True
        else:
            async with self._lock:
                last = self._last_report.get(user_id, 0)
                if now - last < self.REPORT_COOLDOWN:
                    return False
                self._last_report[user_id] = now
                return True

    async def check_flood(self, user_id: int) -> bool:
        """Check for rapid connect/disconnect cycling (Async)."""
        now = time.time()
        key = f"rl:flood:{user_id}"
        
        if distributed_state.redis:
            # Pipelined approach: push now, trim old, check length
            async with distributed_state.redis.pipeline(transaction=True) as pipe:
                pipe.rpush(key, str(now))
                pipe.expire(key, self.FLOOD_WINDOW)
                # Redis doesn't have an "lrem_by_value_range", so we'll just read and prune
                # or simpler: LTRIM if we know frequency
                await pipe.execute()
            
            # For simplicity in Redis: read all, filter in Python, write back
            raw_times = await distributed_state.redis.lrange(key, 0, -1)
            times = [float(t) for t in raw_times if now - float(t) < self.FLOOD_WINDOW]
            
            if len(times) != len(raw_times):
                await distributed_state.redis.delete(key)
                if times:
                    await distributed_state.redis.rpush(key, *[str(t) for t in times])
                    await distributed_state.redis.expire(key, self.FLOOD_WINDOW)
            
            return len(times) > self.FLOOD_MAX_CONNECTS
        else:
            async with self._lock:
                times = self._connect_times.get(user_id, [])
                times = [t for t in times if now - t < self.FLOOD_WINDOW]
                times.append(now)
                self._connect_times[user_id] = times
                return len(times) > self.FLOOD_MAX_CONNECTS

    async def get_cooldown_remaining(self, user_id: int, action_type: str = "message") -> Optional[float]:
        """Get remaining cooldown in seconds for a given action type (Async)."""
        if distributed_state.redis:
            mapping = {
                "message": f"rl:msg:{user_id}",
                "matchmake": f"rl:mm:{user_id}",
                "report": f"rl:rpt:{user_id}"
            }
            key = mapping.get(action_type)
            if not key: return None
            
            ttl = await distributed_state.redis.ttl(key)
            return float(ttl) if ttl > 0 else None
        else:
            now = time.time()
            async with self._lock:
                if action_type == "message":
                    last = self._last_message.get(user_id, 0)
                    cd = self.MESSAGE_COOLDOWN
                elif action_type == "matchmake":
                    last = self._last_matchmaking.get(user_id, 0)
                    cd = self.MATCHMAKE_COOLDOWN
                elif action_type == "report":
                    last = self._last_report.get(user_id, 0)
                    cd = self.REPORT_COOLDOWN
                else:
                    return None
                
                remaining = cd - (now - last)
                return max(0, remaining) if remaining > 0 else None

    async def is_daily_capped(self, user_id: int) -> bool:
        """Check if user has hit their daily message cap (Async)."""
        today = time.strftime("%Y-%m-%d")
        if distributed_state.redis:
            count = await distributed_state.redis.get(f"rl:daily:{user_id}:{today}")
            return int(count) >= self.DAILY_MESSAGE_CAP if count else False
        else:
            async with self._lock:
                daily = self._daily_counts.get(user_id)
                if daily and daily["date"] == today:
                    return daily["count"] >= self.DAILY_MESSAGE_CAP
                return False

rate_limiter = RateLimiter()
