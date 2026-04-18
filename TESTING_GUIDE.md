# Anonymous Chat Bot — Testing Guide

This guide explains how to thoroughly test the new cross‑platform Anonymous Chat Bot (Telegram ↔ Messenger).

## 1. Local Testing Setup (Telegram Only)

Since the Messenger webhook requires a public HTTPS URL (like Render), you might want to test the Telegram part locally first.

1. Install requirements:
   ```bash
   pip install -r requirements.txt
   ```
2. Set up the `.env` file (copy from `.env.example` and fill in `API_ID`, `API_HASH`, and `BOT_TOKEN`).
3. Leave `PAGE_ACCESS_TOKEN` and `VERIFY_TOKEN` empty.
4. Run the bot:
   ```bash
   python main.py
   ```
5. Open Telegram, start your bot, and verify all basic features work (/search, /stop, /stats).

## 2. Using ngrok for Local Messenger Testing

To test Messenger locally without deploying to Render, use `ngrok` to expose your local port 10000 to the internet.

1. Download and install ngrok.
2. Start ngrok on port 10000:
   ```bash
   ngrok http 10000
   ```
3. Copy the `https://xxxx.ngrok.app` URL provided by ngrok.
4. Set up `PAGE_ACCESS_TOKEN` and `VERIFY_TOKEN` in your `.env`.
5. Run your bot locally (`python main.py`).
6. Go to your Facebook Developer Dashboard → Webhooks → Edit Subscription.
7. Set Callback URL to `https://xxxx.ngrok.app/messenger-webhook`.
8. Set Verify Token to match your `.env`.
9. Send a message to your Facebook Page to test.

## 3. Production Testing (Post-Deployment)

Once deployed to Render (see `DEPLOYMENT_GUIDE.md`), perform the following tests:

### Cross-Platform Interaction
- **Scenario:** Match a Telegram user with a Messenger user.
- **Steps:**
  1. Open the bot on Telegram and press "Find Partner".
  2. Open the bot on Messenger (via Facebook Page) and press "Find Partner".
  3. Verify both accounts connect.
  4. Send a text from Telegram → verify it appears on Messenger.
  5. Send a text from Messenger → verify it appears on Telegram.
  6. Let the chat sit idle for 5 minutes and ensure the auto-disconnect fires.

### Economy & VIP Checks
- **Priority Match:** Use the Priority Match feature on both platforms. Ensure it deducts 5 coins correctly.
- **Identity Reveal:** Match two accounts. Ensure one has enough coins (15+). Perform an identity reveal. Verify the correct profile details are shown and the partner is notified.
- **Report Feature:** Press the "Report" button during a chat. Verify the chat ends immediately and the user is added to the database with a report count.

### Admin Dashboard (Telegram Only)
- Ensure your `ADMIN_ID` (Telegram ID) is in the `.env` file.
- Send `/admin` on Telegram.
- Verify you can see system stats, banned users, and perform a full system reset.
