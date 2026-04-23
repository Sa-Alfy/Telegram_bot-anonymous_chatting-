from typing import List, Optional
from core.classifier import BehaviorProfile
from core.signal_collector import UserSignals
from core.config import (
    REPUTATION_WEIGHT, XP_WEIGHT, BEHAVIOR_WEIGHT, MAX_XP_FOR_NORMALIZATION,
    SENTIMENT_WEIGHT_MULTIPLIER, SENTIMENT_MIN_MSG_COUNT
)

class SystemAdaptation:
    """Translates user BehaviorProfiles into concrete system logic adaptations."""

    @staticmethod
    def get_match_score(profiles: List[BehaviorProfile], signals: UserSignals, base_reputation: int = 100, xp: int = 0) -> float:
        """
        Calculates a priority float for matchmaking queue logic.
        match_score = (reputation * 0.4) + (normalized_xp * 0.2) + (behavior_score * 0.4)
        """
        # Calculate base behavior_score starting at 50
        behavior_score = 50.0
        
        # Profile modifiers
        if BehaviorProfile.HIGH_VALUE_USER in profiles or BehaviorProfile.ACTIVE_CONVERSATIONALIST in profiles:
            behavior_score += 20.0
        if BehaviorProfile.FAST_SKIPPER in profiles:
            behavior_score -= 20.0
        if BehaviorProfile.TOXIC_USER in profiles or base_reputation <= -50:
            behavior_score -= 50.0 # Shadowban penalty
        if BehaviorProfile.BOT_SUSPECT in profiles:
            behavior_score -= 40.0
            
        # Add sentiment modifier
        if signals.session_sentiment_count >= SENTIMENT_MIN_MSG_COUNT:
            avg_sentiment = signals.session_sentiment_sum / signals.session_sentiment_count
            behavior_score += (avg_sentiment * SENTIMENT_WEIGHT_MULTIPLIER)
            
        # Clamp behavior score to 0..100
        behavior_score = max(0.0, min(100.0, behavior_score))
        
        # Max xp scaled to 100 for normalization
        normalized_xp = min(xp, MAX_XP_FOR_NORMALIZATION) / (MAX_XP_FOR_NORMALIZATION / 100)
        
        return (base_reputation * REPUTATION_WEIGHT) + (normalized_xp * XP_WEIGHT) + (behavior_score * BEHAVIOR_WEIGHT)

    @staticmethod
    def get_ux_hint(profiles: List[BehaviorProfile], current_state: str) -> Optional[str]:
        """Returns a string to inject into the UI flow based on observed patterns."""
        if BehaviorProfile.NEW_USER in profiles and current_state == "connected":
            return "Say hi! The other person is waiting."
            
        if BehaviorProfile.FAST_SKIPPER in profiles and current_state == "disconnected":
            return "You're switching quickly. Great conversations take a moment to start."
            
        if BehaviorProfile.STALLED_USER in profiles and current_state == "connected":
            return "Conversation stalled? Try a premium Icebreaker!"
            
        if BehaviorProfile.ACTIVE_CONVERSATIONALIST in profiles and current_state == "disconnected":
            return "Nice conversation! You're earning bonus engagement XP."
            
        if BehaviorProfile.BOT_SUSPECT in profiles and current_state == "disconnected":
            return "🤖 Please do not copy-paste repetitive messages. Engage naturally!"
            
        return None

    @staticmethod
    def get_reward_multiplier(profiles: List[BehaviorProfile]) -> float:
        """Determine scale factor for post-session coin/XP rewards."""
        multiplier = 1.0
        if BehaviorProfile.ACTIVE_CONVERSATIONALIST in profiles:
            multiplier += 0.5
        if BehaviorProfile.HIGH_VALUE_USER in profiles:
            multiplier += 0.5
        if BehaviorProfile.FAST_SKIPPER in profiles:
            multiplier -= 0.5
            
        if BehaviorProfile.TOXIC_USER in profiles or BehaviorProfile.BOT_SUSPECT in profiles:
            return 0.0 # Zero economy rewards for toxic matches
            
        return max(0.0, multiplier)

    @staticmethod
    def get_next_cooldown(profiles: List[BehaviorProfile], rapid_skips: int) -> float:
        """Calculate artificial delay applied when a user rapid-fires 'Next'."""
        if BehaviorProfile.BOT_SUSPECT in profiles:
            return 30.0 # Serious penalty
            
        if BehaviorProfile.FAST_SKIPPER in profiles:
            base = 3.0
            extra = max(0, (rapid_skips - 2)) * 2.0
            return min(base + extra, 15.0) # Cap at 15 seconds
        return 3.0 # Default cooldown
