# 🤖 Cross-Platform Anonymous Chat Bot

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python&logoColor=white)](https://www.python.org/)
[![Database](https://img.shields.io/badge/Database-PostgreSQL-blue?logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![State](https://img.shields.io/badge/State-Redis-red?logo=redis&logoColor=white)](https://redis.io/)
[![License](https://img.shields.io/badge/License-GPLv3-green)](LICENSE)

Welcome to **Neonymo** — a production-grade, Meta-compliant anonymous matchmaking bot. 

Think of it like Omegle, but built natively across **Telegram** and **Facebook Messenger**. 
Users on Telegram can seamlessly match and chat with strangers on Facebook Messenger (and vice versa) without ever revealing their real identity, phone number, or social media profile.

This project is built for high engagement with a built-in economy, XP system, VIP tiers, and an automated moderation system to keep chats safe.

---

## ✨ Features at a Glance

### 🔄 Cross-Platform Matchmaking
- **Unified Queue**: Telegram users and Messenger users exist in the same matchmaking pool.
- **Media Relay**: Native support for sending photos, videos, and stickers between platforms.
- **Voice/Video Room Bridging**: Users can generate secure Jitsi Meet rooms globally for anonymous calls.
- **Preference Tracking**: Users can configure their gender and request to match only with specific genders.

### 🧠 Behavioral Intelligence Engine
- **Reputation Tracking**: Real-time analysis of user behavior (rapid skips, message volume, report history).
- **Adaptive UX**: Contextual hints and warnings based on user activity.
- **Intelligent Cooldowns**: Dynamic matchmaking delays to discourage "speed-skipping" and abuse.
- **Match Scoring**: Improved pairing logic using behavioral profiles.

### 🗳️ Public Voting & Reputation
- **Community Rating**: Rate your partners with Likes or Dislikes after a session.
- **Gender Verification**: Peer-to-peer verification helps ensure the accuracy of gender preferences.
- **Social Proof**: Higher reputation leads to better matches and increased coin rewards.

### 💰 In-App Economy & Gamification
- **Leveling System**: Earn XP through active chatting and complete daily challenges.
- **Economy**: Earn and spend "Coins" in the Seasonal Shop.
- **VIP System**: Buy VIP access with coins to bypass cooldowns and earn 2x XP.
- **Streaks**: Daily, Weekly, and Monthly login rewards to drive user retention.

### 🎨 Premium UI/UX Experience
- **Visual Progression**: Dynamic XP progress bars `[███░░░]` in session summaries to visualize leveling.
- **Safety-First Navigation**: Decoupled "Stop" and "Next" buttons to prevent accidental chat termination.
- **Rich Messenger Media**: Transitioned from plain-text menus to Generic Template Cards and Shop Carousels on Facebook Messenger.
- **Smart Safety Reminders**: Throttled daily reminders to reduce visual clutter and "banner blindness."

### 🛡️ Safety, Moderation, & Meta Compliance
- **Consent Gates**: Mandatory Privacy & Terms of Service acceptance screens for new users.
- **Advanced Safety Pipeline**: Evasion-resistant filtering with Unicode normalization, stripping of zero-width characters, and multi-scan detection to block obscured keywords.
- **Behavior-Aware Enforcement**: Tiered response system where repeated violations escalate from warnings to chat termination and automatic banning.
- **Moderation Economy**: Automatic coin deductions based on violation severity (Warn: -10, Block: -25, Auto-Ban: -100).
- **GDPR / CCPA Erasure**: Self-service `/delete` command triggers total PII anonymization.
- **"24-Hour Rule" Enforcement**: Strict Facebook interaction tracking with API `v21.0` to ensure page safety.
- **User Block Lists**: Users can block partners to permanently prevent re-matching.

---

## 🛠️ How to Deploy (Step-by-Step Guide)

You do not need to be an experienced developer to host this bot, but there are a few accounts you will need to set up first. All of the services below offer generous **free tiers**.

### Step 1: Telegram Configuration
1. Talk to [@BotFather](https://t.me/botfather) on Telegram and send `/newbot` to create your bot. Copy the **Bot Token**.
2. Go to [my.telegram.org](https://my.telegram.org/apps), log in with your phone number, and create an Application. Copy your **API ID** and **API HASH**.

### Step 2: Database & Redis Configuration
This bot uses **PostgreSQL** to permanently store user profiles, and **Redis** for fast matchmaking state.
1. Create a free PostgreSQL database at [Supabase](https://supabase.com/). Go to Project Settings -> Database, and copy the **Connection string (URI)**.
2. Create a free Redis database at [Upstash](https://upstash.com/). Copy the **REDIS_URL**.

### Step 3: Facebook Messenger Configuration (Optional but Recommended)
*Skip this step if you only want the bot on Telegram.*
1. Create a Facebook Page.
2. Go to the [Meta Developer Portal](https://developers.facebook.com/) and create an App.
3. Add the **Messenger** product to your app.
4. Link your Facebook Page and generate a **Page Access Token (PAT)**.
5. In basic app settings, copy your **App Secret**.
6. Create an arbitrary password for your webhook verification (e.g., `my_secret_token_123`) — this is your **Verify Token**.

### Step 4: Local Installation & Testing
Clone the code to your local machine:
```bash
git clone https://github.com/Sa-Alfy/Telegram_bot-anonymous_chatting-.git
cd "Telegram_bot-anonymous_chatting--main"
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

Create a file named `.env` in the root directory and fill it with your keys:
```env
# Telegram
API_ID=your_api_id_here
API_HASH=your_api_hash_here
BOT_TOKEN=your_bot_token_here
ADMIN_ID=your_personal_telegram_id_here

# Internal Database
DATABASE_URL=postgres://user:pass@host:5432/dbname
REDIS_URL=rediss://default:pass@host:6379

# Facebook Messenger
PAGE_ACCESS_TOKEN=EAA...
VERIFY_TOKEN=my_secret_token_123
APP_SECRET=your_app_secret
FB_PAGE_ID=your_facebook_page_id
```

Run the bot:
```bash
python main.py
```
*If everything is correct, you will see `Pyrogram bot started successfully!`*

### Step 5: Messenger Webhook Setup (Production Only)
To get actual messages from Facebook, you must host this code online (e.g., Render, Heroku) because Facebook needs a public URL.

1. Deploy the code to an internet-accessible server.
2. Set all the `.env` variables in your server's dashboard.
3. In your Meta app dashboard, go to Webhooks and set the Callback URL to your server URL `https://your-server-url.com/messenger-webhook`. 
4. Enter the `VERIFY_TOKEN` you made up earlier.
5. Subscribe to `messages`, `messaging_postbacks`, and `messaging_optins`.
6. Once deployed, run the setup script to configure your Facebook Page's menus and Greetings:
   ```bash
   python setup_messenger.py
   ```

---

## 🕹️ Bot Commands

Users can control the bot via intuitive UI menus on Messenger or commands on Telegram:

| Command | Action |
| :--- | :--- |
| `/start` | Show the main dashboard and Hero Cards. |
| `/search` | Enter the matchmaking queue. |
| `/stop` | Disconnect from your current partner. |
| `/next` | Skip current partner and immediately find another. |
| `/profile` | Set your Gender, Age, Goal, Interests, and Bio. |
| `/shop` | Open the Seasonal Shop (Buy VIP or Priority queues). |
| `/stats` | View your level, XP, coins, and total matches. |
| `/report` | Report current partner for abuse (disconnects immediately). |
| `/block` | Block current partner permanently. |
| `/delete` | Completely erase your data from the database. |

### 🛠 Admin Commands
If your Telegram ID matches the `ADMIN_ID` in `.env`, you have access to:
| Command | Action |
| :--- | :--- |
| `/admin` | Open Administrative visual dashboard. |
| `/ban <id>` | Ban a user from the platform permanently. |
| `/gift <id> <qty>`| Gift coins directly to a user's balance. |
| `/broadcast <msg>`| Send an announcement to all users in the DB. |

---

## 📂 Project Architecture

```text
anonymous_bot/
├── main.py                    # Entry point (initializes DB, connects workers)
├── webhook_server.py          # Flask Webhook server (Messenger + Compliance)
├── messenger_handlers.py      # Unified messenger logic hub
├── messenger_api.py           # Facebook Graph API client
├── messenger/                 # Modular Messenger components
│   ├── dispatcher.py          # Event routing & verification
│   ├── ui.py                  # Component-based UI library
│   └── handlers/              # Feature-specific Messenger logic
├── core/                      # Behavioral Intelligence Engine
│   ├── behavior_engine.py     # Main signal facade
│   └── adaptation.py          # UX and logic adaptation
├── handlers/                  # Telegram UI and update routers
├── services/                  # Business logic (Economy, Matchmaking)
├── utils/                     # Content Filters, Rate Limiters, Loggers
├── database/                  # Postgres repositories & connection
└── state/                     # Match & User state tracking
```

---

## 📜 License & Acknowledgements

Distributed under the **GNU General Public License v3**. See [LICENSE](LICENSE) for more information.

We prioritize user privacy. No unhashed identity data is shared by default, chat records are entirely ephemeral and disappear the second a chat concludes, and logs are deeply scrubbed of internal Meta identifiers.
