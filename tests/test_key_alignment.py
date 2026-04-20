import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock
from services.distributed_state import distributed_state

@pytest.mark.asyncio
async def test_key_alignment_queue():
    """Verify that add_to_queue and get_queue_candidates use sm:queue"""
    mock_redis = AsyncMock()
    distributed_state.redis = mock_redis
    
    await distributed_state.add_to_queue(123)
    # Match: LPUSH sm:queue 123
    mock_redis.rpush.assert_called_with("sm:queue", "123")
    
    await distributed_state.get_queue_candidates()
    mock_redis.lrange.assert_called_with("sm:queue", 0, -1)

@pytest.mark.asyncio
async def test_key_alignment_claim_match():
    """Verify that atomic_claim_match passes sm: prefixed keys to Lua"""
    mock_redis = AsyncMock()
    distributed_state.redis = mock_redis
    mock_redis.eval.return_value = [1, "MATCHED"]
    
    await distributed_state.atomic_claim_match(111, 222)
    
    args = mock_redis.eval.call_args[0]
    keys = args[2:] # script, num_keys, *keys
    
    assert "sm:state:111" in args
    assert "sm:state:222" in args
    assert "sm:partner:111" in args
    assert "sm:partner:222" in args
    assert "sm:queue" in args

@pytest.mark.asyncio
async def test_key_alignment_partner_methods():
    """Verify set/get/clear partner use sm:partner:"""
    mock_redis = AsyncMock()
    distributed_state.redis = mock_redis
    
    await distributed_state.get_partner(111)
    mock_redis.get.assert_any_call("sm:partner:111")
    
    await distributed_state.set_partner(111, 222)
    mock_redis.set.assert_any_call("sm:partner:111", "222")
    mock_redis.set.assert_any_call("sm:partner:222", "111")
