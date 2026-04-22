"""
═══════════════════════════════════════════════════════════════════
test_cross_platform_chat.py
Cross-platform integration mock tests.

Covers all three pairing combinations:
  - TG  ↔ TG   (both users on Telegram)
  - TG  ↔ MSG  (Telegram matched with Messenger)
  - MSG ↔ MSG  (both users on Facebook Messenger)

Each scenario tests:
  1. Both users join queue
  2. Match is found (atomic claim succeeds)
  3. initialize_match sends correct UI to each platform
  4. Messages relay to the correct platform
  5. Either user can stop; both receive the end-menu
  6. Both users are HOME / partner-less after disconnect

No real Redis, DB, Telegram, or Messenger API calls are made.

Patch target rules (tracing actual import chains):
  - behavior_engine  → "core.behavior_engine.behavior_engine.*"
      (it is always imported lazily inside functions in matchmaking.py)
  - UserRepository   → "database.repositories.user_repository.UserRepository.*"
      (top-level import in matchmaking.py, also used in initialize_match)
  - UserService      → "services.user_service.UserService.*"
  - SessionRepository→ "database.repositories.session_repository.SessionRepository.*"
  - BlockedRepository→ "database.repositories.blocked_repository.BlockedRepository.*"
  - Messenger API    → "messenger_api.send_message" / "messenger_api.send_quick_replies"
  - messenger_handlers API refs → "messenger_handlers.send_message" etc.
═══════════════════════════════════════════════════════════════════
"""
import asyncio
import time
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

# ─── IDs ──────────────────────────────────────────────────────────────────────
TG_USER_A  = 1001
TG_USER_B  = 1002
# Messenger virtual IDs are ≥ 10**15 (platform routing convention)
MSG_USER_C_VID  = 10**15 + 1001
MSG_USER_D_VID  = 10**15 + 2002
MSG_USER_C_PSID = "psid_user_c"
MSG_USER_D_PSID = "psid_user_d"


# ─── User row factory ─────────────────────────────────────────────────────────
def _make_user(virtual_id: int, psid: str | None = None, coins: int = 100) -> dict:
    """Minimal DB row returned by UserRepository.get_by_telegram_id()."""
    username = f"msg_{psid}" if psid else f"tg_{virtual_id}"
    return {
        "telegram_id":      virtual_id,
        "username":         username,
        "first_name":       f"User{virtual_id}",
        "gender":           "Not specified",
        "coins":            coins,
        "xp":               0,
        "level":            1,
        "total_matches":    0,
        "is_guest":         False,
        "is_blocked":       False,
        "priority_pack":    {},
        "priority_matches": 0,
        "coin_booster":     {},
        "reports":          0,
        "consent_given_at": int(time.time()),
        "safety_last_seen": 0,
        "vip_status":       False,
        "last_partner_id":  None,
    }


