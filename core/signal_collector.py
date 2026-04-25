"""
===============================================================================
File: core/signal_collector.py
Description: The data acquisition layer for user behavioral intelligence.

How it works:
This module is responsible for capturing raw interaction "signals" from users.
It defines a structured data model (UserSignals) that tracks metrics such as
message counts, chat duration, rapid skips, and reports. These signals are
stored in Redis (production) or in-memory (testing) and are later consumed
by the BehaviorClassifier to assess user behavior.

Architecture & Patterns:
- Data Transfer Object (DTO): The UserSignals Pydantic model ensures data 
  consistency and easy serialization.
- Strategy Pattern: The BaseSignalStore interface allows swapping between 
  InMemory and Redis storage without changing the collector logic.
- Singleton Pattern: A global signal_collector instance provides a unified 
  entry point for recording behavior across the app.

How to modify:
- To track a new behavior: Add a field to UserSignals and a corresponding 
  'record_X' method in the SignalCollector class.
- To change session logic: Modify the '_end_session' helper to adjust how 
  good/bad sessions are classified.
===============================================================================
"""

import time
import json
import hashlib
from typing import Dict, Optional
from pydantic import BaseModel, Field
from abc import ABC, abstractmethod

from core.config import (
    INACTIVITY_TIMEOUT_SEC, 
    SKIP_THRESHOLD_SEC, 
    MIN_MSG_GOOD_SESSION,
    DECAY_PER_GOOD_SESSION
)
from utils.logger import logger

class UserSignals(BaseModel):
    """
    Structured model representing a user's behavioral footprint.
    """
    
    # Base metrics
    session_count: int = 0
    messages_sent: int = 0
    messages_received: int = 0
    total_chat_duration: float = 0.0
    matches_joined: int = 0
    matches_skipped: int = 0
    total_time_to_skip: float = 0.0
    reports_received: int = 0
    reports_given: int = 0
    last_action_time: float = Field(default_factory=time.time)
    
    # Session state
    current_session_messages: int = 0
    current_session_start: float = 0.0
    
    # Behavior Accumulators
    inactivity_periods: int = 0
    rapid_skips: int = 0       # Total rapid skips penalty
    good_sessions: int = 0     # Deep/good sessions
    bad_sessions: int = 0      # Low message count & fast exit
    violation_count: int = 0
    last_violation_timestamp: float = 0.0
    
    # Anti-Spam
    copy_paste_streak: int = 0
    last_message_hash: str = ""
    
    # Sentiment
    session_sentiment_sum: float = 0.0
    session_sentiment_count: int = 0

class BaseSignalStore(ABC):
    """Storage-agnostic interface for user signals."""
    @abstractmethod
    async def get(self, user_id: int) -> UserSignals: pass
    
    @abstractmethod
    async def save(self, user_id: int, signals: UserSignals): pass

class InMemorySignalStore(BaseSignalStore):
    """Local dict-based store for testing or fallback."""
    def __init__(self):
        self._store: Dict[int, UserSignals] = {}
        
    def reset(self):
        self._store.clear()
        
    async def get(self, user_id: int) -> UserSignals:
        if user_id not in self._store:
            self._store[user_id] = UserSignals()
        return self._store[user_id]
        
    async def save(self, user_id: int, signals: UserSignals):
        self._store[user_id] = signals

class RedisSignalStore(BaseSignalStore):
    """Redis-backed store for production horizontal scaling."""
    def __init__(self, redis_client):
        self.redis = redis_client

    def reset(self):
        """No-op for production Redis store in tests."""
        pass

    async def get(self, user_id: int) -> UserSignals:
        if not self.redis:
            return UserSignals()
        try:
            data = await self.redis.get(f"signals:{user_id}")
            if data:
                return UserSignals.model_validate_json(data)
        except Exception as e:
            logger.error(f"Error reading signals for {user_id}: {e}")
        return UserSignals()

    async def save(self, user_id: int, signals: UserSignals):
        if not self.redis:
            return
        try:
            await self.redis.set(f"signals:{user_id}", signals.model_dump_json())
        except Exception as e:
            logger.error(f"Error saving signals for {user_id}: {e}")

