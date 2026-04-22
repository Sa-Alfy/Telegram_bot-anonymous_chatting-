import asyncio
import sys
import os

# Add project root to sys.path
sys.path.insert(0, r"f:\Code\Youniq")

import sys
import io
if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from utils.renderer import Renderer
from state.match_state import UserState

async def verify_renderer():
    print("--- Verifying Renderer Outputs ---")
    
    # 1. Preferences Menu
    tg_pref = Renderer.render_preferences_menu("telegram", UserState.HOME)
    msg_pref = Renderer.render_preferences_menu("messenger", UserState.HOME)
    
    print("\n[Telegram Preferences]")
    print(f"Text: {tg_pref['text']}")
    # InlineKeyboardMarkup is complex, just check presence
    print(f"Markup Present: {'reply_markup' in tg_pref}")
    
    print("\n[Messenger Preferences]")
    print(f"Text: {msg_pref['text']}")
    for qr in msg_pref['quick_replies']:
        print(f"  - {qr['title']}: {qr['payload']}")
    
    # 2. Searching UI
    tg_search = Renderer.render_searching_ui("telegram", UserState.SEARCHING)
    msg_search = Renderer.render_searching_ui("messenger", UserState.SEARCHING)
    
    print("\n[Telegram Searching]")
    print(f"Text: {tg_search['text']}")
    
    print("\n[Messenger Searching]")
    print(f"Text: {msg_search['text']}")
    for qr in msg_search['quick_replies']:
        print(f"  - {qr['title']}: {qr['payload']}")

    # 3. Match Found
    tg_match = Renderer.render_match_found("telegram", 12345)
    msg_match = Renderer.render_match_found("messenger", 12345)
    
    print("\n[Telegram Match Found]")
    print(f"Text: {tg_match['text']}")
    
    print("\n[Messenger Match Found]")
    print(f"Text: {msg_match['text']}")
    for qr in msg_match.get('quick_replies', []):
        print(f"  - {qr['title']}: {qr['payload']}")

async def main():
    await verify_renderer()

if __name__ == "__main__":
    asyncio.run(main())
