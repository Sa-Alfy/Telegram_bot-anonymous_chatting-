import pytest
import os
import hmac
import hashlib
from unittest.mock import patch, MagicMock, AsyncMock

# ═══════════════════════════════════════════════════════
# 1. Content Filter Remediation Tests
# ═══════════════════════════════════════════════════════
def test_content_filter_cp_false_positive_removed():
    from utils.content_filter import check_message
    
    # "cp" should now be safe (false positive removed)
    is_safe, violation = check_message("cp /path/to/file")
    assert is_safe is True
    assert violation is None
    
    is_safe, violation = check_message("I am at the checkpoint")
    assert is_safe is True
    
    # Critical CSAM should still be blocked (sanity check)
    is_safe, violation = check_message("child porn is bad")
    assert is_safe is False
    assert violation["severity"] == "auto_ban"

# ═══════════════════════════════════════════════════════
# 2. Webhook Signature Remediation Tests
# ═══════════════════════════════════════════════════════
class TestWebhookSecurity:
    @pytest.fixture
    def app(self):
        from webhook_server import app
        app.config['TESTING'] = True
        return app.test_client()

    def test_webhook_unauthorized_mismatch_returns_403(self, app):
        with patch.dict(os.environ, {"APP_SECRET": "top_secret", "FLASK_ENV": "production"}):
            payload = b'{"object":"page"}'
            headers = {"X-Hub-Signature-256": "sha256=wrong_hash"}
            
            # In production mode with APP_SECRET set, signature mismatch MUST return 403
            import config
            config.MESSENGER_ENABLED = True
            
            response = app.post('/messenger-webhook', data=payload, headers=headers)
            assert response.status_code == 403
            assert b"Forbidden" in response.data

    def test_webhook_dev_mode_mismatch_allows_bypass(self, app):
        with patch.dict(os.environ, {"APP_SECRET": "top_secret", "FLASK_ENV": "development"}):
            payload = b'{"object":"page"}'
            headers = {"X-Hub-Signature-256": "sha256=wrong_hash"}
            
            # In development mode, mismatch logs warning but continues (returns 200)
            import config
            config.MESSENGER_ENABLED = True
            
            with patch('messenger.dispatcher._process_messaging_event', new_callable=AsyncMock) as mock_proc:
                response = app.post('/messenger-webhook', data=payload, headers=headers)
                assert response.status_code == 200

    def test_webhook_authorized_success(self, app):
        secret = "top_secret"
        payload = b'{"object":"page","entry":[]}'
        expected_sig = "sha256=" + hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
        
        with patch.dict(os.environ, {"APP_SECRET": secret, "FLASK_ENV": "production"}):
            headers = {"X-Hub-Signature-256": expected_sig}
            import config
            config.MESSENGER_ENABLED = True
            
            response = app.post('/messenger-webhook', data=payload, headers=headers)
            assert response.status_code == 200

# ═══════════════════════════════════════════════════════
# 3. XSS Protection Remediation Tests
# ═══════════════════════════════════════════════════════
def test_deletion_status_xss_protection():
    from webhook_server import app
    client = app.test_client()
    
    # 1. Test XSS payload
    xss_payload = "<script>alert('xss')</script>"
    response = client.get(f'/deletion-status?code={xss_payload}')
    
    # "Invalid" because it fails regex ^[a-f0-9]{1,16}$
    assert b"Invalid" in response.data
    assert b"<script>" not in response.data
    
    # 2. Test valid code
    valid_code = "a1b2c3d4e5f6"
    response = client.get(f'/deletion-status?code={valid_code}')
    assert response.status_code == 200
    assert valid_code.encode() in response.data

# ═══════════════════════════════════════════════════════
# 4. Config Loopshole Remediation Tests
# ═══════════════════════════════════════════════════════
def test_messenger_disabled_if_insecure_token():
    import os
    from importlib import reload
    import config
    
    # Mock environment to simulate missing VERIFY_TOKEN
    with patch.dict(os.environ, {"VERIFY_TOKEN": ""}):
        reload(config)
        # Should be false because VERIFY_TOKEN is empty
        assert config.MESSENGER_ENABLED is False
