"""
===============================================================================
File: core/classifier.py
Description: The rule engine for user behavioral classification.

How it works:
This module evaluates the raw signals collected by the SignalCollector and
maps them to specific behavioral profiles (e.g., 'FAST_SKIPPER', 'TOXIC_USER').
The logic is stateless and relies on predefined thresholds and "decay" 
mechanisms (where good behavior slowly cancels out historical bad behavior).

Architecture & Patterns:
- Rule Engine Pattern: Consolidates all heuristic "judgment" logic into a
  single, easily adjustable module.
- Enum-based Categories: Uses the BehaviorProfile Enum to provide strongly-typed
  labels that other services can consume.
- Stateless Evaluation: The 'classify' method is a pure function, making it 
  easy to test and debug.

How to modify:
- To add a new persona: Add a constant to the BehaviorProfile Enum.
- To adjust classification logic: Update the thresholds or rules inside the
  'classify' method.
===============================================================================
"""

from enum import Enum
from core.signal_collector import UserSignals
from core.config import BOT_SUSPECT_THRESHOLD, GOOD_SESSION_PENALTY_DIVISOR

class BehaviorProfile(Enum):
    """
    Standardized labels representing different user behavior types.
    """
    ACTIVE_CONVERSATIONALIST = "ACTIVE_CONVERSATIONALIST" # Deep chats, engaged
    EXPLORER = "EXPLORER"                     # High match count, solid duration
    PASSIVE_USER = "PASSIVE_USER"             # Few messages sent
    FAST_SKIPPER = "FAST_SKIPPER"             # Skips < 10s repeatedly
    STALLED_USER = "STALLED_USER"             # Goes inactive frequently
    TOXIC_USER = "TOXIC_USER"                 # High reports / bad sessions
    HIGH_VALUE_USER = "HIGH_VALUE_USER"       # Dedicated, good behavior
    BOT_SUSPECT = "BOT_SUSPECT"               # High copy_paste_streak
    NORMAL = "NORMAL"                         # Neutral ground

class BehaviorClassifier:
    """Pure stateless evaluator producing behavior profiles based on UserSignals."""
    
    @staticmethod
    def classify(signals: UserSignals, xp: int = 0) -> list:
        """Returns a list of all applicable BehaviorProfile labels for the user."""
        profiles = set()
        
        # Calculate derived/effective metrics (Decay logic)
        decay = signals.good_sessions // GOOD_SESSION_PENALTY_DIVISOR
        effective_bad_sessions = max(0, signals.bad_sessions - decay)
        effective_rapid_skips = max(0, signals.rapid_skips - decay)
        
        # Bot Suspect
        if signals.copy_paste_streak >= BOT_SUSPECT_THRESHOLD:
            profiles.add(BehaviorProfile.BOT_SUSPECT)
            
        # Risk / Toxic (highest precedence overrides some others visually, but we store all)
        if signals.reports_received >= 2 or effective_bad_sessions >= 8:
            profiles.add(BehaviorProfile.TOXIC_USER)
            
        # Fast Skipper
        if effective_rapid_skips >= 3:
            profiles.add(BehaviorProfile.FAST_SKIPPER)
            
        # New User
        if signals.session_count < 3 and signals.messages_sent < 10:
            profiles.add(BehaviorProfile.NEW_USER)
            
        # Passive User
        msg_per_session = signals.messages_sent / max(1, signals.session_count)
        if msg_per_session < 2 and signals.session_count >= 3:
            profiles.add(BehaviorProfile.PASSIVE_USER)
            
        # Active Conversationalist
        if msg_per_session > 10 and signals.reports_received == 0 and signals.good_sessions >= 2:
            profiles.add(BehaviorProfile.ACTIVE_CONVERSATIONALIST)
            
        # Explorer
        time_to_skip_avg = signals.total_time_to_skip / max(1, signals.matches_skipped)
        if signals.matches_joined > 10 and time_to_skip_avg > 30 and effective_rapid_skips == 0:
            profiles.add(BehaviorProfile.EXPLORER)
            
        # Stalled
        if signals.inactivity_periods > 5:
            profiles.add(BehaviorProfile.STALLED_USER)
            
        # High-Value
        if xp >= 500 and signals.reports_received == 0 and signals.good_sessions >= 5:
            profiles.add(BehaviorProfile.HIGH_VALUE_USER)
            
        if not profiles:
            profiles.add(BehaviorProfile.NORMAL)
            
        return list(profiles)
