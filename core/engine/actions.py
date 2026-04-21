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

        elif etype == "END_CHAT":
            partner_id = await distributed_state.get_partner(uid)
            if not partner_id: return {"success": False, "error": "No partner found"}
            p_uid = str(partner_id)
            
            keys = [
                f"sm:state:{uid}", f"sm:state:{p_uid}",
                f"sm:partner:{uid}", f"sm:partner:{p_uid}",
                f"sm:ver:m:{mid}", f"sm:event_log:{mid}", f"sm:audit_log:{mid}", idemp_key
            ]
            code, msg, ver = await RedisScripts.execute(redis, RedisScripts.END_CHAT_LUA, keys, [uid, p_uid, mid, str(ts)])
            result = {
                "success": code in {1, 2}, "state": msg, "version": ver,
                "notify_partner": {"user_id": p_uid, "state": UnifiedState.VOTING, "match_id": mid}
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

        elif etype == "TIMEOUT_VOTING":
            keys = [
                f"sm:state:{uid}", f"sm:vote:{mid}:{uid}", f"sm:lock:vote:{mid}",
                f"sm:ver:m:{mid}", f"sm:audit_log:{mid}"
            ]
            code, msg, ver = await RedisScripts.execute(redis, RedisScripts.TIMEOUT_VOTING_LUA, keys, [uid, mid, str(ts)])
            result = {"success": code == 1, "state": msg, "version": ver}

        elif etype == "NEXT_MATCH":
            state = await redis.get(f"sm:state:{uid}")
            if state == UnifiedState.HOME:
                return await cls.process_event({"event_type": "START_SEARCH", "user_id": uid, "timestamp": ts})
            result = {"success": False, "error": "VOTING_INCOMPLETE", "current_state": state}

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
        adapter = app_state.msg_adapter if user_id.startswith("msg_") else app_state.tg_adapter
        
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