# ─────────────────────────────────────────────────────────────────────────────
# FIXTURE: fully mocked environment
# ─────────────────────────────────────────────────────────────────────────────
@pytest.fixture()
def mock_env():
    """
    Provides a clean mocked environment.
    Resets distributed_state and match_state singletons, then patches
    all external I/O (DB, Telegram client, Messenger API).
    """
    from services.distributed_state import distributed_state
    from state.match_state import match_state

    # ── Reset singletons in-place ─────────────────────────────────────────
    distributed_state._fallback_store.clear()
    distributed_state.redis = None
    match_state.waiting_queue.clear()
    match_state.active_chats.clear()
    match_state.user_preferences.clear()
    match_state.rematch_requests.clear()
    match_state.chat_start_times.clear()
    match_state.user_ui_messages.clear()
    match_state.user_states.clear()
    match_state.last_button_time.clear()
    # Refresh the asyncio.Lock so it's bound to the current event loop (avoids cross-loop deadlock)
    match_state._lock = asyncio.Lock()

    # ── Shared user table (populated per test class) ──────────────────────
    users: dict = {}

    # ── Mock Telegram client ──────────────────────────────────────────────
    tg_client = MagicMock()
    tg_client.send_message = AsyncMock(return_value=MagicMock(id=9999))

    # ── Capture Messenger API calls ───────────────────────────────────────
    sent_messages:    list = []   # (psid, text)
    sent_quick_replies: list = [] # (psid, text, buttons)

    def _cap_msg(psid, text):
        sent_messages.append((psid, text))

    def _cap_qr(psid, text, buttons):
        sent_quick_replies.append((psid, text, buttons))

    # ── DB helpers (routed by virtual_id) ─────────────────────────────────
    async def _repo_get(vid):
        return users.get(vid)

    async def _repo_update(vid, **kw):
        if vid in users:
            users[vid].update(kw)

    async def _repo_inc_coins(vid, amount):
        if vid in users:
            users[vid]["coins"] = users[vid].get("coins", 0) + amount

    env = {
        "tg_client":          tg_client,
        "sent_messages":      sent_messages,
        "sent_quick_replies": sent_quick_replies,
        "users":              users,
    }

    # Use ExitStack — Python 3.13 limits static with-nesting to ~20 blocks.
    from contextlib import ExitStack

    _patches = [
        # ── core.behavior_engine (lazy-imported inside every matchmaking fn) ──
        patch("core.behavior_engine.behavior_engine.get_match_score",
              new_callable=AsyncMock, return_value=50.0),
        patch("core.behavior_engine.behavior_engine.record_session_start",
              new_callable=AsyncMock),
        patch("core.behavior_engine.behavior_engine.get_contextual_hint",
              new_callable=AsyncMock, return_value=None),
        patch("core.behavior_engine.behavior_engine.get_reward_multiplier",
              new_callable=AsyncMock, return_value=1.0),
        patch("core.behavior_engine.behavior_engine.record_disconnect",
              new_callable=AsyncMock),
        patch("core.behavior_engine.behavior_engine.get_adapted_chat_buttons",
              new_callable=AsyncMock, return_value=[]),
        patch("core.behavior_engine.behavior_engine.is_new_user",
              new_callable=AsyncMock, return_value=False),
        patch("core.behavior_engine.behavior_engine.get_match_warning",
              new_callable=AsyncMock, return_value=None),
        patch("core.behavior_engine.behavior_engine.get_next_cooldown",
              new_callable=AsyncMock, return_value=0.0),
        # ── Database ──────────────────────────────────────────────────────────
        patch("database.repositories.user_repository.UserRepository.get_by_telegram_id",
              new_callable=AsyncMock, side_effect=_repo_get),
        patch("database.repositories.user_repository.UserRepository.update",
              new_callable=AsyncMock, side_effect=_repo_update),
        patch("database.repositories.user_repository.UserRepository.increment_coins",
              new_callable=AsyncMock, side_effect=_repo_inc_coins),
        patch("database.repositories.session_repository.SessionRepository.create_and_end",
              new_callable=AsyncMock),
        patch("database.repositories.blocked_repository.BlockedRepository.is_mutually_blocked",
              new_callable=AsyncMock, return_value=False),
        # ── UserService ───────────────────────────────────────────────────────
        patch("services.user_service.UserService.add_coins",
              new_callable=AsyncMock, return_value=True),
        patch("services.user_service.UserService.add_xp",
              new_callable=AsyncMock, return_value=False),
        patch("services.user_service.UserService.increment_challenge",
              new_callable=AsyncMock),
        patch("services.user_service.UserService.deduct_coins",
              new_callable=AsyncMock, return_value=True),
        # ── EventManager ──────────────────────────────────────────────────────
        patch("services.event_manager.get_active_event",
              return_value={"multiplier": 1.0}),
        # ── Messenger API ─────────────────────────────────────────────────────
        patch("messenger_api.send_message",       side_effect=_cap_msg),
        patch("messenger_api.send_quick_replies",  side_effect=_cap_qr),
        patch("messenger_handlers.send_message",   side_effect=_cap_msg),
        patch("messenger_handlers.send_quick_replies", side_effect=_cap_qr),
        patch("adapters.messenger.adapter.send_message", side_effect=_cap_msg),
        patch("adapters.messenger.adapter.send_quick_replies", side_effect=_cap_qr),
        patch("adapters.messenger.adapter.send_generic_template", side_effect=lambda *a, **kw: None),
        # ── Telegram helpers ──────────────────────────────────────────────────
        patch("utils.helpers.update_user_ui", new_callable=AsyncMock),
    ]

    # ── Hook up Unified Engine Adapters ───────────────────────────────────
    import app_state
    from adapters.telegram.adapter import TelegramAdapter
    from adapters.messenger.adapter import MessengerAdapter
    from core.engine.actions import ActionRouter
    
    # 1. Mock Engine
    engine = AsyncMock()
    
    async def mock_process_event(event):
        etype = event["event_type"]
        uid = event["user_id"]
        # Simulate state transitions for rehydration
        state = "HOME"
        if etype == "CONNECT": state = "CHAT_ACTIVE"
        elif etype == "START_SEARCH": state = "SEARCHING"
        elif etype in ("STOP", "END_CHAT"): state = "VOTING"
        elif etype == "SET_STATE": state = event.get("payload", {}).get("new_state", "HOME")
        
        # Sync state back to match_state/distributed_state so legacy lookups work
        from database.repositories.user_repository import UserRepository
        vid = UserRepository._sanitize_id(uid)
        await distributed_state.set_user_state(vid, state)
        
        # Trigger adapter rehydration
        is_msg = str(uid).startswith("msg_") or int(vid) >= 10**15
        adapter = app_state.msg_adapter if is_msg else app_state.tg_adapter
        await adapter.render_state(uid, state, event.get("payload", {}))
        
        # If CONNECT, notify partner too
        if etype == "CONNECT":
            p_id = await match_state.get_partner(int(vid))
            if p_id:
                p_uid = str(p_id)
                is_p_msg = p_uid.startswith("msg_") or int(p_id) >= 10**15
                p_adapter = app_state.msg_adapter if is_p_msg else app_state.tg_adapter
                await p_adapter.render_state(p_uid, state, {})
        
        return {"success": True, "state": state}

    engine.process_event.side_effect = mock_process_event
    app_state.engine = engine

    # 2. Setup Adapters
    # Telegram
    app_state.tg_adapter = TelegramAdapter(tg_client)
    # Messenger
    app_state.msg_adapter = MessengerAdapter()

    with ExitStack() as stack:
        for p in _patches:
            stack.enter_context(p)
        yield env


