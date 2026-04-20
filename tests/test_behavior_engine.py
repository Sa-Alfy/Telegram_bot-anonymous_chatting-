import pytest
import time
from core.signal_collector import UserSignals, SignalCollector
from core.classifier import BehaviorClassifier, BehaviorProfile
from core.adaptation import SystemAdaptation

def test_fast_skipper_classification():
    signals = UserSignals()
    signals.session_count = 5
    signals.rapid_skips = 3
    
    profiles = BehaviorClassifier.classify(signals)
    assert BehaviorProfile.FAST_SKIPPER in profiles

def test_toxic_user_classification():
    signals = UserSignals()
    signals.reports_received = 3
    
    profiles = BehaviorClassifier.classify(signals)
    assert BehaviorProfile.TOXIC_USER in profiles

def test_high_value_user_classification():
    signals = UserSignals()
    signals.good_sessions = 6
    signals.reports_received = 0
    
    # 500 XP required for high volume
    profiles = BehaviorClassifier.classify(signals, xp=600)
    assert BehaviorProfile.HIGH_VALUE_USER in profiles
    
def test_new_user_classification():
    signals = UserSignals()
    signals.session_count = 1
    signals.messages_sent = 5
    
    profiles = BehaviorClassifier.classify(signals)
    assert BehaviorProfile.NEW_USER in profiles

def test_adaptation_match_score():
    # Toxic User
    signals = UserSignals()
    profiles = [BehaviorProfile.TOXIC_USER]
    # base(40) + xp(2) + beh(8) = 50.0
    score = SystemAdaptation.get_match_score(profiles, signals, base_reputation=100, xp=100)
    assert score == 50.0  
    
    # High-Value User
    hv_score = SystemAdaptation.get_match_score([BehaviorProfile.HIGH_VALUE_USER], signals, base_reputation=100, xp=1000)
    assert hv_score > score

def test_adaptation_cooldown():
    profiles = [BehaviorProfile.FAST_SKIPPER]
    cooldown = SystemAdaptation.get_next_cooldown(profiles, rapid_skips=4)
    # base 3.0 + (4 - 2) * 2.0 = 7.0
    assert cooldown == 7.0
    
    normal_cooldown = SystemAdaptation.get_next_cooldown([BehaviorProfile.NORMAL], rapid_skips=0)
    assert normal_cooldown == 3.0

@pytest.mark.asyncio
async def test_signal_collector_integration():
    collector = SignalCollector()
    user_id = 999
    
    await collector.record_session_start(user_id)
    s = await collector.get_signals(user_id)
    assert s.session_count == 1
    
    # Send a message
    await collector.record_message_sent(user_id, text="Hello world, this is a test message.")
    s = await collector.get_signals(user_id) # Refresh
    assert s.messages_sent == 1
    assert s.current_session_messages == 1
    
    # Disconnect
    await collector.record_disconnect(user_id)
    s = await collector.get_signals(user_id) # Refresh
    assert s.current_session_messages == 0 # Reset on end session

@pytest.mark.asyncio
async def test_anti_spam_decay():
    collector = SignalCollector()
    user_id = 888
    
    # Trigger copy-paste streak
    text = "This is a very long message that I am copying and pasting multiple times."
    await collector.record_session_start(user_id)
    await collector.record_message_sent(user_id, text=text)
    await collector.record_message_sent(user_id, text=text) # Streak 1
    
    s = await collector.get_signals(user_id)
    assert s.copy_paste_streak == 1
    
    # Complete a good session to decay
    for _ in range(5):
        await collector.record_message_sent(user_id, text=f"Unique message {_}")
    
    await collector.record_disconnect(user_id)
    s = await collector.get_signals(user_id)
    assert s.copy_paste_streak == 0 # Decayed
