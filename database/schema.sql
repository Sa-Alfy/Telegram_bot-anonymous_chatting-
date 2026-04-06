-- SQLite schema for Anonymous Chat Bot

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id INTEGER UNIQUE NOT NULL,
    username TEXT,
    first_name TEXT,
    gender TEXT DEFAULT 'Not specified',
    location TEXT DEFAULT 'Secret',
    bio TEXT DEFAULT 'No bio provided.',
    profile_photo TEXT,
    coins INTEGER DEFAULT 10,
    xp INTEGER DEFAULT 0,
    level INTEGER DEFAULT 1,
    vip_status BOOLEAN DEFAULT 0,
    total_matches INTEGER DEFAULT 0,
    total_chat_time INTEGER DEFAULT 0, -- in seconds
    daily_streak INTEGER DEFAULT 0,
    weekly_streak INTEGER DEFAULT 0,
    monthly_streak INTEGER DEFAULT 0,
    last_login INTEGER, -- timestamp
    last_active INTEGER, -- timestamp
    is_blocked BOOLEAN DEFAULT 0,
    is_guest BOOLEAN DEFAULT 1,
    json_data TEXT DEFAULT '{}' -- For extra/legacy fields
);

CREATE TABLE IF NOT EXISTS sessions (
    session_id INTEGER PRIMARY KEY AUTOINCREMENT,
    user1_id INTEGER NOT NULL,
    user2_id INTEGER NOT NULL,
    start_time INTEGER NOT NULL,
    end_time INTEGER,
    duration_seconds INTEGER DEFAULT 0,
    coins_earned1 INTEGER DEFAULT 0,
    coins_earned2 INTEGER DEFAULT 0,
    xp_earned1 INTEGER DEFAULT 0,
    xp_earned2 INTEGER DEFAULT 0,
    FOREIGN KEY (user1_id) REFERENCES users(telegram_id),
    FOREIGN KEY (user2_id) REFERENCES users(telegram_id)
);

CREATE TABLE IF NOT EXISTS reports_bans (
    report_id INTEGER PRIMARY KEY AUTOINCREMENT,
    reporter_id INTEGER NOT NULL,
    reported_id INTEGER NOT NULL,
    reason TEXT,
    status TEXT DEFAULT 'pending', -- pending, reviewed, rejected
    timestamp INTEGER NOT NULL,
    admin_review_id INTEGER,
    FOREIGN KEY (reporter_id) REFERENCES users(telegram_id),
    FOREIGN KEY (reported_id) REFERENCES users(telegram_id)
);

CREATE TABLE IF NOT EXISTS appeals (
    appeal_id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    reason TEXT NOT NULL,
    status TEXT DEFAULT 'pending', -- pending, accepted, rejected
    timestamp INTEGER NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(telegram_id)
);

CREATE TABLE IF NOT EXISTS reveal_history (
    reveal_id INTEGER PRIMARY KEY AUTOINCREMENT,
    revealer_id INTEGER NOT NULL,
    revealed_id INTEGER NOT NULL,
    reveal_type TEXT NOT NULL, -- partial, full
    cost INTEGER NOT NULL,
    timestamp INTEGER NOT NULL,
    FOREIGN KEY (revealer_id) REFERENCES users(telegram_id),
    FOREIGN KEY (revealed_id) REFERENCES users(telegram_id)
);

CREATE TABLE IF NOT EXISTS audit_logs (
    log_id INTEGER PRIMARY KEY AUTOINCREMENT,
    admin_id INTEGER NOT NULL,
    action TEXT NOT NULL,
    target_user_id INTEGER,
    details TEXT,
    timestamp INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS friends (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    friend_id INTEGER NOT NULL,
    status TEXT DEFAULT 'pending', -- pending, accepted
    created_at INTEGER NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(telegram_id),
    FOREIGN KEY (friend_id) REFERENCES users(telegram_id),
    UNIQUE(user_id, friend_id)
);

-- Indices for performance
CREATE INDEX IF NOT EXISTS idx_users_telegram_id ON users(telegram_id);
CREATE INDEX IF NOT EXISTS idx_sessions_users ON sessions(user1_id, user2_id);
CREATE INDEX IF NOT EXISTS idx_reports_reported ON reports_bans(reported_id);
CREATE INDEX IF NOT EXISTS idx_friends_users ON friends(user_id, friend_id);
