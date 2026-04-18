from pyrogram import Client, filters
from pyrogram.types import Message

@Client.on_message(filters.command("terms") & filters.private)
async def terms_command(client: Client, message: Message):
    text = (
        "⚖️ **Terms of Service**\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "1. You must be 18+ years old.\n"
        "2. No harassment, bullying, or hate speech.\n"
        "3. No spam, advertisements, or scams.\n"
        "4. No illegal content or solicitation.\n"
        "5. We reserve the right to ban users who violate these rules.\n\n"
        "For the full legal text, visit: https://neonymo-chat.onrender.com/terms"
    )
    await message.reply_text(text)

@Client.on_message(filters.command("privacy") & filters.private)
async def privacy_command(client: Client, message: Message):
    text = (
        "🛡️ **Privacy Policy**\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "1. We do not store your real identity.\n"
        "2. Messages are relayed in real-time and not logged permanently.\n"
        "3. We use a hashed ID to manage your session and stats.\n"
        "4. You can delete your data anytime via Settings.\n\n"
        "For the full legal text, visit: https://neonymo-chat.onrender.com/privacy"
    )
    await message.reply_text(text)
