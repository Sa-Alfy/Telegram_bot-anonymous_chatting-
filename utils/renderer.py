from typing import Dict, Any, List, Optional
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

class StateBoundPayload:
    @staticmethod
    def encode(action: str, target: str, state: str) -> str:
        """Encodes state into callback data. Max 64 bytes for Telegram."""
        return f"{action}:{target}:{state}"
        
    @staticmethod
    def decode(data: str) -> tuple[str, str, str]:
        """Decodes state payload into (action, target, expected_state).
        Robustly handles multi-part payloads (e.g. VOTE:sig:val:state) 
        by treating the first part as action and the LAST part as the state gate.
        """
        if not data or ":" not in data:
            return data or "", "", "HOME"
            
        parts = data.split(":")
        if len(parts) < 2:
            return data, "", "HOME"
            
        action = parts[0]
        state = parts[-1]
        # Target is everything in between
        target = ":".join(parts[1:-1]) if len(parts) > 2 else ""
        
        return action, target, state



# Render logic is now handled directly by platform-specific adapters:
# - adapters/telegram/keyboards.py
# - adapters/messenger/ui_factory.py
