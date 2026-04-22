import pytest
from utils.content_filter import (
    normalize_text, check_message, apply_enforcement,
    SEVERITY_WARN, SEVERITY_BLOCK, SEVERITY_AUTO_BAN
)
from unittest.mock import MagicMock, patch, AsyncMock

def test_normalize_text():
    assert normalize_text("Hey   there!") == "hey there!"
    # Zero width space \u200b
    assert normalize_text("k\u200by\u200bs") == "kys"
    assert normalize_text("K Y S") == "k y s"
    assert normalize_text("K.Y.S.") == "k.y.s."
    assert normalize_text("  SPACES  ") == "spaces"

def test_check_message_safe():
    is_safe, violation = check_message("Hello, how are you today?")
    assert is_safe
    assert violation is None

def test_check_message_fast_path():
    # Only simple text, no suspicious symbols should be very fast and safe
    is_safe, violation = check_message("Normal conversation without links or numbers")
    assert is_safe
    assert violation is None

def test_check_message_csam():
    is_safe, violation = check_message("child porn")
    assert not is_safe
    assert violation["severity"] == SEVERITY_AUTO_BAN
    assert violation["category"] == "csam"

def test_check_message_link_bypass():
    # t.me/joinchat is SEVERITY_BLOCK
    is_safe, violation = check_message("t.m\u200be/join\u200bchat")
    assert not is_safe
    assert violation["category"] == "telegram_spam"
    assert violation["severity"] == SEVERITY_BLOCK

def test_check_message_multi_scan_priority():
    # Link (BLOCK) + CSAM (AUTO_BAN)
    is_safe, violation = check_message("visit google.com and child porn")
    assert not is_safe
    assert violation["severity"] == SEVERITY_AUTO_BAN
    assert violation["category"] == "csam"

@pytest.mark.asyncio
async def test_apply_enforcement_escalation():
    user_id = 999
    violation = {
        "severity": SEVERITY_WARN,
        "category": "contact_sharing",
        "description": "Phone number sharing",
        "matched_text": "12345678"
    }
    
    # Path to track after refactor
    with patch("core.behavior_engine.behavior_engine.get_signals", new_callable=AsyncMock) as mock_get, \
         patch("core.behavior_engine.behavior_engine.record_violation", new_callable=AsyncMock) as mock_record:
        
        # Scenario: First violation (no escalation)
        mock_signals = MagicMock()
        mock_signals.violation_count = 0
        mock_get.return_value = mock_signals
        
        decision = await apply_enforcement(user_id, violation)
        assert decision["final_severity"] == SEVERITY_WARN
        assert decision["penalty"] == 10
        
        # Scenario: 3 violations -> WARN becomes BLOCK
        mock_signals.violation_count = 3
        decision = await apply_enforcement(user_id, violation)
        assert decision["final_severity"] == SEVERITY_BLOCK
        assert decision["action"] == "terminate_chat"
        assert decision["penalty"] == 25
        
        # Scenario: 5 violations -> BLOCK becomes AUTO_BAN
        mock_signals.violation_count = 5
        violation["severity"] = SEVERITY_BLOCK
        decision = await apply_enforcement(user_id, violation)
        assert decision["final_severity"] == SEVERITY_AUTO_BAN
        assert decision["action"] == "auto_ban_user"
        assert decision["penalty"] == 100

@pytest.mark.asyncio
async def test_apply_enforcement_overrides():
    user_id = 888
    # "self_harm" category should automatically set severity to BLOCK
    violation = {
        "severity": SEVERITY_WARN,
        "category": "self_harm",
        "description": "Self-harm",
        "matched_text": "kys"
    }
    
    with patch("core.behavior_engine.behavior_engine.get_signals", new_callable=AsyncMock) as mock_get, \
         patch("core.behavior_engine.behavior_engine.record_violation", new_callable=AsyncMock) as mock_record:
        
        mock_signals = MagicMock()
        mock_signals.violation_count = 0
        mock_get.return_value = mock_signals
        
        decision = await apply_enforcement(user_id, violation)
        assert decision["final_severity"] == SEVERITY_BLOCK
        assert decision["action"] == "terminate_chat"
        
        # "csam" always AUTO_BAN
        violation["category"] = "csam"
        decision = await apply_enforcement(user_id, violation)
        assert decision["final_severity"] == SEVERITY_AUTO_BAN
        assert decision["action"] == "auto_ban_user"

def test_check_message_short_numbers_allowed():
    # Only 7+ digits should trigger
    is_safe, violation = check_message("I am 25 years old")
    assert is_safe
    
    is_safe, violation = check_message("Call me at 12345678")
    assert not is_safe
    assert violation["category"] == "contact_sharing"
