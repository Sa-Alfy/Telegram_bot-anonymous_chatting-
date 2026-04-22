# core/config.py
# Centralized configuration for the Behavioral Intelligence Engine.

# ── Magic Numbers & Thresholds ──────────────────────────────
SKIP_THRESHOLD_SEC = 10.0
INACTIVITY_TIMEOUT_SEC = 180.0
HIGH_VALUE_XP_THRESHOLD = 500
MIN_MSG_GOOD_SESSION = 5

# ── Matchmaking Formula Weights ─────────────────────────────
REPUTATION_WEIGHT = 0.4
XP_WEIGHT = 0.2
BEHAVIOR_WEIGHT = 0.4
MAX_XP_FOR_NORMALIZATION = 1000

# ── Anti-Spam & Penalty Decay ───────────────────────────────
COPY_PASTE_THRESHOLD = 3        # Streak before flagging as BOT_SUSPECT warning
BOT_SUSPECT_THRESHOLD = 5       # Streak where they get BOT_SUSPECT flag
DECAY_PER_GOOD_SESSION = 1      # Amount to reduce penalty counters per good session
GOOD_SESSION_PENALTY_DIVISOR = 5 # E.g., 5 good sessions removes 1 bad session / 1 rapid skip.

# ── Sentiment Evaluation ────────────────────────────────────
SENTIMENT_WEIGHT_MULTIPLIER = 15.0  # Max impact on behavior_score (+/- 15 points)
SENTIMENT_MIN_MSG_COUNT = 3         # Minimum messages in session before applying sentiment modifier
