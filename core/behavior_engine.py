from typing import Optional
from core.signal_collector import signal_collector
from core.classifier import BehaviorClassifier, BehaviorProfile
from core.adaptation import SystemAdaptation

class BehaviorEngine:
    """Facade for the Behavioral Intelligence System."""

    collector = signal_collector

    @staticmethod
    def reset():
        """Reset the collector state (for tests)."""
        signal_collector.reset()

    # ── Signal Capture Hooks ──────────────────────────────────────────

    @staticmethod
    async def record_action(user_id: int, is_expected_to_respond: bool = True):
        await signal_collector.record_action(user_id, is_expected_to_respond)

    @staticmethod
    async def record_session_start(user_id: int):
        await signal_collector.record_session_start(user_id)

    @staticmethod
    async def record_message_sent(user_id: int, text: str = "", sentiment_score: Optional[float] = None):
        await signal_collector.record_message_sent(user_id, text, sentiment_score)

    @staticmethod
    async def record_message_received(user_id: int):
        await signal_collector.record_message_received(user_id)

    @staticmethod
    async def record_next(user_id: int):
        """Maps to record_skip in SignalCollector."""
        await signal_collector.record_skip(user_id)

    @staticmethod
    async def record_disconnect(user_id: int):
        await signal_collector.record_disconnect(user_id)

    @staticmethod
    async def record_report_given(user_id: int):
        """Legacy pass-through (if required by old API)"""
        s = await signal_collector.get_signals(user_id)
        s.reports_given += 1
        await signal_collector._save(user_id, s)
        await signal_collector.record_action(user_id)

    @staticmethod
    async def record_report_received(user_id: int):
        await signal_collector.record_report_received(user_id)

    @staticmethod
    async def record_violation(user_id: int):
        await signal_collector.record_violation(user_id)

    @staticmethod
    async def get_signals(user_id: int):
        return await signal_collector.get_signals(user_id)

    # ── Downstream Systems Adapters ─────────────────────────────────

    @staticmethod
    async def get_contextual_hint(user_id: int, state: str) -> Optional[str]:
        signals = await signal_collector.get_signals(user_id)
        profiles = BehaviorClassifier.classify(signals, xp=0)
        return SystemAdaptation.get_ux_hint(profiles, state)

    @staticmethod
    async def get_next_cooldown(user_id: int) -> float:
        signals = await signal_collector.get_signals(user_id)
        profiles = BehaviorClassifier.classify(signals, xp=0)
        return SystemAdaptation.get_next_cooldown(profiles, signals.rapid_skips)

    @staticmethod
    async def is_rapid_nexting(user_id: int) -> bool:
        signals = await signal_collector.get_signals(user_id)
        profiles = BehaviorClassifier.classify(signals, xp=0)
        return BehaviorProfile.FAST_SKIPPER in profiles

    @staticmethod
    async def get_match_score(user_id: int, base_reputation: int = 100, xp: int = 0) -> float:
        signals = await signal_collector.get_signals(user_id)
        profiles = BehaviorClassifier.classify(signals, xp)
        return SystemAdaptation.get_match_score(profiles, signals, base_reputation, xp)

    @staticmethod
    async def get_reward_multiplier(user_id: int) -> float:
        signals = await signal_collector.get_signals(user_id)
        profiles = BehaviorClassifier.classify(signals, xp=0)
        return SystemAdaptation.get_reward_multiplier(profiles)

    # ── UI/Legacy adapters ──────────────────────────────────────────
    @staticmethod
    async def get_adapted_chat_buttons(user_id: int) -> list:
        # Legacy stub for UX consistency
        return [
            {"title": "⏭ Next",     "payload": "NEXT"},
            {"title": "🛑 Stop",     "payload": "STOP"},
            {"title": "⚠️ Report",  "payload": "REPORT"},
            {"title": "🚫 Block",   "payload": "BLOCK_PARTNER"},
            {"title": "💌 Friend",  "payload": "ADD_FRIEND"},
        ]

    @staticmethod
    async def get_match_warning(user_id: int) -> Optional[str]:
        signals = await signal_collector.get_signals(user_id)
        profiles = BehaviorClassifier.classify(signals, xp=0)
        if BehaviorProfile.TOXIC_USER in profiles:
            return "⚠️ Please be respectful. Repeated reports may result in a ban."
        return None

    @staticmethod
    async def is_new_user(user_id: int) -> bool:
        """Legacy stub to determine if the user is new (for typing delays etc)."""
        from database.repositories.user_repository import UserRepository
        user = await UserRepository.get_by_telegram_id(user_id)
        return user is not None and user.get("total_matches", 0) <= 2

    @staticmethod
    async def get_typing_delay() -> float:
        """Legacy stub for realistic typing indicators."""
        import random
        return random.uniform(1.0, 2.5)

# Global singleton replacement
behavior_engine = BehaviorEngine()
