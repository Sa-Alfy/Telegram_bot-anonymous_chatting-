-- PostgreSQL schema for Anonymous Chat Bot

CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    telegram_id BIGINT UNIQUE NOT NULL,
    username TEXT,
    first_name TEXT,
    gender TEXT DEFAULT 'Not specified',
    location TEXT DEFAULT 'Secret',
    bio TEXT DEFAULT 'No bio provided.',
    profile_photo TEXT,
    coins INTEGER DEFAULT 10,
    xp INTEGER DEFAULT 0,
    level INTEGER DEFAULT 1,
    vip_status BOOLEAN DEFAULT false,
    total_matches INTEGER DEFAULT 0,
    total_chat_time INTEGER DEFAULT 0, -- in seconds
    daily_streak INTEGER DEFAULT 0,
    weekly_streak INTEGER DEFAULT 0,
    monthly_streak INTEGER DEFAULT 0,
    last_login BIGINT, -- timestamp
    last_active BIGINT, -- timestamp
    is_blocked BOOLEAN DEFAULT false,
    is_guest BOOLEAN DEFAULT true,
    reports INTEGER DEFAULT 0,
    last_partner_id BIGINT,
    consent_given_at BIGINT, -- timestamp when user accepted privacy/ToS
    data_deleted_at BIGINT, -- timestamp when user data was soft-deleted (anonymized)
    json_data TEXT DEFAULT '{}', -- For extra/legacy fields
    likes INTEGER DEFAULT 0,
    dislikes INTEGER DEFAULT 0,
    votes_male INTEGER DEFAULT 0,
    votes_female INTEGER DEFAULT 0,
    verified_gender TEXT -- 'male', 'female', or NULL
);

-- Public voting records to prevent double voting
CREATE TABLE IF NOT EXISTS user_votes (
    id SERIAL PRIMARY KEY,
    voter_id BIGINT NOT NULL,
    voted_id BIGINT NOT NULL,
    vote_type TEXT, -- 'like', 'dislike'
    gender_vote TEXT, -- 'male', 'female'
    created_at BIGINT NOT NULL,
    FOREIGN KEY (voter_id) REFERENCES users(telegram_id),
    FOREIGN KEY (voted_id) REFERENCES users(telegram_id),
    UNIQUE(voter_id, voted_id)
);

-- Per-user block list (prevents re-matching)
CREATE TABLE IF NOT EXISTS blocked_users (
    id SERIAL PRIMARY KEY,
    blocker_id BIGINT NOT NULL,
    blocked_id BIGINT NOT NULL,
    created_at BIGINT NOT NULL,
    FOREIGN KEY (blocker_id) REFERENCES users(telegram_id),
    FOREIGN KEY (blocked_id) REFERENCES users(telegram_id),
    UNIQUE(blocker_id, blocked_id)
);

CREATE TABLE IF NOT EXISTS sessions (
    session_id SERIAL PRIMARY KEY,
    user1_id BIGINT NOT NULL,
    user2_id BIGINT NOT NULL,
    start_time BIGINT NOT NULL,
    end_time BIGINT,
    duration_seconds INTEGER DEFAULT 0,
    coins_earned1 INTEGER DEFAULT 0,
    coins_earned2 INTEGER DEFAULT 0,
    xp_earned1 INTEGER DEFAULT 0,
    xp_earned2 INTEGER DEFAULT 0,
    FOREIGN KEY (user1_id) REFERENCES users(telegram_id),
    FOREIGN KEY (user2_id) REFERENCES users(telegram_id)
);

CREATE TABLE IF NOT EXISTS reports_bans (
    report_id SERIAL PRIMARY KEY,
    reporter_id BIGINT NOT NULL,
    reported_id BIGINT NOT NULL,
    reason TEXT,
    status TEXT DEFAULT 'pending', -- pending, reviewed, rejected
    timestamp BIGINT NOT NULL,
    admin_review_id BIGINT,
    FOREIGN KEY (reporter_id) REFERENCES users(telegram_id),
    FOREIGN KEY (reported_id) REFERENCES users(telegram_id)
);

CREATE TABLE IF NOT EXISTS appeals (
    appeal_id SERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    reason TEXT NOT NULL,
    status TEXT DEFAULT 'pending', -- pending, accepted, rejected
    timestamp BIGINT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(telegram_id)
);

CREATE TABLE IF NOT EXISTS reveal_history (
    reveal_id SERIAL PRIMARY KEY,
    revealer_id BIGINT NOT NULL,
    revealed_id BIGINT NOT NULL,
    reveal_type TEXT NOT NULL, -- partial, full
    cost INTEGER NOT NULL,
    timestamp BIGINT NOT NULL,
    FOREIGN KEY (revealer_id) REFERENCES users(telegram_id),
    FOREIGN KEY (revealed_id) REFERENCES users(telegram_id)
);

CREATE TABLE IF NOT EXISTS audit_logs (
    log_id SERIAL PRIMARY KEY,
    admin_id BIGINT NOT NULL,
    action TEXT NOT NULL,
    target_user_id BIGINT,
    details TEXT,
    timestamp BIGINT NOT NULL
);

CREATE TABLE IF NOT EXISTS friends (
    id SERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    friend_id BIGINT NOT NULL,
    status TEXT DEFAULT 'pending', -- pending, accepted
    created_at BIGINT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(telegram_id),
    FOREIGN KEY (friend_id) REFERENCES users(telegram_id),
    UNIQUE(user_id, friend_id)
);

-- Indices for performance
CREATE INDEX IF NOT EXISTS idx_users_telegram_id ON users(telegram_id);
CREATE INDEX IF NOT EXISTS idx_sessions_users ON sessions(user1_id, user2_id);
CREATE INDEX IF NOT EXISTS idx_reports_reported ON reports_bans(reported_id);
CREATE INDEX IF NOT EXISTS idx_friends_users ON friends(user_id, friend_id);
CREATE INDEX IF NOT EXISTS idx_blocked_users ON blocked_users(blocker_id, blocked_id);
