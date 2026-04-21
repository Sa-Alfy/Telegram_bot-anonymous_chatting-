# core/engine/actions.py

import time
import hashlib
from typing import Dict, Any, Optional
from utils.logger import logger
from core.engine.state_machine import UnifiedState
from core.engine.redis_scripts import RedisScripts
from services.distributed_state import distributed_state

class ActionRouter:
    """Idempotent Event Router for the Unified Matchmaking system.
    PRODUCTION HARDENED: Sequencing, Atomic Timeouts, and Render-ACK flow.
    """

    @staticmethod
    def generate_idemp_key(user_id: str, event_type: str, match_id: Optional[str], timestamp: int) -> str:
        raw = f"{user_id}:{event_type}:{match_id or 'none'}:{timestamp}"
        h = hashlib.md5(raw.encode()).hexdigest()
        return f"sm:idemp:{h}"

    @classmethod
    async def process_event(cls, event: Dict[str, Any]) -> Dict[str, Any]:
        etype = event.get("event_type")
        uid = str(event.get("user_id"))
        mid = event.get("match_id", "global")
        ts = event.get("timestamp", int(time.time()))
        payload = event.get("payload", {})

        idemp_key = cls.generate_idemp_key(uid, etype, mid, ts)
        redis = distributed_state.redis

        if not redis:
            return {"success": False, "error": "Redis not connected"}

        logger.info(f"Processing Event: {etype} for User:{uid} (Match:{mid})")

        result = {"success": False}
        
        # --- 1. TRANSITIONS ---
        if etype == "SHOW_PREFS":
            keys = [f"sm:state:{uid}", idemp_key, f"sm:ver:u:{uid}"]
            code, msg, ver = await RedisScripts.execute(redis, RedisScripts.SET_PREFS_LUA, keys, [uid, str(ts)])
            result = {"success": code in {1, 2}, "state": msg, "version": ver}

        elif etype == "START_SEARCH":
            pref = payload.get("pref", "")
            keys = [f"sm:state:{uid}", "sm:queue", idemp_key, f"sm:ver:u:{uid}", f"sm:match:pref:{uid}"]
            code, msg, ver = await RedisScripts.execute(redis, RedisScripts.START_SEARCH_LUA, keys, [uid, str(ts), pref])
            result = {"success": code in {1, 2}, "state": msg, "version": ver}

        elif etype in {"STOP_SEARCH", "CANCEL_SEARCH"}:
            keys = [f"sm:state:{uid}", "sm:queue", f"sm:match:pref:{uid}", f"sm:ver:u:{uid}"]
            code, msg, ver = await RedisScripts.execute(redis, RedisScripts.STOP_SEARCH_LUA, keys, [uid, str(ts)])
            result = {"success": code == 1, "state": msg, "version": ver}

        elif etype == "CONNECT":
            partner_id = await distributed_state.get_partner(uid)
            if not partner_id: return {"success": False, "error": "No partner found"}
            p_uid = str(partner_id)
            u1, u2 = sorted([uid, p_uid])
            match_id = f"m_{u1}_{u2}"
            
            keys = [
                f"sm:state:{uid}", f"sm:state:{p_uid}",
                f"sm:match:{match_id}", f"sm:ver:m:{match_id}",
                f"sm:event_log:{match_id}", f"sm:audit_log:{match_id}"
            ]
            code, msg, ver = await RedisScripts.execute(redis, RedisScripts.CONNECT_LUA, keys, [match_id, uid, p_uid, str(ts)])
            result = {
                "success": code in {1, 2}, "state": msg, "version": ver,
                "notify_partner": {"user_id": p_uid, "state": UnifiedState.CHAT_ACTIVE, "match_id": match_id}
            }

        elif etype == "END_CHAT":
            from services.matchmaking import MatchmakingService
            stats = await MatchmakingService.disconnect(int(uid))
            if not stats: return {"success": False, "error": "No active session"}
            
            p_uid = str(stats["partner_id"])
            result = {
                "success": True, 
                "state": UnifiedState.VOTING,
                "version": "1", # MatchmakingService.disconnect handles versioning via atomic_disconnect
                "payload": stats,
                "notify_partner": {
                    "user_id": p_uid, 
                    "state": UnifiedState.VOTING, 
                    "match_id": mid,
                    "payload": stats
                }
            }

        elif etype == "SUBMIT_VOTE":
            vtype = payload.get("type")
            vval = payload.get("value")
            keys = [
                f"sm:state:{uid}", f"sm:vote:{mid}:{uid}", f"sm:lock:vote:{mid}",
                f"sm:ver:m:{mid}", f"sm:audit_log:{mid}", idemp_key
            ]
            code, msg, ver = await RedisScripts.execute(redis, RedisScripts.SUBMIT_VOTE_LUA, keys, [uid, mid, vtype, str(vval), str(ts)])
            signals = await redis.hgetall(f"sm:vote:{mid}:{uid}")
            result = {"success": code == 1, "state": msg, "version": ver, "signals": signals}
            
            # --- PERSISTENCE BRIDGE: Sync engine vote to Supabase ---
            if result["success"] and mid.startswith("m_"):
                try:
                    # Extract partner_id from mid (format: m_user1_user2)
                    parts = mid.split("_")
                    u1, u2 = parts[1], parts[2]
                    p_uid = u2 if uid.endswith(u1) else u1 # Robust check handles 'msg_' prefix mismatch
                    
                    from database.repositories.vote_repository import VoteRepository
                    # Map engine signals to DB format
                    db_vote_type = vval if vtype == "reputation" else None # 'like'/'dislike'
                    db_gender_vote = vval if vtype == "identity" else None # 'male'/'female'
                    
                    if vval == "good": db_vote_type = "like"
                    elif vval == "bad": db_vote_type = "dislike"
                    
                    # Clean PSID for DB int4/int8 compatibility
                    c_uid = int(uid[4:]) if uid.startswith("msg_") else int(uid)
                    c_pid = int(p_uid[4:]) if p_uid.startswith("msg_") else int(p_uid)
                    
                    await VoteRepository.submit_vote(voter_id=c_uid, voted_id=c_pid, 
                                                   vote_type=db_vote_type, gender_vote=db_gender_vote)
                except Exception as e:
                    logger.error(f"Persistence Bridge failed for VOTE: {e}")

        elif etype == "TIMEOUT_VOTING":
            keys = [
                f"sm:state:{uid}", f"sm:vote:{mid}:{uid}", f"sm:lock:vote:{mid}",
                f"sm:ver:m:{mid}", f"sm:audit_log:{mid}"
            ]
            code, msg, ver = await RedisScripts.execute(redis, RedisScripts.TIMEOUT_VOTING_LUA, keys, [uid, mid, str(ts)])
            result = {"success": code == 1, "state": msg, "version": ver}

        elif etype == "SKIP_VOTE":
            keys = [f"sm:state:{uid}", f"sm:ver:m:{mid}", f"sm:audit_log:{mid}", idemp_key]
            code, msg, ver = await RedisScripts.execute(redis, RedisScripts.SKIP_VOTE_LUA, keys, [uid, mid, str(ts)])
            result = {"success": code in {1, 2}, "state": msg, "version": ver}

        elif etype == "RECOVER":
            state = await redis.get(f"sm:state:{uid}") or UnifiedState.HOME
            result = {"success": True, "state": state, "version": "0"}

        elif etype == "NEXT_MATCH":
            state = await redis.get(f"sm:state:{uid}")
            if state == UnifiedState.HOME:
                return await cls.process_event({"event_type": "START_SEARCH", "user_id": uid, "timestamp": ts})
            result = {"success": False, "error": "VOTING_INCOMPLETE", "current_state": state}

        elif etype == "SET_STATE":
            new_s = payload.get("new_state", "HOME")
            keys = [f"sm:state:{uid}", idemp_key, f"sm:ver:u:{uid}"]
            code, msg, ver = await RedisScripts.execute(redis, RedisScripts.SET_STATE_LUA, keys, [uid, str(ts), new_s])
            result = {"success": code in {1, 2}, "state": msg, "version": ver}

        # --- 2. RENDER GATE & ACK FLOW ---
        if result.get("success"):
            new_state = result.get("state")
            await cls._rehydrate_ui(uid, new_state, mid, result)
            
            # Symmetric update for partner
            if result.get("notify_partner"):
                p_info = result["notify_partner"]
                await cls._rehydrate_ui(p_info["user_id"], p_info["state"], p_info["match_id"])

        return result

    @classmethod
    async def _rehydrate_ui(cls, user_id: str, state: str, match_id: str, extra: dict = None):
        """Authoritative Rehydration with Render Storm Prevention."""
        redis = distributed_state.redis
        import app_state
        
        # 1. Check if render is actually needed (Issue 5 Gate)
        last_render = await redis.get(f"sm:last_render:{user_id}")
        last_ack = await redis.get(f"sm:render_ack:{user_id}")
        
        # Force render if state changed OR if previous render was never ACKed (Issue 4 ACK)
        if state == last_render and last_ack == "1":
            logger.info(f"UI for {user_id} already consistent with {state}. Skipping render.")
            return

        # 2. Select Adapter
        is_messenger = user_id.startswith("msg_")
        if not is_messenger and user_id.isdigit():
            if int(user_id) >= 10**15:
                is_messenger = True
        
        adapter = app_state.msg_adapter if is_messenger else app_state.tg_adapter
        
        # 3. Perform Render
        payload = {"match_id": match_id}
        if extra: payload.update(extra)
        
        # Reset ACK before rendering
        await redis.delete(f"sm:render_ack:{user_id}")
        
        success = await adapter.render_state(user_id, state, payload)
        
        if success:
            # 4. Update authoritative render state & ACK (Issue 4/5)
            await redis.set(f"sm:last_render:{user_id}", state)
            await redis.set(f"sm:render_ack:{user_id}", "1", ex=3600)
            logger.info(f"UI rehydrated for {user_id} -> {state} (ACK set)")
        else:
            logger.error(f"UI rehydration FAILED for {user_id}. ACK missing.")
