# core/engine/state_machine.py

class UnifiedState:
    """Deterministic states for the Unified Matchmaking system."""
    HOME = "HOME"
    SEARCHING = "SEARCHING"
    MATCHED = "MATCHED"        # State after discovery, before sync
    CONNECTING = "CONNECTING"  # Handshake/Initialization phase
    CHAT_ACTIVE = "CHAT_ACTIVE"
    CHAT_END = "CHAT_END"      # Instant terminal state for chat
    VOTING = "VOTING"          # Hard gate that must be completed

    # List of all valid states for validation
    ALL_STATES = {
        HOME, SEARCHING, MATCHED, CONNECTING, CHAT_ACTIVE, CHAT_END, VOTING
    }

    # Strict transition map (Backend Truth)
    # format: { current_state: { set_of_allowed_next_states } }
    TRANSITIONS = {
        HOME: {SEARCHING},
        SEARCHING: {HOME, MATCHED},
        MATCHED: {CONNECTING, HOME}, # Allow HOME if partner cancels during match found
        CONNECTING: {CHAT_ACTIVE, CHAT_END},
        CHAT_ACTIVE: {CHAT_END},
        CHAT_END: {VOTING},          # UNCONDITIONAL GATE
        VOTING: {SEARCHING, HOME},   # Only exit once signals are complete
    }

    @classmethod
    def can_transition(cls, current: str, target: str) -> bool:
        """Validator for transitions. Used by the action router."""
        if current not in cls.TRANSITIONS:
            return False
        return target in cls.TRANSITIONS[current]

    @classmethod
    def is_safe_output_state(cls, state: str) -> bool:
        """Used by the Reconciler to determine if a state is UI-safe."""
        return state in {cls.CHAT_ACTIVE, cls.CHAT_END, cls.VOTING}