class SignalCollector:
    """Aggregates behavioral signals using an async datastore interface."""
    
    def __init__(self):
        self.store: BaseSignalStore = InMemorySignalStore()
        
    def configure(self, redis_client):
        """Inject Redis client on startup."""
        if redis_client:
            self.store = RedisSignalStore(redis_client)

    def reset(self):
        """Clears all signals from the current store (used for tests)."""
        if hasattr(self.store, 'reset'):
            self.store.reset()

    async def get_signals(self, user_id: int) -> UserSignals:
        return await self.store.get(user_id)
        
    async def _save(self, user_id: int, s: UserSignals):
        await self.store.save(user_id, s)
        
    async def record_action(self, user_id: int, is_expected_to_respond: bool = True):
        # We save this manually in the handlers that call it or implicitly when it wraps others.
        s = await self.get_signals(user_id)
        now = time.time()
        
        # Smart inactivity: Only strike if they were expected to say something
        if s.current_session_start > 0 and (now - s.last_action_time) > INACTIVITY_TIMEOUT_SEC:
            if is_expected_to_respond:
                s.inactivity_periods += 1
                
        s.last_action_time = now
        await self._save(user_id, s)
        
    async def record_session_start(self, user_id: int):
        s = await self.get_signals(user_id)
        s.session_count += 1
        s.matches_joined += 1
        s.current_session_messages = 0
        s.current_session_start = time.time()
        
        # Reset session sentiment
        s.session_sentiment_sum = 0.0
        s.session_sentiment_count = 0
        
        s.last_action_time = time.time()
        await self._save(user_id, s)
        
    async def record_message_sent(self, user_id: int, text: str = "", sentiment_score: Optional[float] = None):
        """Record an outbound message event with anti-spam and sentiment tracking."""
        s = await self.get_signals(user_id)
        
        length = len(text) if text else 0
        s.messages_sent += 1
        s.current_session_messages += 1
        s.last_action_time = time.time()
        
        # Copy-Paste Anti-Spam (naive check for long repeated strings)
        if length > 20:
            msg_hash = hashlib.md5(text.encode("utf-8")).hexdigest()
            if s.last_message_hash == msg_hash:
                s.copy_paste_streak += 1
            else:
                s.last_message_hash = msg_hash
                
        # Sentiment tracking
        if sentiment_score is not None:
            s.session_sentiment_sum += sentiment_score
            s.session_sentiment_count += 1
            
        await self._save(user_id, s)

    async def record_message_received(self, user_id: int):
        s = await self.get_signals(user_id)
        s.messages_received += 1
        await self._save(user_id, s)

    async def record_skip(self, user_id: int):
        """User pressed 'Next'."""
        s = await self.get_signals(user_id)
        now = time.time()
        s.matches_skipped += 1
        s.last_action_time = now
        
        if s.current_session_start > 0:
            duration = now - s.current_session_start
            s.total_time_to_skip += duration
            
            if duration < SKIP_THRESHOLD_SEC:
                s.rapid_skips += 1
                
            await self._end_session(user_id, s, duration)
        else:
            await self._save(user_id, s)
        
    async def record_disconnect(self, user_id: int):
        """User pressed 'Stop' or was disconnected."""
        s = await self.get_signals(user_id)
        now = time.time()
        s.last_action_time = now
        
        if s.current_session_start > 0:
            duration = now - s.current_session_start
            await self._end_session(user_id, s, duration)
        else:
            await self._save(user_id, s)
        
    async def record_report_received(self, user_id: int):
        """User was reported."""
        s = await self.get_signals(user_id)
        s.reports_received += 1
        await self._save(user_id, s)

    async def record_violation(self, user_id: int):
        """Record a content filter violation."""
        s = await self.get_signals(user_id)
        s.violation_count += 1
        s.last_violation_timestamp = time.time()
        s.last_action_time = time.time()
        await self._save(user_id, s)

    async def _end_session(self, user_id: int, s: UserSignals, duration: float):
        """Finalize metrics for a session and apply recovery/decay."""
        s.total_chat_duration += duration
        
        if s.current_session_messages >= MIN_MSG_GOOD_SESSION:
            s.good_sessions += 1
            # Recovery: decrement copy_paste_streak safely
            s.copy_paste_streak = max(0, s.copy_paste_streak - DECAY_PER_GOOD_SESSION)
        elif s.current_session_messages < 2 and duration < 15:
            s.bad_sessions += 1
            
        s.current_session_start = 0.0
        s.current_session_messages = 0
        await self._save(user_id, s)

# Global singleton wrapper
signal_collector = SignalCollector()