# ─── Queue + match helper ─────────────────────────────────────────────────────
async def _queue_and_match(env, uid_a, uid_b) -> int | None:
    """Put both users in queue and return partner found for uid_a."""
    from services.matchmaking import MatchmakingService
    await MatchmakingService.add_to_queue(uid_a, gender_pref="Any")
    await MatchmakingService.add_to_queue(uid_b, gender_pref="Any")
    return await MatchmakingService.find_partner(env["tg_client"], uid_a)


async def _partner(uid) -> str | None:
    from state.match_state import match_state
    return await match_state.get_partner(uid)


async def _state(uid) -> str | None:
    from state.match_state import match_state
    return await match_state.get_user_state(uid)


# ═════════════════════════════════════════════════════════════════════════════
# SCENARIO 1 — Telegram ↔ Telegram
# ═════════════════════════════════════════════════════════════════════════════
class TestTelegramToTelegram:

    @pytest.fixture(autouse=True)
    def _seed(self, mock_env):
        mock_env["users"].update({
            TG_USER_A: _make_user(TG_USER_A),
            TG_USER_B: _make_user(TG_USER_B),
        })
        self.env = mock_env

    # ── 1. Match connects ─────────────────────────────────────────────────────
    @pytest.mark.asyncio
    async def test_match_connects(self):
        """TG-A and TG-B are paired; both store each other as partner."""
        partner = await _queue_and_match(self.env, TG_USER_A, TG_USER_B)

        assert partner == TG_USER_B, "find_partner must return TG_USER_B"
        assert await _partner(TG_USER_A) in (TG_USER_B, str(TG_USER_B))
        assert await _partner(TG_USER_B) in (TG_USER_A, str(TG_USER_A))

    # ── 2. initialize_match notifies both TG users ────────────────────────────
    @pytest.mark.asyncio
    async def test_initialize_match_notifies_both(self):
        """Both Telegram users receive a send_message call after initialize_match."""
        from services.matchmaking import MatchmakingService

        await _queue_and_match(self.env, TG_USER_A, TG_USER_B)
        self.env["tg_client"].send_message.reset_mock()

        await MatchmakingService.initialize_match(
            self.env["tg_client"], TG_USER_A, TG_USER_B
        )

        chat_ids = {
            c.kwargs.get("chat_id") or c.args[0]
            for c in self.env["tg_client"].send_message.call_args_list
        }
        assert TG_USER_A in chat_ids, "TG_USER_A must be notified"
        assert TG_USER_B in chat_ids, "TG_USER_B must be notified"

    # ── 3. Message relay TG → TG ──────────────────────────────────────────────
    @pytest.mark.asyncio
    async def test_message_relay_tg_to_tg(self):
        """Message from TG-A reaches TG-B via tg_client.send_message."""
        from messenger_handlers import _notify_user
        import app_state

        await _queue_and_match(self.env, TG_USER_A, TG_USER_B)
        app_state.telegram_app = self.env["tg_client"]
        self.env["tg_client"].send_message.reset_mock()

        await _notify_user(TG_USER_B, "💬 Hello from A")

        chat_ids = [
            c.kwargs.get("chat_id") or c.args[0]
            for c in self.env["tg_client"].send_message.call_args_list
        ]
        assert TG_USER_B in chat_ids, "TG_USER_B must receive the relayed message"

    # ── 4. Stop resets both users to HOME ─────────────────────────────────────
    @pytest.mark.asyncio
    async def test_stop_resets_both_states(self):
        """After disconnect, neither user has a partner."""
        from services.matchmaking import MatchmakingService
        from state.match_state import match_state, UserState

        await _queue_and_match(self.env, TG_USER_A, TG_USER_B)
        await match_state.set_user_state(TG_USER_A, UserState.CHATTING)
        await match_state.set_user_state(TG_USER_B, UserState.CHATTING)

        stats = await MatchmakingService.disconnect(TG_USER_A)

        assert stats is not None, "disconnect must return stats"
        assert stats["partner_id"] == TG_USER_B
        assert await _partner(TG_USER_A) is None
        assert await _partner(TG_USER_B) is None


