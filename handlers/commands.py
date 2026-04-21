from pyrogram import Client, filters
from pyrogram.types import Message
from handlers.actions.matching import MatchingHandler
from handlers.actions.social import SocialHandler
from handlers.actions.economy import EconomyHandler
from handlers.callbacks import handle_help
from utils.helpers import update_user_ui
from utils.keyboard import start_menu
from database.repositories.user_repository import UserRepository

@Client.on_message(filters.command("help") & filters.private)
async def help_cmd(client: Client, message: Message):
    user_id = message.from_user.id
    resp = await handle_help(client, user_id)
    await update_user_ui(client, user_id, resp["text"], resp.get("reply_markup"), force_new=True)

@Client.on_message(filters.command("stop") & filters.private)
async def stop_cmd(client: Client, message: Message):
    user_id = message.from_user.id
    resp = await MatchingHandler.handle_stop(client, user_id)
    await update_user_ui(client, user_id, resp["text"], resp.get("reply_markup"), force_new=True)

@Client.on_message(filters.command("next") & filters.private)
async def next_cmd(client: Client, message: Message):
    user_id = message.from_user.id
    resp = await MatchingHandler.handle_next(client, user_id)
    await update_user_ui(client, user_id, resp["text"], resp.get("reply_markup"), force_new=True)

@Client.on_message(filters.command(["find", "search", "match"]) & filters.private)
async def find_cmd(client: Client, message: Message):
    user_id = message.from_user.id
    resp = await MatchingHandler.handle_search(client, user_id)
    await update_user_ui(client, user_id, resp["text"], resp.get("reply_markup"), force_new=True)

@Client.on_message(filters.command(["shop", "store"]) & filters.private)
async def shop_cmd(client: Client, message: Message):
    user_id = message.from_user.id
    resp = await EconomyHandler.handle_seasonal_shop(client, user_id)
    await update_user_ui(client, user_id, resp["text"], resp.get("reply_markup"), force_new=True)

@Client.on_message(filters.command(["profile", "account", "me"]) & filters.private)
async def profile_cmd(client: Client, message: Message):
    user_id = message.from_user.id
    user = await UserRepository.get_by_telegram_id(user_id)
    is_guest = user.get("is_guest", True) if user else True
    
    from handlers.start import get_start_text
    coins = user.get("coins", 0) if user else 0
    await message.reply_text(
        get_start_text(coins, is_guest),
        reply_markup=start_menu(is_guest)
    )

@Client.on_message(filters.command("report") & filters.private)
async def report_cmd(client: Client, message: Message):
    user_id = message.from_user.id
    resp = await SocialHandler.handle_report(client, user_id)
    await update_user_ui(client, user_id, resp["text"], resp.get("reply_markup"))
