# core/engine/redis_scripts.py

import time
from typing import Tuple, List, Optional
from utils.logger import logger

class RedisScripts:
    """Lua script library for atomic Unified Matchmaking state transitions.
    PRODUCTION HARDENED: Match-level versioning, atomic audit logs, and vote locks.
    """

    # 0. SET PREFERENCES (Transition from HOME)
    # KEYS: 1:state:user, 2:idemp:hash, 3:user_ver:id
    # ARGV: 1:user_id, 2:timestamp
    SET_PREFS_LUA = """
        local state_key = KEYS[1]
        local idemp_key = KEYS[2]
        local ver_key = KEYS[3]

        -- 1. Idempotency Check
        if redis.call("EXISTS", idemp_key) == 1 then return {2, "ALREADY_PROCESSED"} end

        -- 2. State Validation
        local current = redis.call("GET", state_key)
        if current and current ~= "HOME" and current ~= "VOTING" and current ~= "SEARCHING" then return {0, "INVALID_STATE", current} end

        -- 3. Execution
        redis.call("SET", state_key, "PREFERENCES")
        redis.call("SET", idemp_key, "1", "EX", 30)

        -- Increment User Version
        local ver = redis.call("INCR", ver_key)

        return {1, "PREFERENCES", tostring(ver)}
    """

    # 1. START SEARCH
    # KEYS: 1:state:user, 2:queue, 3:idemp:hash, 4:user_ver:id, 5:match_pref:user
    # ARGV: 1:user_id, 2:timestamp, 3:preference, 4:priority ("1" or "0")
    START_SEARCH_LUA = """
        local state_key = KEYS[1]
        local queue_key = KEYS[2]
        local idemp_key = KEYS[3]
        local ver_key = KEYS[4]
        local pref_key = KEYS[5]
        
        -- 1. Idempotency Check
        if redis.call("EXISTS", idemp_key) == 1 then return {2, "ALREADY_PROCESSED"} end

        -- 2. State Validation
        local current = redis.call("GET", state_key)
        if current and current ~= "HOME" and current ~= "PREFERENCES" and current ~= "SEARCHING" and current ~= "VOTING" then 
            return {0, "INVALID_STATE", current or "NULL"} 
        end

        -- 3. Execution
        redis.call("SET", state_key, "SEARCHING")
        
        -- Store preference if provided
        if ARGV[3] and ARGV[3] ~= "" then
            redis.call("HSET", pref_key, "pref", ARGV[3])
            redis.call("EXPIRE", pref_key, 3600)
        end
        
        redis.call("LREM", queue_key, 0, ARGV[1])
        if ARGV[4] == "1" then
            redis.call("LPUSH", queue_key, ARGV[1])
        else
            redis.call("RPUSH", queue_key, ARGV[1])
        end
        redis.call("SET", idemp_key, "1", "EX", 30)
        
        -- Increment User Version
        local ver = redis.call("INCR", ver_key)
        
        return {1, "SEARCHING", tostring(ver)}
    """

    # 2. CLAIM MATCH (System Triggered)
    # KEYS: 1:state:uA, 2:state:uB, 3:partner:uA, 4:partner:uB, 5:queue
    # ARGV: 1:uA_id, 2:uB_id, 3:now
    CLAIM_MATCH_LUA = """
        if redis.call("GET", KEYS[1]) ~= "SEARCHING" then return {0, "A_NOT_SEARCHING"} end
        if redis.call("GET", KEYS[2]) ~= "SEARCHING" then return {0, "B_NOT_SEARCHING"} end

        redis.call("LREM", KEYS[5], 0, ARGV[1])
        redis.call("LREM", KEYS[5], 0, ARGV[2])

        redis.call("SET", KEYS[1], "MATCHED")
        redis.call("SET", KEYS[2], "MATCHED")
        redis.call("SET", KEYS[3], ARGV[2])
        redis.call("SET", KEYS[4], ARGV[1])

        return {1, "MATCHED"}
    """

    # 3. CONNECT / SESSION START
    # KEYS: 1:state:uA, 2:state:uB, 3:match:id, 4:match_ver:id, 5:event_log:id, 6:audit_log:id
    # ARGV: 1:match_id, 2:uA_id, 3:uB_id, 4:now
    CONNECT_LUA = """
        redis.call("SET", KEYS[1], "CHAT_ACTIVE")
        redis.call("SET", KEYS[2], "CHAT_ACTIVE")
        
        -- Initialize match & version
        local match_data = "id:" .. ARGV[1] .. "|start:" .. ARGV[4] .. "|uA:" .. ARGV[2] .. "|uB:" .. ARGV[3]
        redis.call("SET", KEYS[3], match_data, "EX", 86400)
        local ver = redis.call("INCR", KEYS[4])
        redis.call("EXPIRE", KEYS[4], 86400)
        
        -- BUNDLED LOGGING
        redis.call("RPUSH", KEYS[5], ARGV[4] .. ":SESSION_START")
        redis.call("LTRIM", KEYS[5], -100, -1)
        redis.call("EXPIRE", KEYS[5], 86400)
        
        redis.call("RPUSH", KEYS[6], ARGV[4] .. ":MATCH_CREATED:" .. ARGV[1])
        redis.call("EXPIRE", KEYS[6], 86400)

        return {1, "CHAT_ACTIVE", tostring(ver)}
    """

    # 4. END CHAT (Atomic Symmetrical Disconnect)
    # KEYS: 1:state:uA, 2:state:uB, 3:partner:uA, 4:partner:uB, 5:match_ver:id, 6:event_log:id, 7:audit_log:id, 8:idemp:hash
    # ARGV: 1:uA_id, 2:uB_id, 3:match_id, 4:now
    END_CHAT_LUA = """
        if redis.call("EXISTS", KEYS[8]) == 1 then return {2, "ALREADY_ENDED"} end

        redis.call("SET", KEYS[1], "HOME")
        redis.call("SET", KEYS[2], "HOME")
        redis.call("DEL", KEYS[3])
        redis.call("DEL", KEYS[4])

        local ver = redis.call("INCR", KEYS[5])
        
        -- BUNDLED LOGGING
        redis.call("RPUSH", KEYS[6], ARGV[4] .. ":END_CHAT:by:" .. ARGV[1])
        redis.call("LTRIM", KEYS[6], -100, -1)
        redis.call("RPUSH", KEYS[7], ARGV[4] .. ":SESSION_END:" .. ARGV[3] .. ":ver:" .. ver)

        redis.call("SET", KEYS[8], "1", "EX", 30)
        return {1, "HOME", tostring(ver)}
    """

    # 4.5 SKIP VOTE (The Safety Exit)
    # KEYS: 1:state:user, 2:match_ver:id, 3:audit_log:id, 4:idemp:hash
    # ARGV: 1:user_id, 2:match_id, 3:now
    SKIP_VOTE_LUA = """
        if redis.call("EXISTS", KEYS[4]) == 1 then return {2, "ALREADY_PROCESSED"} end
        -- Optional: skip state check to allow voting from HOME
        -- if redis.call("GET", KEYS[1]) ~= "VOTING" then return {0, "NOT_IN_VOTING"} end

        redis.call("SET", KEYS[1], "HOME")
        local ver = redis.call("INCR", KEYS[2])
        redis.call("RPUSH", KEYS[3], ARGV[3] .. ":SKIP_VOTE_SUBMITTED:by:" .. ARGV[1])

        redis.call("SET", KEYS[4], "1", "EX", 30)
        return {1, "HOME", tostring(ver)}
    """

    # 5. SUBMIT VOTE (The Gatekeeper)
    # KEYS: 1:state:user, 2:vote:record, 3:vote_lock:id, 4:match_ver:id, 5:audit_log:id, 6:idemp:hash
    # ARGV: 1:user_id, 2:match_id, 3:vote_type, 4:vote_value, 5:now
    SUBMIT_VOTE_LUA = """
        if redis.call("EXISTS", KEYS[6]) == 1 then return {2, "ALREADY_SUBMITTED"} end
        -- if redis.call("GET", KEYS[1]) ~= "VOTING" then return {0, "NOT_IN_VOTING"} end

        -- ACQUIRE VOTE LOCK (Issue 2)
        if not redis.call("SET", KEYS[3], "1", "NX", "EX", 5) then return {0, "LOCKED"} end

        redis.call("HSET", KEYS[2], ARGV[3], ARGV[4])
        redis.call("EXPIRE", KEYS[2], 86400)

        local ver = redis.call("INCR", KEYS[4])
        redis.call("RPUSH", KEYS[5], ARGV[5] .. ":VOTE_SUBMITTED:" .. ARGV[3] .. ":by:" .. ARGV[1])

        local res = {1, "VOTE_RECORDED", tostring(ver)}
        local rep = redis.call("HGET", KEYS[2], "reputation")
        local iden = redis.call("HGET", KEYS[2], "identity")

        if rep and iden then
            redis.call("SET", KEYS[1], "HOME")
            res = {1, "VOTING_COMPLETE", tostring(ver)}
        end

        redis.call("DEL", KEYS[3]) -- Release lock
        redis.call("SET", KEYS[6], "1", "EX", 30)
        return res
    """

    # 6. TIMEOUT VOTING (System Triggered)
    # KEYS: 1:state:user, 2:vote:record, 3:vote_lock:id, 4:match_ver:id, 5:audit_log:id
    # ARGV: 1:user_id, 2:match_id, 3:now
    TIMEOUT_VOTING_LUA = """
        if redis.call("GET", KEYS[1]) ~= "VOTING" then return {0, "NOT_IN_VOTING"} end
        
        -- ACQUIRE VOTE LOCK (Prevent race with manual vote)
        if not redis.call("SET", KEYS[3], "1", "NX", "EX", 5) then return {0, "LOCKED"} end

        -- Re-verify signals under lock
        local rep = redis.call("HGET", KEYS[2], "reputation")
        local iden = redis.call("HGET", KEYS[2], "identity")
        if rep and iden then 
            redis.call("DEL", KEYS[3])
            return {0, "VOTE_WAS_COMPLETE"} 
        end

        redis.call("SET", KEYS[1], "HOME")
        local ver = redis.call("INCR", KEYS[4])
        redis.call("RPUSH", KEYS[5], ARGV[3] .. ":TIMEOUT_VOTING:" .. ARGV[1])
        
        redis.call("DEL", KEYS[3])
        return {1, "TIMEOUT_CLEANUP", tostring(ver)}
    """
    
    # 7. STOP SEARCH (Manual Cancel)
    # KEYS: 1:state:user, 2:queue, 3:match_pref:user, 4:user_ver:id
    # ARGV: 1:user_id, 2:now
    STOP_SEARCH_LUA = """
        local state_key = KEYS[1]
        local queue_key = KEYS[2]
        
        -- Remove from queue
        redis.call("LREM", queue_key, 0, ARGV[1])
        
        -- Cleanup preference
        redis.call("DEL", KEYS[3])
        
        -- Reset state
        redis.call("SET", state_key, "HOME")
        
        -- Increment User Version
        local ver = redis.call("INCR", KEYS[4])
        
        return {1, "HOME", tostring(ver)}
    """

    # 8. GENERIC SET STATE (Engine-Aware Transition)
    # KEYS: 1:state:user, 2:idemp:hash, 3:user_ver:id
    # ARGV: 1:user_id, 2:timestamp, 3:new_state
    SET_STATE_LUA = """
        local state_key = KEYS[1]
        local idemp_key = KEYS[2]
        local ver_key = KEYS[3]

        -- 1. Idempotency Check
        if redis.call("EXISTS", idemp_key) == 1 then return {2, "ALREADY_PROCESSED"} end

        -- 2. Execution
        redis.call("SET", state_key, ARGV[3])
        redis.call("SET", idemp_key, "1", "EX", 30)

        -- Increment User Version
        local ver = redis.call("INCR", ver_key)

        return {1, ARGV[3], tostring(ver)}
    """

    @staticmethod
    async def execute(redis, script: str, keys: List[str], args: List[str]) -> Tuple[int, str, Optional[str]]:
        try:
            res = await redis.eval(script, len(keys), *keys, *args)
            return int(res[0]), res[1], (res[2] if len(res) > 2 else None)
        except Exception as e:
            logger.error(f"Lua execution failed: {e}")
            return -1, str(e), None
