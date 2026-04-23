"""
Tests for Messenger specific logic.
Covers webhook_server and messenger_handlers.
"""
import pytest
import time
from unittest.mock import AsyncMock, patch, MagicMock

# ═══════════════════════════════════════════════════════
# 1. Webhook Server Tests
# ═══════════════════════════════════════════════════════
class TestWebhookServer:
    @pytest.fixture
    def app(self):
        from webhook_server import app
        import os
        # Reconfigure Flask app for testing
        app.config['TESTING'] = True
        os.environ["FLASK_ENV"] = "development"
        return app.test_client()

    def test_health_check(self, app):
        response = app.get('/health')
        assert response.status_code == 200
        assert b"status" in response.data
        assert b"bot_loop" in response.data

    def test_webhook_verification_success(self, app):
        import config
        config.VERIFY_TOKEN = "secret_test_token"
        config.MESSENGER_ENABLED = True
        with patch("webhook_server.handle_messenger_webhook_get", return_value=("1234", 200)):
            response = app.get('/messenger-webhook?hub.verify_token=secret_test_token&hub.challenge=1234')
            assert response.status_code == 200
            assert b"1234" in response.data

    def test_webhook_verification_failure(self, app):
        import config
        config.VERIFY_TOKEN = "secret_test_token"
        config.MESSENGER_ENABLED = True
        with patch("webhook_server.handle_messenger_webhook_get", return_value=("Forbidden", 403)):
            response = app.get('/messenger-webhook?hub.verify_token=wrong_token&hub.challenge=1234')
            assert response.status_code == 403

    def test_webhook_post_empty_body(self, app):
        response = app.post('/webhook', json={})
        assert response.status_code == 404

    @patch('messenger_handlers.asyncio.run_coroutine_threadsafe')
    def test_webhook_post_schedules_background_task(self, mock_schedule, app):
        import app_state
        app_state.bot_loop = MagicMock()
        app_state.bot_loop.is_running.return_value = True
        
        payload = {
            "object": "page",
            "entry": [{"messaging": [{"sender": {"id": "123"}}]}]
        }
        import config
        config.MESSENGER_ENABLED = True
        
        # Test the messenger-webhook endpoint
        response = app.post('/messenger-webhook', json=payload)
        assert response.status_code == 200
        assert mock_schedule.called


class TestMessengerApi:
    """Test the Send API wrappers in messenger_api.py."""
    
    @patch('messenger_api.messenger_session.post')
    def test_send_generic_template(self, mock_post):
        from messenger_api import send_generic_template
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {"result": "ok"}
        
        elements = [{"title": "Test Card", "image_url": "http://test.com"}]
        result = send_generic_template("PSID123", elements)
        
        assert result["result"] == "ok"
        # Check payload structure
        payload = mock_post.call_args[1]["json"]
        assert payload["message"]["attachment"]["payload"]["template_type"] == "generic"
        assert payload["message"]["attachment"]["payload"]["elements"][0]["title"] == "Test Card"

    @patch('messenger_api.messenger_session.post')
    def test_set_messenger_profile(self, mock_post):
        from messenger_api import set_messenger_profile
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {"result": "success"}
        
        payload = {"get_started": {"payload": "START"}}
        result = set_messenger_profile(payload)
        
        assert result["result"] == "success"
        assert "messenger_profile" in mock_post.call_args[0][0]

# ═══════════════════════════════════════════════════════
# 2. Messenger Handlers Tests
# ═══════════════════════════════════════════════════════
class TestMessengerHandlers:
    @pytest.fixture(autouse=True)
    def setup_mocks(self):
        with patch('messenger_handlers.send_message') as self.mock_send_msg, \
             patch('messenger_handlers.send_quick_replies') as self.mock_send_qr, \
             patch('messenger_handlers.send_generic_template') as self.mock_send_carousel, \
             patch('app_state.msg_adapter', new_callable=AsyncMock) as self.mock_adapter, \
             patch('app_state.engine', new_callable=AsyncMock) as self.mock_engine:
            yield

    @pytest.mark.asyncio
    async def test_map_reply_markup_start_menu(self):
        from messenger_handlers import _map_reply_markup
        from adapters.telegram.keyboards import start_menu
        markup = start_menu(is_guest=False)
        qr = _map_reply_markup(markup)
        assert qr is not None
        assert "Find Partner" in str(qr)

    @pytest.mark.asyncio
    async def test_map_reply_markup_null(self):
        from messenger_handlers import _map_reply_markup
        assert _map_reply_markup(None) is None


    @pytest.mark.asyncio
    async def test_execute_action_routes_correctly(self):
        from messenger_handlers import _execute_action
        import app_state
        app_state.telegram_app = MagicMock()
        
        async def dummy_action(client, virtual_id):
            return {"text": "dummy response", "reply_markup": None}
            
        await _execute_action("PSID_TEST", 1000, dummy_action)
        self.mock_send_msg.assert_called_with("PSID_TEST", "dummy response")

    @pytest.mark.asyncio
    async def test_handle_start_shows_hero_carousel(self):
        from messenger_handlers import _handle_start
        await _handle_start("PSID123", 1000, {"coins": 100})
        self.mock_send_carousel.assert_called_once()
        args = self.mock_send_carousel.call_args[0]
        assert "Neonymo" in args[1][0]["title"]

    @pytest.mark.asyncio
    async def test_handle_postback_routing(self):
        from messenger_handlers import handle_messenger_postback
        user = {"telegram_id": 1000, "coins": 50, "consent_given_at": 123456789}
        
        self.mock_adapter.translate_event.return_value = {"event_type": "SHOW_STATS", "user_id": "msg_PSID123"}
        self.mock_engine.process_event.return_value = {"success": True}
        
        await handle_messenger_postback("PSID123", 1000, user, "STATS")
        self.mock_engine.process_event.assert_called()
        # Verify event type
        call_args = self.mock_engine.process_event.call_args[0][0]
        assert call_args["event_type"] == "SHOW_STATS"

    @pytest.mark.asyncio
    async def test_process_messaging_event_duplicate_mid(self):
        from messenger.dispatcher import _process_messaging_event
        from messenger.dispatcher import distributed_state
        with patch.object(distributed_state, 'is_duplicate_message', new_callable=AsyncMock) as mock_dup:
            mock_dup.return_value = True
            event = {"sender": {"id": "123"}, "message": {"mid": "mid_1"}}
            await _process_messaging_event(event)
            # Should return early without calling other handlers

    @pytest.mark.asyncio
    async def test_process_messaging_event_postback_deduplication(self):
        from messenger.dispatcher import _process_messaging_event
        from messenger.dispatcher import distributed_state
        user = {"telegram_id": 1000, "consent_given_at": time.time()}
        with patch('messenger.dispatcher._get_or_create_messenger_user', return_value=(user, 1000)), \
             patch.object(distributed_state, 'is_duplicate_interaction', new_callable=AsyncMock) as mock_dup, \
             patch('messenger_handlers.handle_messenger_postback', new_callable=AsyncMock) as mock_handle:
            mock_dup.return_value = True
            event = {"sender": {"id": "PSID1"}, "postback": {"payload": "CLICK"}}
            await _process_messaging_event(event)
            mock_handle.assert_not_called()