# ═════════════════════════════════════════════════════════════════════════════
# SCENARIO 2 — Messenger ↔ Messenger
# ═════════════════════════════════════════════════════════════════════════════
class TestMessengerToMessenger:

    @pytest.fixture(autouse=True)
    def _seed(self, mock_env):
        mock_env["users"].update({
            MSG_USER_C_VID: _make_user(MSG_USER_C_VID, psid=MSG_USER_C_PSID),
            MSG_USER_D_VID: _make_user(MSG_USER_D_VID, psid=MSG_USER_D_PSID),
        })
        self.env = mock_env

    @pytest.mark.asyncio
    async def test_match_connects(self):
        """MSG-C and MSG-D are paired; both store each other as partner."""
        partner = await _queue_and_match(self.env, MSG_USER_C_VID, MSG_USER_D_VID)

        assert partner == MSG_USER_D_VID
        assert await _partner(MSG_USER_C_VID) in (MSG_USER_D_VID, str(MSG_USER_D_VID))
        assert await _partner(MSG_USER_D_VID) in (MSG_USER_C_VID, str(MSG_USER_C_VID))

    @pytest.mark.asyncio
    async def test_initialize_match_sends_quick_replies_to_both(self):
        """Both Messenger PSIDs receive send_quick_replies on initialize_match."""
        from services.matchmaking import MatchmakingService

        await _queue_and_match(self.env, MSG_USER_C_VID, MSG_USER_D_VID)
        self.env["sent_quick_replies"].clear()

        await MatchmakingService.initialize_match(
            self.env["tg_client"], MSG_USER_C_VID, MSG_USER_D_VID
        )

        psids = {call[0] for call in self.env["sent_quick_replies"]}
        assert MSG_USER_C_PSID in psids, "MSG-C must receive a quick_reply"
        assert MSG_USER_D_PSID in psids, "MSG-D must receive a quick_reply"

    @pytest.mark.asyncio
    async def test_chat_menu_buttons_use_chatting_state(self):
        """Buttons sent on match-found must include Stop/Next (chat controls)."""
        from services.matchmaking import MatchmakingService

        await _queue_and_match(self.env, MSG_USER_C_VID, MSG_USER_D_VID)
        self.env["sent_quick_replies"].clear()

        await MatchmakingService.initialize_match(
            self.env["tg_client"], MSG_USER_C_VID, MSG_USER_D_VID
        )

        all_buttons = str(self.env["sent_quick_replies"])
        assert "STOP" in all_buttons or "NEXT" in all_buttons, \
            "Chat buttons (STOP/NEXT) must be present in Messenger match notification"

    @pytest.mark.asyncio
    async def test_message_relay_msg_to_msg(self):
        """Text sent by MSG-C must arrive at MSG-D's PSID via _notify_user."""
        from messenger_handlers import _notify_user
        from state.match_state import match_state, UserState

        await _queue_and_match(self.env, MSG_USER_C_VID, MSG_USER_D_VID)
        await match_state.set_user_state(MSG_USER_D_VID, UserState.CHATTING)

        self.env["sent_quick_replies"].clear()
        self.env["sent_messages"].clear()

        with patch(
            "messenger_handlers.UserRepository.get_by_telegram_id",
            new_callable=AsyncMock,
            return_value=_make_user(MSG_USER_D_VID, psid=MSG_USER_D_PSID),
        ):
            await _notify_user(MSG_USER_D_VID, "💬 Hello from C")

        all_targets = (
            [m[0] for m in self.env["sent_quick_replies"]]
            + [m[0] for m in self.env["sent_messages"]]
        )
        assert MSG_USER_D_PSID in all_targets, \
            "MSG-D PSID must receive the relayed message"

    @pytest.mark.asyncio
    async def test_stop_resets_both_states(self):
        """After disconnect, neither MSG user retains a partner."""
        from services.matchmaking import MatchmakingService
        from state.match_state import match_state, UserState

        await _queue_and_match(self.env, MSG_USER_C_VID, MSG_USER_D_VID)
        await match_state.set_user_state(MSG_USER_C_VID, UserState.CHATTING)
        await match_state.set_user_state(MSG_USER_D_VID, UserState.CHATTING)

        stats = await MatchmakingService.disconnect(MSG_USER_C_VID)

        assert stats is not None
        assert stats["partner_id"] == MSG_USER_D_VID
        assert await _partner(MSG_USER_C_VID) is None
        assert await _partner(MSG_USER_D_VID) is None


