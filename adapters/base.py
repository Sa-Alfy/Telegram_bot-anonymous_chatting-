# adapters/base.py

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional

class BaseAdapter(ABC):
    """Abstract Base Class for Platform Adapters (Telegram, Messenger).
    Ensures a strict contract for translating platform events to Core Logic
    and rendering Core State back to UI.
    """

    @abstractmethod
    async def translate_event(self, raw_update: Any) -> Optional[Dict[str, Any]]:
        """Maps platform-specific payload (Pyrogram Message, Messenger Webhook)
        to the standardized Event Contract Schema.
        """
        pass

    @abstractmethod
    async def render_state(self, user_id: str, state: str, payload: Optional[Dict[str, Any]] = None) -> bool:
        """Translates a deterministic State from the Core Engine into
        platform-specific UI elements. Returns True if render-ack is successful.
        """
        pass


    @abstractmethod
    async def send_error(self, user_id: str, error_msg: str):
        """Deterministic error reporting for the user."""
        pass

    def create_event(self, etype: str, uid: str, mid: Optional[str] = None, payload: Dict[str, Any] = None) -> Dict[str, Any]:
        """Helper to create a valid Event Contract object."""
        import time
        return {
            "event_type": etype,
            "user_id": uid,
            "match_id": mid,
            "timestamp": int(time.time()),
            "payload": payload or {}
        }
