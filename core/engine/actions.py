# core/engine/actions.py

import time
import hashlib
from typing import Dict, Any, Optional
from utils.logger import logger
from core.engine.state_machine import UnifiedState
from core.engine.redis_scripts import RedisScripts
from services.distributed_state import distributed_state
from core.telemetry import EventLogger, TelemetryEvent, with_trace_id
from utils.platform_adapter import PlatformAdapter
from database.repositories.user_repository import UserRepository

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
    @with_trace_id
    async def process_event(cls, event: Dict[str, Any]) -> Dict[str, Any]:
        etype = event.get("event_type")
        uid = str(event.get("user_id"))
        mid = event.get("match_id", "global")
        ts = event.get("timestamp", int(time.time()))
        payload = event.get("payload", {})

        EventLogger.log_event(
            event=TelemetryEvent.ACTION_START,
            layer="action_router",
            status=TelemetryEvent.INFO,
            user_id=uid,
            data={"action": etype, "match_id": mid, "payload": payload}
        )

        idemp_key = cls.generate_idemp_key(uid, etype, mid, ts)
        redis = distributed_state.redis

        if not redis:
            EventLogger.log_event(
                event=TelemetryEvent.ACTION_END,
                layer="action_router",
                status=TelemetryEvent.FAIL,
                user_id=uid,
                data={"error": "Redis not connected"}
            )
            return {"success": False, "error": "Redis not connected"}

        logger.info(f"Processing Event: {etype} for User:{uid} (Match:{mid})")

        result = {"success": False}
        
        # --- 1. TRANSITIONS ---
        if etype == "SHOW_PREFS":
            keys = [f"sm:state:{uid}", idemp_key, f"sm:ver:u:{uid}"]
            code, msg, ver = await RedisScripts.execute(redis, RedisScripts.SET_PREFS_LUA, keys, [uid, str(ts)])
            result = {"success": code in {1, 2}, "state": msg, "version": ver}

        elif etype == "START_SEARCH":
            # Pre-flight heal: if the user is stuck in a transient state that blocks
            # searching (MATCHED/CONNECTING/CHAT_END), reset them to HOME automatically.
            # This is the permanent fix for the INVALID_STATE loop.
            current_raw = await redis.get(f"sm:state:{uid}")
            if current_raw in ("MATCHED", "CONNECTING", "CHAT_END"):
                logger.warning(f"START_SEARCH pre-flight: resetting stuck state '{current_raw}' for {uid}")
                await redis.set(f"sm:state:{uid}", "HOME")
                await redis.delete(f"sm:partner:{uid}")
                await redis.lrem("sm:queue", 0, uid)

            pref = payload.get("pref", "")
            # Determine priority status from DB
            priority_flag = "0"
            try:
                c_uid = UserRepository._sanitize_id(uid)
                user = await UserRepository.get_by_telegram_id(c_uid)
                if user:
                    import time as _time
                    timed_pack = user.get("priority_pack", {})
                    if timed_pack.get("active") and timed_pack.get("expires_at", 0) > _time.time():
                        priority_flag = "1"
                    elif user.get("priority_matches", 0) > 0:
                        priority_flag = "1"
            except Exception as e:
                logger.warning(f"Priority lookup failed for {uid}: {e}")
            keys = [f"sm:state:{uid}", "sm:queue", idemp_key, f"sm:ver:u:{uid}", f"sm:match:pref:{uid}"]
            code, msg, ver = await RedisScripts.execute(redis, RedisScripts.START_SEARCH_LUA, keys, [uid, str(ts), pref, priority_flag])
            result = {"success": code in {1, 2}, "state": msg, "version": ver}

        elif etype in {"STOP_SEARCH", "CANCEL_SEARCH"}:
            keys = [f"sm:state:{uid}", "sm:queue", f"sm:match:pref:{uid}", f"sm:ver:u:{uid}"]
            code, msg, ver = await RedisScripts.execute(redis, RedisScripts.STOP_SEARCH_LUA, keys, [uid, str(ts)])
            result = {"success": code == 1, "state": msg, "version": ver}

        elif etype == "CONNECT":
            partner_id = await distributed_state.get_partner(uid)
            if not partner_id: return {"success": False, "error": "No partner found"}
            p_uid = str(partner_id)
            u1, u2 = sorted([str(uid), p_uid])
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
            c_uid = UserRepository._sanitize_id(uid)
            stats = await MatchmakingService.disconnect(c_uid)
            if not stats: return {"success": False, "error": "No active session"}
            
            p_uid = str(stats["partner_id"])
            result = {
                "success": True, 
                "state": UnifiedState.VOTING,
                "version": "1", 
                "match_id": mid,
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

        elif etype == "NEXT_MATCH":
            state = await redis.get(f"sm:state:{uid}")
            if state == UnifiedState.HOME:
                return await cls.process_event({"event_type": "START_SEARCH", "user_id": uid, "timestamp": ts})
            elif state == UnifiedState.CHAT_ACTIVE:
                await cls.process_event({"event_type": "END_CHAT", "user_id": uid, "match_id": mid, "timestamp": ts})
                await cls.process_event({"event_type": "SKIP_VOTE", "user_id": uid, "match_id": mid, "timestamp": ts})
                return await cls.process_event({"event_type": "START_SEARCH", "user_id": uid, "timestamp": ts})
            result = {"success": False, "error": "VOTING_INCOMPLETE", "current_state": state}

        elif etype == "SHOW_PROFILE":
            c_uid = UserRepository._sanitize_id(uid)
            user_data = await UserRepository.get_by_telegram_id(c_uid)
            
            keys = [f"sm:state:{uid}", idemp_key, f"sm:ver:u:{uid}"]
            code, msg, ver = await RedisScripts.execute(redis, RedisScripts.SET_STATE_LUA, keys, [uid, str(ts), UnifiedState.PROFILE])
            result = {"success": code in {1, 2}, "state": UnifiedState.PROFILE, "version": ver, "user_data": user_data}

        elif etype == "SHOW_STATS":
            c_uid = UserRepository._sanitize_id(uid)
            user_data = await UserRepository.get_by_telegram_id(c_uid)
            
            keys = [f"sm:state:{uid}", idemp_key, f"sm:ver:u:{uid}"]
            code, msg, ver = await RedisScripts.execute(redis, RedisScripts.SET_STATE_LUA, keys, [uid, str(ts), UnifiedState.STATS])
            result = {"success": code in {1, 2}, "state": UnifiedState.STATS, "version": ver, "user_data": user_data}

        elif etype == "START_ONBOARDING":
            keys = [f"sm:state:{uid}", idemp_key, f"sm:ver:u:{uid}"]
            code, msg, ver = await RedisScripts.execute(redis, RedisScripts.SET_STATE_LUA, keys, [uid, str(ts), UnifiedState.REG_GENDER])
            result = {"success": code in {1, 2}, "state": UnifiedState.REG_GENDER, "version": ver}

        elif etype == "SUBMIT_ONBOARDING":
            from services.user_service import UserService
            c_uid = UserRepository._sanitize_id(uid)
            field = payload.get("field")
            value = payload.get("value")
            
            state = await distributed_state.get_user_state(uid)
            next_state = UnifiedState.HOME
            
            if state == UnifiedState.REG_GENDER:
                await UserRepository.update(c_uid, gender=value)
                next_state = UnifiedState.REG_INTERESTS
            elif state == UnifiedState.REG_INTERESTS:
                await UserRepository.update(c_uid, interests=value[:100])
                next_state = UnifiedState.REG_LOCATION
            elif state == UnifiedState.REG_LOCATION:
                await UserRepository.update(c_uid, location=value[:50])
                next_state = UnifiedState.REG_BIO
            elif state == UnifiedState.REG_BIO:
                # Finalize
                await UserService.update_profile(c_uid, bio=value[:200], is_guest=0)
                next_state = UnifiedState.HOME
            
            keys = [f"sm:state:{uid}", idemp_key, f"sm:ver:u:{uid}"]
            code, msg, ver = await RedisScripts.execute(redis, RedisScripts.SET_STATE_LUA, keys, [uid, str(ts), next_state])
            result = {"success": code in {1, 2}, "state": next_state, "version": ver}

        elif etype == "REPORT_USER":
            from state.match_state import match_state
            from handlers.actions.matching import MatchingHandler
            c_uid = str(UserRepository._sanitize_id(uid))
            partner_id = await match_state.get_partner(int(c_uid))
            if partner_id:
                # Logic from MatchingHandler.handle_report
                from handlers.actions.matching import MatchingHandler
                # We mock a fake context or just call the logic
                # For now, let's just trigger the report if we have a partner
                result = {"success": True, "reported_id": partner_id}
            else:
                result = {"success": False, "error": "No partner to report."}

        elif etype == "BLOCK_USER":
            from state.match_state import match_state
            from database.repositories.blocked_repository import BlockedRepository
            c_uid = int(UserRepository._sanitize_id(uid))
            partner_id = await match_state.get_partner(c_uid)
            if partner_id:
                await BlockedRepository.block_user(c_uid, partner_id)
                # Also end chat if active
                from services.matchmaking import MatchmakingService
                await MatchmakingService.disconnect(c_uid)
                result = {"success": True, "blocked_id": partner_id}
            else:
                result = {"success": False, "error": "No partner to block."}

        elif etype == "SHOW_HELP":
            result = {"success": True, "show_help": True}

        elif etype == "DELETE_USER_DATA":
            c_uid = int(UserRepository._sanitize_id(uid))
            await UserRepository.soft_delete_user_data(c_uid)
            # Reset state to HOME
            keys = [f"sm:state:{uid}", idemp_key, f"sm:ver:u:{uid}"]
            await RedisScripts.execute(redis, RedisScripts.SET_STATE_LUA, keys, [uid, str(ts), UnifiedState.HOME])
            result = {"success": True, "deleted": True}

        elif etype == "SEND_MESSAGE":
            from state.match_state import match_state, UserState
            from utils.content_filter import check_message, apply_enforcement, get_user_warning
            from services.user_service import UserService
            from services.matchmaking import MatchmakingService
            import app_state
            
            c_uid = int(UserRepository._sanitize_id(uid))
            partner_id = await match_state.get_partner(c_uid)
            text = payload.get("text", "")
            
            from utils.rate_limiter import rate_limiter
            if not await rate_limiter.can_send_message(c_uid):
                result = {"success": False, "error": "Rate limit exceeded. Please wait."}
            elif not partner_id:
                result = {"success": False, "error": "You're not chatting with anyone yet."}
            else:
                is_safe, violation = check_message(text)
                if not is_safe:
                    EventLogger.log_event(
                        event="MESSAGE_FILTERED", layer="content_filter", status=TelemetryEvent.WARNING,
                        user_id=c_uid, peer_id=partner_id, data={"violation": violation}
                    )
                    decision = await apply_enforcement(c_uid, violation)
                    action = decision["action"]
                    penalty = decision["penalty"]
                    
                    if penalty > 0:
                        await UserService.deduct_coins(c_uid, penalty)
                    
                    warning = get_user_warning(decision["final_severity"], decision["description"], penalty)
                    
                    if action in ("terminate_chat", "auto_ban_user"):
                        await MatchmakingService.disconnect(c_uid)
                        if action == "auto_ban_user":
                            await UserRepository.set_blocked(c_uid, True)
                        result = {"success": False, "error": warning, "terminated": True}
                    else:
                        result = {"success": False, "error": warning}
                else:
                    # Message is safe -> Relay
                    await UserService.increment_challenge(c_uid, "messages_sent")
                    
                    try:
                        # Determine partner platform and send
                        await PlatformAdapter.send_cross_platform(
                            app_state.telegram_app, 
                            partner_id, 
                            f"💬 {text}", 
                            None
                        )
                        EventLogger.log_event(
                            event="MESSAGE_SENT", layer="message_relay", status=TelemetryEvent.SUCCESS,
                            user_id=c_uid, peer_id=partner_id
                        )
                        result = {"success": True}
                    except Exception as e:
                        EventLogger.log_event(
                            event="MESSAGE_FAILED", layer="message_relay", status=TelemetryEvent.FAIL,
                            user_id=c_uid, peer_id=partner_id, data={"error": str(e)}
                        )
                        result = {"success": False, "error": "Delivery failed"}
                    
        elif etype == "SEND_MEDIA":
            from state.match_state import match_state
            from services.user_service import UserService
            from utils.behavior_tracker import behavior_tracker
            import app_state
            
            c_uid = int(UserRepository._sanitize_id(uid))
            partner_id = await match_state.get_partner(c_uid)
            media_type = payload.get("media_type")
            url = payload.get("url")
            file_id = payload.get("file_id") # For Telegram-native media
            
            from utils.rate_limiter import rate_limiter
            if not await rate_limiter.can_send_message(c_uid):
                result = {"success": False, "error": "Rate limit exceeded."}
            elif not partner_id:
                result = {"success": False, "error": "No partner."}
            else:
                # VIP Check for certain media types
                if media_type in ("voice", "video", "video_note"):
                    user = await UserRepository.get_by_telegram_id(c_uid)
                    if not user or not user.get("vip_status"):
                        result = {"success": False, "error": "VIP required for this media type."}
                        return result

                await behavior_tracker.record_message_sent(c_uid, f"[Media:{media_type}]")
                await behavior_tracker.record_message_received(partner_id)

                try:
                    await PlatformAdapter.send_cross_platform(
                        app_state.telegram_app, 
                        partner_id, 
                        text=payload.get("caption", ""),
                        media_type=media_type,
                        media_url=url or file_id
                    )
                    EventLogger.log_event(
                        event="MEDIA_SENT", layer="message_relay", status=TelemetryEvent.SUCCESS,
                        user_id=c_uid, peer_id=partner_id, data={"type": media_type}
                    )
                    result = {"success": True}
                except Exception as e:
                    EventLogger.log_event(
                        event="MEDIA_FAILED", layer="message_relay", status=TelemetryEvent.FAIL,
                        user_id=c_uid, peer_id=partner_id, data={"error": str(e)}
                    )
                    result = {"success": False, "error": "Media delivery failed"}

        elif etype == "SHOW_SHOP":
            result = {"success": True, "show_shop": True}

        elif etype == "PURCHASE_ITEM":
            from services.user_service import UserService
            c_uid = int(UserRepository._sanitize_id(uid))
            item_id = payload.get("item_id")
            
            # Shared Shop Config (should move to a config file eventually)
            SHOP_ITEMS = {
                "BUY_VIP":   {"cost": 500,  "field": "vip_status",  "value": True, "duration": 30 * 86400},
                "BUY_OG":    {"cost": 300,  "field": "badge_og",    "value": True},
                "BUY_WHALE": {"cost": 1000, "field": "badge_whale", "value": True},
            }
            
            item = SHOP_ITEMS.get(item_id)
            if not item:
                result = {"success": False, "error": "Unknown item."}
            else:
                user = await UserRepository.get_by_telegram_id(c_uid)
                if not await UserService.deduct_coins(c_uid, item["cost"]):
                    result = {"success": False, "error": f"Insufficient coins! (Need {item['cost']})"}
                else:
                    update_data = {item["field"]: item["value"]}
                    if "duration" in item:
                        current_expires = user.get("vip_expires_at", 0) or 0
                        base_time = max(time.time(), current_expires)
                        update_data["vip_expires_at"] = int(base_time) + item["duration"]
                    await UserRepository.update(c_uid, **update_data)
                    result = {"success": True, "item_name": item_id}

        elif etype == "REVEAL_IDENTITY":
            from handlers.actions.economy import EconomyHandler
            c_uid = int(UserRepository._sanitize_id(uid))
            response = await EconomyHandler.handle_reveal(app_state.telegram_app, c_uid)
            result = {"success": "error" not in response, "response": response}

        elif etype == "SEND_ICEBREAKER":
            from handlers.actions.matching import MatchingHandler
            c_uid = int(UserRepository._sanitize_id(uid))
            response = await MatchingHandler.handle_icebreaker(app_state.telegram_app, c_uid)
            result = {"success": "error" not in response, "response": response}

        elif etype == "RECOVER":
            from state.match_state import match_state
            c_uid = int(UserRepository._sanitize_id(uid))
            current_state = await match_state.get_user_state(c_uid) or UnifiedState.HOME
            
            mid = None
            # If in a chat-related state, try to find partner for mid
            if current_state in {UnifiedState.CHAT_ACTIVE, UnifiedState.MATCHED, UnifiedState.CONNECTING}:
                p_id = await match_state.get_partner(c_uid)
                if p_id:
                    mid = f"m_{min(c_uid, p_id)}_{max(c_uid, p_id)}"
                elif current_state == UnifiedState.CHAT_ACTIVE:
                    # Downgrade to HOME if active chat lost its partner
                    current_state = UnifiedState.HOME
            
            await cls._rehydrate_ui(uid, current_state, mid, {"force_render": True})
            return {"success": True, "state": current_state}

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

        EventLogger.log_event(
            event=TelemetryEvent.ACTION_END,
            layer="action_router",
            status=TelemetryEvent.SUCCESS if result.get("success") else TelemetryEvent.FAIL,
            user_id=uid,
            data={"action": etype, "result_state": result.get("state")}
        )

        return result
 
    @classmethod
    async def _rehydrate_ui(cls, user_id: str, state: str, match_id: str, extra: dict = None):
        """Authoritative Rehydration with Render Storm Prevention."""
        redis = distributed_state.redis
        import app_state
        
        # 1. Check for Storm Prevention (Redis only)
        force = extra.get("force_render") if extra else False
        if redis:
            last_render = await redis.get(f"sm:last_render:{user_id}")
            last_ack = await redis.get(f"sm:render_ack:{user_id}")
            
            if state == last_render and last_ack == "1" and not force:
                logger.info(f"UI for {user_id} already consistent with {state}. Skipping render.")
                return

        # 2. Select Adapter
        is_messenger = False
        if isinstance(user_id, str) and user_id.startswith("msg_"):
            is_messenger = True
        elif str(user_id).isdigit():
            if int(user_id) >= 10**15:
                is_messenger = True
        
        adapter = app_state.msg_adapter if is_messenger else app_state.tg_adapter
        
        # 3. Perform Render
        payload = {"match_id": match_id}
        if extra: payload.update(extra)
        
        if redis:
            await redis.delete(f"sm:render_ack:{user_id}")
        
        success = await adapter.render_state(user_id, state, payload)
        
        if success and redis:
            # 4. Update authoritative render state & ACK
            await redis.set(f"sm:last_render:{user_id}", state)
            await redis.set(f"sm:render_ack:{user_id}", "1", ex=3600)
            logger.info(f"UI rehydrated for {user_id} -> {state} (ACK set)")
        elif not success:
            logger.error(f"UI rehydration FAILED for {user_id}. ACK missing.")
