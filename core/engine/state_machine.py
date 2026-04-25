# core/engine/state_machine.py

class UnifiedState:
    """Deterministic states for the Unified Matchmaking system."""
    HOME = "HOME"
    PREFERENCES = "PREFERENCES"
    SEARCHING = "SEARCHING"
    MATCHED = "MATCHED"        # State after discovery, before sync
    CONNECTING = "CONNECTING"  # Handshake/Initialization phase
    CHAT_ACTIVE = "CHAT_ACTIVE"
    CHAT_END = "CHAT_END"      # Instant terminal state for chat
    VOTING = "VOTING"
    PROFILE = "PROFILE"
    STATS = "STATS"
    REG_GENDER = "REG_GENDER"
    REG_INTERESTS = "REG_INTERESTS"
    REG_LOCATION = "REG_LOCATION"
    REG_BIO = "REG_BIO"

    # List of all valid states for validation
    ALL_STATES = {
        HOME, PREFERENCES, SEARCHING, MATCHED, CONNECTING, CHAT_ACTIVE, CHAT_END, VOTING, PROFILE, STATS,
        REG_GENDER, REG_INTERESTS, REG_LOCATION, REG_BIO
    }

    # Strict transition map (Backend Truth)
    # format: { current_state: { set_of_allowed_next_states } }
    TRANSITIONS = {
        HOME: {PREFERENCES, SEARCHING, PROFILE, STATS, REG_GENDER},
        PREFERENCES: {SEARCHING, HOME},
        SEARCHING: {HOME, MATCHED},
        MATCHED: {CONNECTING, HOME}, # Allow HOME if partner cancels during match found
        CONNECTING: {CHAT_ACTIVE, CHAT_END},
        CHAT_ACTIVE: {CHAT_END},
        CHAT_END: {VOTING, HOME},      
        VOTING: {SEARCHING, HOME, PROFILE, STATS},   # Only exit once signals are complete
        PROFILE: {HOME, SEARCHING, STATS, REG_GENDER},
        STATS: {HOME, SEARCHING, PROFILE},
        REG_GENDER: {REG_INTERESTS, HOME},
        REG_INTERESTS: {REG_LOCATION, HOME},
        REG_LOCATION: {REG_BIO, HOME},
        REG_BIO: {HOME}
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

    @classmethod
    def is_client_settable(cls, state: str) -> bool:
        """States that a user can manually navigate to via buttons."""
        return state in {cls.HOME, cls.PREFERENCES, cls.PROFILE, cls.STATS, cls.REG_GENDER, cls.SEARCHING}
