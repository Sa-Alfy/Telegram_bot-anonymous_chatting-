# 🤖 Anonymous Telegram Chat Bot

A feature-rich, high-performance anonymous matchmaking bot for Telegram, inspired by platforms like Omegle. Built with Pyrogram, it features a robust economy, tiered leveling, seasonal events, and advanced matchmaking.

## ✨ Features

- **Anonymous Matchmaking**: Connect with strangers instantly.
- **Economy 2.0**: Earn coins/XP, buy boosters, and unlock exclusive badges.
- **Seasonal Events**: Weekly tournaments and daily mini-events (multipliers).
- **Social Features**: Friend system, reactions, and identity reveal.
- **Advanced UX**: Realistic typing simulations, connection animations, and milestones.
- **Admin Tools**: Real-time monitoring and event management.

## 🛠 Tech Stack

- **Language**: Python 3.10+
- **Framework**: [Pyrogram](https://docs.pyrogram.org/)
- **Data Storage**: JSON-based persistent storage (expandable to SQLite/PostgreSQL)
- **Environment**: Dotenv for secure configuration

## 🚀 Getting Started

### 1. Prerequisites
- Python 3.10 or higher
- A Telegram [API ID and Hash](https://my.telegram.org/apps)
- A Bot Token from [@BotFather](https://t.me/botfather)

### 2. Installation
```bash
# Clone the repository
git clone https://github.com/yourusername/anonymous-chat-bot.git
cd anonymous-chat-bot

# Create and activate virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 3. Configuration
Create a `.env` file in the root directory based on `.env.example`:
```env
API_ID=your_api_id
API_HASH=your_api_hash
BOT_TOKEN=your_bot_token
ADMIN_ID=your_telegram_id
```

### 4. Running the Bot
```bash
python anonymous_chat_bot/main.py
```

## 📂 Project Structure

- `handlers/`: Telegram update handlers (commands, callbacks, messages).
- `services/`: Core logic (matchmaking, economy, events, sessions).
- `state/`: Persistence and in-memory state management.
- `utils/`: UI components (keyboards), logging, and helpers.
- `data/`: Local storage for user profiles (ignored by git).

## 🛡 Security & Privacy
- Chat sessions are completely anonymous.
- No personal data is stored without explicit "Reveal Identity" actions.
- Secrets are managed via environment variables.

## 🛡 Ethical Usage & Responsibility

This project was created for **positive social interaction and community building**. By using this code, you agree to:
- **Respect Privacy**: Never use this bot to harass, dox, or harm individuals.
- **Moderate Responsibly**: Implement strict reporting and blocking systems to protect users.
- **Compliance**: Ensure your deployment complies with Telegram's Terms of Service and local laws.

The author is not responsible for any misuse of this software.

## 📄 License

This project is licensed under the **GNU General Public License v3 (GPLv3)**. This ensures that the software remains free and open-source, and any derivatives must also be released under the same protective terms. See the [LICENSE](LICENSE) file for details.