# ═════════════════════════════════════════════════════════════════════════════
# SCENARIO 3 — Telegram ↔ Messenger (cross-platform)
# ═════════════════════════════════════════════════════════════════════════════
class TestTelegramToMessenger:

    @pytest.fixture(autouse=True)
    def _seed(self, mock_env):
        mock_env["users"].update({
            TG_USER_A:      _make_user(TG_USER_A),
            MSG_USER_C_VID: _make_user(MSG_USER_C_VID, psid=MSG_USER_C_PSID),
        })
        self.env = mock_env

    @pytest.mark.asyncio
    async def test_match_connects(self):
        """TG-A and MSG-C are paired atomically."""
        partner = await _queue_and_match(self.env, TG_USER_A, MSG_USER_C_VID)

        assert partner == MSG_USER_C_VID
        assert await _partner(TG_USER_A) in (MSG_USER_C_VID, str(MSG_USER_C_VID))
        assert await _partner(MSG_USER_C_VID) in (TG_USER_A, str(TG_USER_A))

    @pytest.mark.asyncio
    async def test_initialize_match_sends_to_correct_platforms(self):
        """
        initialize_match must:
        - send_message to TG-A via tg_client.send_message
        - send_quick_replies to MSG-C via Messenger API
        """
        from services.matchmaking import MatchmakingService

        await _queue_and_match(self.env, TG_USER_A, MSG_USER_C_VID)
        self.env["tg_client"].send_message.reset_mock()
        self.env["sent_quick_replies"].clear()

        await MatchmakingService.initialize_match(
            self.env["tg_client"], TG_USER_A, MSG_USER_C_VID
        )

        tg_ids = {
            c.kwargs.get("chat_id") or c.args[0]
            for c in self.env["tg_client"].send_message.call_args_list
        }
        assert TG_USER_A in tg_ids, "TG-A must be notified via tg_client"

        msg_psids = {m[0] for m in self.env["sent_quick_replies"]}
        assert MSG_USER_C_PSID in msg_psids, \
            "MSG-C must be notified via send_quick_replies"

    @pytest.mark.asyncio
    async def test_tg_message_relayed_to_messenger(self):
        """Message from TG-A must arrive at MSG-C's PSID."""
        from messenger_handlers import _notify_user
        from state.match_state import match_state, UserState

        await _queue_and_match(self.env, TG_USER_A, MSG_USER_C_VID)
        await match_state.set_user_state(MSG_USER_C_VID, UserState.CHATTING)
        self.env["sent_quick_replies"].clear()
        self.env["sent_messages"].clear()

        with patch(
            "messenger_handlers.UserRepository.get_by_telegram_id",
            new_callable=AsyncMock,
            return_value=_make_user(MSG_USER_C_VID, psid=MSG_USER_C_PSID),
        ):
            await _notify_user(MSG_USER_C_VID, "💬 Hi from TG-A!")

        all_targets = (
            [m[0] for m in self.env["sent_quick_replies"]]
            + [m[0] for m in self.env["sent_messages"]]
        )
        assert MSG_USER_C_PSID in all_targets, \
            "Message from TG-A must be delivered to MSG-C's PSID"

    @pytest.mark.asyncio
    async def test_messenger_message_relayed_to_telegram(self):
        """Message from MSG-C must call tg_client.send_message for TG-A."""
        from messenger_handlers import _notify_user
        import app_state

        await _queue_and_match(self.env, TG_USER_A, MSG_USER_C_VID)
        app_state.telegram_app = self.env["tg_client"]
        self.env["tg_client"].send_message.reset_mock()

        await _notify_user(TG_USER_A, "💬 Hi from MSG-C!")

        chat_ids = [
            c.kwargs.get("chat_id") or c.args[0]
            for c in self.env["tg_client"].send_message.call_args_list
        ]
        assert TG_USER_A in chat_ids, \
            "Message from MSG-C must be delivered to TG-A via tg_client"

    @pytest.mark.asyncio
    async def test_stop_from_tg_produces_partner_msg_for_messenger(self):
        """
        MatchingHandler.handle_stop called for TG-A must include
        partner_msg targeting MSG-C's virtual_id in the response dict.
        """
        from handlers.actions.matching import MatchingHandler
        from state.match_state import match_state, UserState

        await _queue_and_match(self.env, TG_USER_A, MSG_USER_C_VID)
        await match_state.set_user_state(TG_USER_A, UserState.CHATTING)
        await match_state.set_user_state(MSG_USER_C_VID, UserState.CHATTING)

        with patch(
            "database.repositories.user_repository.UserRepository.get_by_telegram_id",
            new_callable=AsyncMock,
            side_effect=lambda vid: self.env["users"].get(vid),
        ):
            response = await MatchingHandler.handle_stop(
                self.env["tg_client"], TG_USER_A
            )

        assert response is not None
        assert "text" in response, "Caller (TG-A) must receive a summary text"
        assert "partner_msg" in response, \
            "partner_msg must be present for cross-platform relay"
        assert response["partner_msg"]["target_id"] == MSG_USER_C_VID

    @pytest.mark.asyncio
    async def test_stop_from_messenger_produces_partner_msg_for_tg(self):
        """
        MatchingHandler.handle_stop from MSG-C's perspective must
        include partner_msg targeting TG-A.
        """
        from handlers.actions.matching import MatchingHandler
        from state.match_state import match_state, UserState

        # MSG-C finds TG-A
        await _queue_and_match(self.env, MSG_USER_C_VID, TG_USER_A)
        await match_state.set_user_state(MSG_USER_C_VID, UserState.CHATTING)
        await match_state.set_user_state(TG_USER_A, UserState.CHATTING)

        with patch(
            "database.repositories.user_repository.UserRepository.get_by_telegram_id",
            new_callable=AsyncMock,
            side_effect=lambda vid: self.env["users"].get(vid),
        ):
            response = await MatchingHandler.handle_stop(
                self.env["tg_client"], MSG_USER_C_VID
            )

        assert response is not None
        assert "partner_msg" in response
        assert response["partner_msg"]["target_id"] == TG_USER_A


