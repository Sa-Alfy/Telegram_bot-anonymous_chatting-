# 🤖 Anonymous Telegram matchmaking Chat Bot

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python&logoColor=white)](https://www.python.org/)
[![Framework](https://img.shields.io/badge/Framework-Pyrogram-orange?logo=telegram&logoColor=white)](https://docs.pyrogram.org/)
[![Database](https://img.shields.io/badge/Database-SQLite-lightgrey?logo=sqlite&logoColor=white)](https://www.sqlite.org/)
[![License](https://img.shields.io/badge/License-GPLv3-green)](LICENSE)

A production-grade, high-performance anonymous matchmaking bot for Telegram. Designed for engagement, safety, and scalability, featuring a robust economy, social connectivity, and automated moderation.

---

## ✨ Key Features

### 🔄 Seamless Matchmaking
- **Instant Connection**: Find and chat with strangers in seconds.
- **Smart Filtering**: Match based on gender, location, or interests.
- **Rich Interaction**: Full support for text, media, and interactive buttons.

### 💰 Economy & Progression 2.0
- **Dynamic Leveling**: Earn XP through active chatting and complete challenges.
- **Coin System**: Earn coins to unlock premium features and boosters.
- **Boosters**: 2x XP and Coin multipliers for VIP users and special events.
- **Streaks**: Daily, Weekly, and Monthly login rewards to drive retention.

### 🤝 Social & Identity
- **Friend System**: Add favorite partners to your social circle for future chats.
- **Profile Customization**: Set your gender, location, and a unique bio.
- **Identity Reveal**: Safely share your profile info with trusted partners.

### 🛡️ Safety & Moderation
- **Auto-Block**: Users are automatically restricted after reaching report thresholds.
- **Appeal System**: Transparent process for users to request unblocking.
- **Admin Audit**: Detailed logs and real-time monitoring for administrators.

---

## 🛠️ Tech Stack

- **Core**: Python 3.10+ utilizing `asyncio` for high concurrency.
- **Telegram API**: [Pyrogram](https://docs.pyrogram.org/) (MTProto) for speed and flexibility.
- **Database**: SQLite with an asynchronous repository pattern for data integrity.
- **State Management**: In-memory tracking for active matches and queues.
- **Logging**: Comprehensive rotating logs for debugging and analytics.

---

## 🚀 Getting Started

### 1. Prerequisites
- Python 3.10 or higher.
- Telegram [API ID and Hash](https://my.telegram.org/apps).
- A Bot Token from [@BotFather](https://t.me/botfather).

### 2. Installation
```bash
# Clone the repository
git clone https://github.com/Sa-Alfy/Telegram_bot-anonymous_chatting-.git
cd "anonymous_chat_bot"

# Create and activate virtual environment
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 3. Configuration
Rename `.env.example` to `.env` and fill in your credentials:
```env
API_ID=1234567
API_HASH=your_api_hash_here
BOT_TOKEN=your_bot_token_here
ADMIN_ID=your_telegram_id
```

### 4. Running the Bot
```bash
python main.py
```

---

## 📂 Project Structure

```text
anonymous_chat_bot/
├── handlers/          # Telegram update handlers (UI/UX logic)
│   ├── actions/       # Specific features (matching, social, economy)
│   └── admin.py       # Admin-only commands
├── services/          # Business logic & background tasks
│   ├── matchmaking.py # The matching engine
│   ├── user_service.py # Economy and profile management
│   └── event_manager.py# Seasonal triggers and multipliers
├── database/          # SQLite schema and repositories
├── data/              # Persistent storage (SQLite DB, sessions, backups)
├── utils/             # Keyboard builders, formatters, and loggers
├── state/             # Real-time in-memory match tracking
└── main.py            # Application entry point
```

---

## 🔒 Security & Privacy

We prioritize user privacy:
- **Total Anonymity**: No identity data is shared by default.
- **Ephemeral Sessions**: Chat records are abstracted and strictly for rewards tracking.
- **Encryption**: Leverages Telegram's secure MTProto protocol.

---

## 📜 License

Distributed under the **GNU General Public License v3**. See [LICENSE](LICENSE) for more information.


