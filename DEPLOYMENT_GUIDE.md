# deployment_guide.md 

# Deployment Guide: Render.com

This guide covers deploying the dual-platform Anonymous Chat Bot to Render.com using the native Python environment, requiring zero local Python installations to get it running in production.

## Step 1: Create a Render Account and Web Service

1. Go to [Render.com](https://render.com/) and sign in.
2. Click **New** → **Web Service**.
3. Connect your GitHub account and select your repository containing the bot files.

## Step 2: Configure the Web Service

Render will auto-detect your `render.yaml` file, but if configuring manually:
- **Name:** anonymous-chat-bot
- **Environment:** Python 3
- **Build Command:** `pip install -r requirements.txt`
- **Start Command:** `python main.py`
- **Health Check Path:** `/health`

## Step 3: Add Environment Variables

In the Render dashboard for your web service, go to **Environment** and add the following keys. Do **NOT** enclose the values in quotes.

### Required values (Telegram)
- `API_ID`: Your Telegram API ID
- `API_HASH`: Your Telegram API Hash
- `BOT_TOKEN`: The bot token from @BotFather
- `ADMIN_ID`: Your personal Telegram ID

### Required values (Messenger)
- `PAGE_ACCESS_TOKEN`: The long token from your Facebook App dashboard.
- `VERIFY_TOKEN`: Make up a secure string (e.g., `my_secret_bot_123`).

## Step 4: Deploy and Setup Messenger Facebook Profile

1. Click **Deploy**. Render will download dependencies and start `main.py`.
2. Wait for the deploy to show "Live".
3. Copy your Render URL (e.g., `https://anonymous-chat-bot.onrender.com`).
4. **Important Webhook Setup:**
   - Go to your app on Facebook Developers.
   - Go to Webhooks.
   - Set the callback URL to `YOUR_RENDER_URL/messenger-webhook` (e.g., `https://anonymous-chat-bot.onrender.com/messenger-webhook`).
   - Set the Verify Token to what you entered in Step 3.

## Step 5: Initialize the Messenger UI

Because the Facebook UI requires one-time API calls to set up the Persistent Menu and "Get Started" button, we need to run `setup_messenger.py`. 

You can do this using the **Render Web Shell**:
1. Go to your Render Web Service dashboard.
2. Click on the **Shell** tab on the left sidebar.
3. Run the following command:
   ```bash
   python setup_messenger.py
   ```
4. You should see "✅ Setup complete" messages. 

## Step 6: Verify 

Your bot is now live!
- Message the bot on Telegram.
- Send a message to your Facebook Page.
- They should both respond contextually, and can be matched with each other!