# ═════════════════════════════════════════════════════════════════════════════
# SCENARIO 4 — HOME-redirect regression (legacy Messenger action routing)
# Validates every fix applied to _handle_legacy_messenger_action.
# ═════════════════════════════════════════════════════════════════════════════
class TestMessengerLegacyActionRouting:

    @pytest.fixture(autouse=True)
    def _seed(self, mock_env):
        mock_env["users"].update({
            MSG_USER_C_VID: _make_user(MSG_USER_C_VID, psid=MSG_USER_C_PSID),
        })
        self.env = mock_env
        self.user = self.env["users"][MSG_USER_C_VID]

    # ── Fix A: NEXT routes to handle_next ────────────────────────────────────
    @pytest.mark.asyncio
    async def test_next_payload_reaches_handle_next(self):
        """NEXT:0:CHATTING must invoke handle_next."""
        from messenger_handlers import handle_messenger_quick_reply
        from utils.renderer import StateBoundPayload
        from state.match_state import UserState

        payload = StateBoundPayload.encode("NEXT", "0", UserState.CHATTING)
        import app_state
        app_state.engine.process_event.reset_mock()
        
        await handle_messenger_quick_reply(
            MSG_USER_C_PSID, MSG_USER_C_VID, self.user, payload
        )
        # Check that it reached the engine with the correct event type
        calls = [c.args[0]["event_type"] for c in app_state.engine.process_event.call_args_list]
        assert "NEXT_MATCH" in calls

    # ── Fix A: STOP routes to handle_stop ────────────────────────────────────
    @pytest.mark.asyncio
    async def test_stop_payload_reaches_handle_stop(self):
        """STOP:0:CHATTING must invoke handle_stop."""
        from messenger_handlers import handle_messenger_quick_reply
        from utils.renderer import StateBoundPayload
        from state.match_state import UserState

        payload = StateBoundPayload.encode("STOP", "0", UserState.CHATTING)
        import app_state
        app_state.engine.process_event.reset_mock()
        
        await handle_messenger_quick_reply(
            MSG_USER_C_PSID, MSG_USER_C_VID, self.user, payload
        )
        calls = [c.args[0]["event_type"] for c in app_state.engine.process_event.call_args_list]
        assert "END_CHAT" in calls

    # ── Fix A: CANCEL_SEARCH routes to handle_cancel_search ──────────────────
    @pytest.mark.asyncio
    async def test_cancel_search_reaches_handle_cancel(self):
        """CANCEL_SEARCH:0:SEARCHING must invoke handle_cancel."""
        from messenger_handlers import handle_messenger_quick_reply
        from utils.renderer import StateBoundPayload
        from state.match_state import UserState

        payload = StateBoundPayload.encode("CANCEL_SEARCH", "0", UserState.SEARCHING)
        import app_state
        app_state.engine.process_event.reset_mock()
        
        await handle_messenger_quick_reply(
            MSG_USER_C_PSID, MSG_USER_C_VID, self.user, payload
        )
        calls = [c.args[0]["event_type"] for c in app_state.engine.process_event.call_args_list]
        assert "STOP_SEARCH" in calls

    # ── Fix A: PREF_ANY routes to handle_search_with_pref('Any') ─────────────
    @pytest.mark.asyncio
    async def test_pref_any_reaches_search_with_pref(self):
        """SEARCH_PREF:Any:HOME must invoke handle_search_with_pref with 'Any'."""
        from messenger_handlers import handle_messenger_quick_reply
        from utils.renderer import StateBoundPayload
        from state.match_state import UserState

        payload = StateBoundPayload.encode("SEARCH_PREF", "Any", UserState.HOME)
        import app_state
        app_state.engine.process_event.reset_mock()
        
        await handle_messenger_quick_reply(
            MSG_USER_C_PSID, MSG_USER_C_VID, self.user, payload
        )
        calls = [c.args[0]["event_type"] for c in app_state.engine.process_event.call_args_list]
        assert "START_SEARCH" in calls

    # ── Fix B: Unknown action while CHATTING → chat UI, not HOME ─────────────
    @pytest.mark.asyncio
    async def test_unknown_action_while_chatting_rerenders_chat_menu(self):
        """
        An unrecognised payload while the user is CHATTING must re-render
        the chat menu — not the Home/Welcome screen.
        """
        from messenger_handlers import handle_messenger_quick_reply
        from state.match_state import match_state, UserState

        await match_state.set_user_state(MSG_USER_C_VID, UserState.CHATTING)
        self.env["sent_quick_replies"].clear()

        # Send a payload that doesn't map to an engine action
        await handle_messenger_quick_reply(
            MSG_USER_C_PSID, MSG_USER_C_VID, self.user,
            "TOTALLY_UNKNOWN:0:CHATTING"
        )

        assert self.env["sent_quick_replies"], "Must send a response"
        _, _, buttons = self.env["sent_quick_replies"][-1]
        button_payloads = str(buttons)
        # Chat menu must contain STOP or NEXT
        assert "STOP" in button_payloads or "NEXT" in button_payloads, (
            f"Expected chat-menu buttons but got: {button_payloads}"
        )

    # ── Fix B: Unknown action while SEARCHING → cancel button, not HOME ───────
    @pytest.mark.asyncio
    async def test_unknown_action_while_searching_rerenders_cancel(self):
        """
        An unrecognised payload while the user is SEARCHING must re-render
        the cancel-search prompt — not the Home/Welcome screen.
        """
        from messenger_handlers import handle_messenger_quick_reply
        from state.match_state import match_state, UserState

        await match_state.set_user_state(MSG_USER_C_VID, UserState.SEARCHING)
        self.env["sent_quick_replies"].clear()

        await handle_messenger_quick_reply(
            MSG_USER_C_PSID, MSG_USER_C_VID, self.user,
            "UNKNOWN_DURING_SEARCH:0:SEARCHING"
        )

        assert self.env["sent_quick_replies"], "Must send a response"
        _, _, buttons = self.env["sent_quick_replies"][-1]
        button_payloads = str(buttons)
        assert "CANCEL_SEARCH" in button_payloads or "Cancel" in button_payloads, (
            f"Expected cancel button but got: {button_payloads}"
        )

    # ── Fix C: cancel-search button encodes SEARCHING state ──────────────────
    @pytest.mark.asyncio
    async def test_map_reply_markup_cancel_encodes_searching_state(self):
        """
        _map_reply_markup for the active-search menu must produce
        CANCEL_SEARCH:0:SEARCHING — not CANCEL_SEARCH:0:HOME.
        This ensures the stale-state validator never rejects it during search.
        """
        from messenger_handlers import _map_reply_markup

        # Create a markup string that looks like the active-search menu
        fake_markup = MagicMock()
        fake_markup.__str__ = lambda self: "priority_packs cancel_search"

        buttons = _map_reply_markup(fake_markup)
        assert buttons is not None
        cancel_btn = next(
            (b for b in buttons if "Cancel" in b.get("title", "")), None
        )
        assert cancel_btn is not None, "Cancel button must be present"
        assert ":SEARCHING" in cancel_btn["payload"], (
            f"Cancel payload must encode SEARCHING state, got: {cancel_btn['payload']}"
        )
