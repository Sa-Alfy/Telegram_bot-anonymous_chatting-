"""
===============================================================================
File: core/engine/actions.py
Description: The central event router and state transition engine for the bot.

How it works:
This file contains the ActionRouter, which processes every user interaction
(e.g., clicking a button, sending a command). It translates these events into
atomic state changes in Redis using Lua scripts and coordinates between
services (Matchmaking, User, Economy).

Architecture & Patterns:
- Router Pattern: Decouples platform-specific updates from business logic.
- Idempotency: Uses MD5 hash keys to ensure an event is only processed once.
- Service Integration: Orchestrates MatchmakingService and UserRepository.

How to modify:
- To add a new user action: Define a new event type (etype) in _handle_event.
- Safety: Always use cls.generate_idemp_key for new state-changing actions.
- Dependency Management: Import services INSIDE the specific 'elif' block to
  prevent circular import issues.
===============================================================================
"""

import time
import hashlib
import asyncio
import json
from typing import Dict, Any, Optional
from utils.logger import logger
from core.engine.state_machine import UnifiedState
from core.engine.redis_scripts import RedisScripts
from core.telemetry import EventLogger, TelemetryEvent, with_trace_id
from services.distributed_state import distributed_state
from database.repositories.user_repository import UserRepository
from utils.platform_adapter import PlatformAdapter
import app_state

class ActionRouter:
    """
    The master controller for all stateful bot interactions.
    Handles searching, chatting, voting, and profile management with
    idempotency and atomic state guarantees.
    """

    @staticmethod
    def generate_idemp_key(user_id: str, event_type: str, match_id: Optional[str], timestamp: int) -> str:
        """Creates a unique key to prevent the same action from firing twice."""
        raw = f"{user_id}:{event_type}:{match_id or 'none'}:{timestamp}"
        h = hashlib.md5(raw.encode()).hexdigest()
        return f"sm:idemp:{h}"

    @classmethod
    @with_trace_id
    async def process_event(cls, event: Dict[str, Any]) -> Dict[str, Any]:
        """Main entry point for all bot state changes."""
        start_time = time.time()
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
        try:
            result = await cls._handle_event(etype, uid, mid, ts, payload, idemp_key, redis)
        except Exception as e:
            logger.error(f"Engine Error in {etype}: {e}", exc_info=True)
            result = {"success": False, "error": str(e)}

        duration = (time.time() - start_time) * 1000
        
        # Publish Trace to Admin Dashboard
        trace = {
            "event_type": etype,
            "user_id": uid,
            "match_id": mid,
            "payload": payload,
            "success": result.get("success", False),
            "error": result.get("error"),
            "state": result.get("state") or "unknown",
            "duration_ms": duration
        }
        asyncio.create_task(cls._publish_trace(trace))

        # --- 2. RENDER GATE & ACK FLOW ---
        if result.get("success"):
            new_state = result.get("state")
            if new_state or result.get("force_render"):
                await cls._rehydrate_ui(uid, new_state, mid, result)
            
            # Symmetric update for partner
            if result.get("notify_partner"):
                p_info = result["notify_partner"]
                if p_info.get("state") or p_info.get("force_render"):
                    await cls._rehydrate_ui(
                        p_info["user_id"], 
                        p_info.get("state"), 
                        p_info.get("match_id", "global"), 
                        p_info
                    )

        return result

    @classmethod
    async def _publish_trace(cls, trace: Dict[str, Any]):
        """Pushes event trace to Redis Stream for the Admin Dashboard."""
        try:
            if not distributed_state.redis:
                return
            
            flat_trace = {}
            for k, v in trace.items():
                try:
                    if v is None:
                        flat_trace[k] = ""
                    elif isinstance(v, bool):
                        flat_trace[k] = str(v).lower()
                    elif isinstance(v, (int, float)):
                        flat_trace[k] = str(v)
                    elif isinstance(v, str):
                        flat_trace[k] = v
                    elif isinstance(v, (dict, list)):
                        flat_trace[k] = json.dumps(v, default=str)
                    else:
                        # Covers Pyrogram objects, dataclasses, etc.
                        flat_trace[k] = str(v)
                except Exception:
                    flat_trace[k] = f"[unserializable:{type(v).__name__}]"
            
            # Ensure event_type is always present for dashboard filtering
            if "event_type" not in flat_trace:
                flat_trace["event_type"] = "UNKNOWN"
                
            await distributed_state.redis.xadd("admin:events", flat_trace, maxlen=1000)
        except Exception as e:
            logger.warning(f"Failed to publish trace for {trace.get('event_type', '?')}: {e}")

    @classmethod
    async def _handle_event(cls, etype, uid, mid, ts, payload, idemp_key, redis) -> Dict[str, Any]:
        """Internal router for event logic."""
        logger.info(f"[ENGINE] uid={uid} event={etype}")
        if etype == "SHOW_PREFS":
            keys = [f"sm:state:{uid}", idemp_key, f"sm:ver:u:{uid}"]
            code, msg, ver = await RedisScripts.execute(redis, RedisScripts.SET_PREFS_LUA, keys, [uid, str(ts)])
            return {"success": code in {1, 2}, "state": msg, "version": ver}

        elif etype == "START_SEARCH":
            current_raw = await redis.get(f"sm:state:{uid}")
            if current_raw in ("MATCHED", "CONNECTING", "CHAT_END"):
                logger.warning(f"START_SEARCH pre-flight: resetting stuck state '{current_raw}' for {uid}")
                await redis.set(f"sm:state:{uid}", "HOME")
                await redis.delete(f"sm:partner:{uid}")
                await redis.lrem("sm:queue", 0, uid)

            pref = payload.get("pref", "")
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
            return {"success": code in {1, 2}, "state": msg, "version": ver}

        elif etype in {"STOP_SEARCH", "CANCEL_SEARCH"}:
            keys = [f"sm:state:{uid}", "sm:queue", f"sm:match:pref:{uid}", f"sm:ver:u:{uid}"]
            code, msg, ver = await RedisScripts.execute(redis, RedisScripts.STOP_SEARCH_LUA, keys, [uid, str(ts)])
            return {"success": code == 1, "state": msg, "version": ver}

        elif etype == "CONNECT":
            partner_id = await distributed_state.get_partner(uid)
            if not partner_id: return {"success": False, "error": "No partner assigned"}
            p_uid = str(partner_id)
            match_id = f"m_{min(uid, p_uid)}_{max(uid, p_uid)}"
            keys = [
                f"sm:state:{uid}", f"sm:state:{p_uid}", f"sm:ver:m:{match_id}", idemp_key,
                f"sm:event_log:{match_id}", f"sm:audit_log:{match_id}"
            ]
            code, msg, ver = await RedisScripts.execute(redis, RedisScripts.CONNECT_LUA, keys, [match_id, uid, p_uid, str(ts)])
            return {
                "success": code in {1, 2}, "state": msg, "version": ver,
                "notify_partner": {"user_id": p_uid, "state": UnifiedState.CHAT_ACTIVE, "match_id": match_id}
            }

        elif etype == "END_CHAT":
            from services.matchmaking import MatchmakingService
            c_uid = UserRepository._sanitize_id(uid)
            stats = await MatchmakingService.disconnect(uid)
            if not stats: return {"success": False, "error": "No active session"}
            
            p_uid = str(stats["partner_id"])
            
            # Create partner-facing stats by swapping U1/U2 fields
            partner_stats = stats.copy()
            partner_stats.update({
                "user_id": p_uid,
                "partner_id": uid,
                "coins_earned": stats.get("u2_coins_earned", 0),
                "xp_earned": stats.get("u2_xp_earned", 0),
                "coins_balance": stats.get("u2_coins_balance", 0),
                "total_xp": stats.get("u2_total_xp", 0),
                "u1_levelup": stats.get("u2_levelup", False),
                # Keep u2 fields for symmetry if needed, but the primary ones are now "ours"
                "u2_coins_earned": stats.get("coins_earned", 0),
                "u2_xp_earned": stats.get("xp_earned", 0),
                "u2_coins_balance": stats.get("coins_balance", 0),
                "u2_total_xp": stats.get("total_xp", 0),
                "u2_levelup": stats.get("u1_levelup", False)
            })

            return {
                "success": True, 
                "state": UnifiedState.VOTING,
                "version": "1", 
                "match_id": mid,
                "payload": stats,
                "notify_partner": {
                    "user_id": p_uid, 
                    "state": UnifiedState.VOTING, 
                    "match_id": mid,
                    "payload": partner_stats
                }
            }

        elif etype == "SUBMIT_VOTE":
            vtype = payload.get("type")
            vval = payload.get("value")
            keys = [f"sm:state:{uid}", f"sm:vote:{mid}:{uid}", f"sm:vote_lock:{mid}", f"sm:ver:m:{mid}", f"sm:audit_log:{mid}", idemp_key]
            code, msg, ver = await RedisScripts.execute(redis, RedisScripts.SUBMIT_VOTE_LUA, keys, [uid, mid, vtype, vval, str(ts)])
            signals = await redis.hgetall(f"sm:vote:{mid}:{uid}")
            
            # UX: Redirect to HOME if voting is done (according to Lua)
            effective_state = msg
            if msg == "VOTING_COMPLETE":
                effective_state = UnifiedState.HOME
            
            result = {
                "success": code == 1, 
                "state": effective_state, 
                "version": ver, 
                "signals": signals,
                "force_render": True # Ensure HOME menu pops up immediately
            }
            
            if result["success"] and mid.startswith("m_"):
                try:
                    # ROBUST EXTRACTION: Messenger IDs contain underscores, so simple split fails.
                    # mid is "m_<id1>_<id2>". We know our own ID (uid).
                    m_body = mid[2:] # Strip "m_"
                    u_str = str(uid)
                    if m_body.startswith(u_str + "_"):
                        p_uid = m_body[len(u_str)+1:]
                    elif m_body.endswith("_" + u_str):
                        p_uid = m_body[:-len(u_str)-1]
                    else:
                        # Final fallback: look for the part that is NOT our own ID
                        # (Handles cases where mid might be "m_idA_idB" in any order)
                        parts = m_body.split("_")
                        if len(parts) == 2:
                            p_uid = parts[1] if parts[0] == u_str else parts[0]
                        elif len(parts) > 2:
                            # Complex case: one or both IDs contain underscores (Messenger)
                            if m_body.startswith(u_str + "_"):
                                p_uid = m_body[len(u_str)+1:]
                            elif m_body.endswith("_" + u_str):
                                p_uid = m_body[:-len(u_str)-1]
                            else:
                                # This should be unreachable if mid was created correctly
                                p_uid = parts[0] # Desperate fallback
                        else:
                            p_uid = m_body # Likely a single ID match_id (searching)
                    
                    from database.repositories.vote_repository import VoteRepository
                    db_vote_type = vval if vtype == "reputation" else None
                    db_gender_vote = vval if vtype == "identity" else None
                    if vval == "good": db_vote_type = "like"
                    elif vval == "bad": db_vote_type = "dislike"
                    
                    # Sanitize IDs for database using repository helper
                    c_uid = UserRepository._sanitize_id(uid)
                    c_pid = UserRepository._sanitize_id(p_uid)
                    
                    # Safety check: Ensure voted user exists to prevent ForeignKeyViolation
                    voted_user = await UserRepository.get_by_telegram_id(c_pid)
                    if voted_user:
                        await VoteRepository.submit_vote(voter_id=c_uid, voted_id=c_pid, 
                                                       vote_type=db_vote_type, gender_vote=db_gender_vote)
                    else:
                        logger.warning(f"Skipping DB vote: Target user {c_pid} not found in database.")
                    if result["success"] and vtype == "reputation" and vval == "good":
                        try:
                            # Notify the voted user about their karma boost
                            await PlatformAdapter.send_cross_platform(
                                app_state.telegram_app, 
                                p_uid, 
                                "✨ **Karma Boost!**\nYour partner gave you a 'Good' rating. Your reputation has increased!"
                            )
                        except Exception:
                            pass

                except Exception as e:
                    logger.error(f"Failed to persist vote for {uid} in {mid}: {e}")
            return result

        elif etype == "TIMEOUT_VOTING":
            keys = [
                f"sm:state:{uid}", f"sm:vote:{mid}:{uid}", f"sm:vote_lock:{mid}",
                f"sm:ver:m:{mid}", f"sm:audit_log:{mid}"
            ]
            code, msg, ver = await RedisScripts.execute(redis, RedisScripts.TIMEOUT_VOTING_LUA, keys, [uid, mid, str(ts)])
            return {"success": code == 1, "state": msg, "version": ver}

        elif etype == "SKIP_VOTE":
            keys = [f"sm:state:{uid}", f"sm:ver:m:{mid}", f"sm:audit_log:{mid}", idemp_key]
            code, msg, ver = await RedisScripts.execute(redis, RedisScripts.SKIP_VOTE_LUA, keys, [uid, mid, str(ts)])
            # force_render=True ensures HOME render is not skipped by the ACK cache
            # (prevents user getting stuck on a blank screen after voting)
            return {"success": code in {1, 2}, "state": msg, "version": ver, "force_render": True}

        elif etype == "NEXT_MATCH":
            state = await redis.get(f"sm:state:{uid}")
            if state in (UnifiedState.CHAT_ACTIVE, UnifiedState.VOTING):
                # Call _handle_event directly to suppress intermediate UI renders.
                # Only the final START_SEARCH result is returned, so only ONE
                # render fires (SEARCHING) instead of VOTING -> HOME -> SEARCHING flicker.
                ec_key = cls.generate_idemp_key(uid, "END_CHAT", mid, ts)
                sv_key = cls.generate_idemp_key(uid, "SKIP_VOTE", mid, ts)
                ss_key = cls.generate_idemp_key(uid, "START_SEARCH", "global", ts)

                if state == UnifiedState.CHAT_ACTIVE:
                    await cls._handle_event("END_CHAT", uid, mid, ts, payload, ec_key, redis)
                await cls._handle_event("SKIP_VOTE", uid, mid, ts, payload, sv_key, redis)
                return await cls._handle_event("START_SEARCH", uid, "global", ts, {}, ss_key, redis)
            return {"success": False, "error": "VOTING_INCOMPLETE", "current_state": state}

        elif etype == "SHOW_PROFILE":
            c_uid = UserRepository._sanitize_id(uid)
            user_data = await UserRepository.get_by_telegram_id(c_uid)
            keys = [f"sm:state:{uid}", idemp_key, f"sm:ver:u:{uid}"]
            code, msg, ver = await RedisScripts.execute(redis, RedisScripts.SET_STATE_LUA, keys, [uid, str(ts), UnifiedState.PROFILE])
            return {"success": code in {1, 2}, "state": UnifiedState.PROFILE, "version": ver, "user_data": user_data}

        elif etype == "SHOW_STATS":
            c_uid = UserRepository._sanitize_id(uid)
            user_data = await UserRepository.get_by_telegram_id(c_uid)
            keys = [f"sm:state:{uid}", idemp_key, f"sm:ver:u:{uid}"]
            code, msg, ver = await RedisScripts.execute(redis, RedisScripts.SET_STATE_LUA, keys, [uid, str(ts), UnifiedState.STATS])
            return {"success": code in {1, 2}, "state": UnifiedState.STATS, "version": ver, "user_data": user_data}

        elif etype == "START_ONBOARDING":
            keys = [f"sm:state:{uid}", idemp_key, f"sm:ver:u:{uid}"]
            code, msg, ver = await RedisScripts.execute(redis, RedisScripts.SET_STATE_LUA, keys, [uid, str(ts), UnifiedState.REG_GENDER])
            return {"success": code in {1, 2}, "state": UnifiedState.REG_GENDER, "version": ver}

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
                await UserService.update_profile(c_uid, bio=value[:200], is_guest=0)
                next_state = UnifiedState.HOME
            keys = [f"sm:state:{uid}", idemp_key, f"sm:ver:u:{uid}"]
            code, msg, ver = await RedisScripts.execute(redis, RedisScripts.SET_STATE_LUA, keys, [uid, str(ts), next_state])
        elif etype == "CONFIRM_REVEAL":
            from services.user_service import UserService
            from state.match_state import match_state
            cost = payload.get("cost", 0)
            c_uid = str(UserRepository._sanitize_id(uid))
            partner_id = await match_state.get_partner(uid)
            
            if not partner_id:
                return {"success": False, "error": "Partner disconnected."}
            
            if await UserService.deduct_coins(c_uid, cost):
                partner = await UserRepository.get_by_telegram_id(partner_id)
                # Reveal logic...
                return {"success": True, "cost": cost, "partner_data": partner}
            else:
                return {"success": False, "error": f"You need {cost} coins for this reveal!"}

        elif etype == "REVEAL_IDENTITY":
            from state.match_state import match_state
            from services.economy_service import EconomyService
            c_uid = str(UserRepository._sanitize_id(uid))
            partner_id = await match_state.get_partner(uid)
            if not partner_id:
                return {"success": False, "error": "Partner disconnected!"}
            
            # Message count check (Legacy: 50 messages)
            msg_count = await distributed_state.get_message_count(uid, partner_id)
            if msg_count < 50:
                return {"success": False, "error": f"🔒 Reveal Locked. You need 50 messages (Current: {msg_count})."}
            
            cost = await EconomyService.get_dynamic_cost(c_uid, "identity_reveal", partner_id)
            return {"success": True, "cost": cost, "msg_count": msg_count}

        elif etype == "REPORT_USER":
            from state.match_state import match_state
            from services.matchmaking import MatchmakingService
            from services.user_service import UserService
            c_uid = str(UserRepository._sanitize_id(uid))
            partner_id = await match_state.get_partner(uid) # Use raw uid for state lookup
            if partner_id:
                # 1. Disconnect both users
                stats = await MatchmakingService.disconnect(uid)
                # 2. Record the report
                await UserService.report_user(c_uid, partner_id, "Reported via Unified Engine")
                # 3. Telemetry
                EventLogger.log_event(event="USER_REPORTED", layer="engine", status=TelemetryEvent.WARNING, user_id=c_uid, data={"reported_id": partner_id})
                return {"success": True, "reported_id": partner_id, "state": UnifiedState.VOTING}
            else:
                return {"success": False, "error": "No partner to report."}

        elif etype == "SUBMIT_VOTE":
            from database.repositories.vote_repository import VoteRepository
            c_uid = UserRepository._sanitize_id(uid)
            # Match metadata contains target_id or we derive it from match_id
            v_type = payload.get("type")
            v_val = payload.get("value")
            
            # Extract target_id from mid (format m_id1_id2)
            u1, u2 = mid.replace("m_", "").split("_")
            target_id = int(u2) if int(u1) == int(c_uid) else int(u1)
            
            vote_type = v_val if v_type == "reputation" else None
            gender_vote = v_val if v_type == "identity" else None
            
            await VoteRepository.submit_vote(
                voter_id=int(c_uid),
                voted_id=int(target_id),
                vote_type=vote_type,
                gender_vote=gender_vote
            )
            return {"success": True, "voted": True}

        elif etype == "SHOW_PREFS":
            return {"success": True, "show_prefs": True}

        elif etype == "BLOCK_USER":
            from state.match_state import match_state
            from database.repositories.blocked_repository import BlockedRepository
            c_uid = UserRepository._sanitize_id(uid)
            partner_id = await match_state.get_partner(c_uid)
            if partner_id:
                await BlockedRepository.block_user(c_uid, partner_id)
                from services.matchmaking import MatchmakingService
                await MatchmakingService.disconnect(c_uid)
                return {"success": True, "blocked_id": partner_id}
            else: return {"success": False, "error": "No partner to block."}

        elif etype == "SHOW_HELP":
            return {"success": True, "show_help": True}

        elif etype == "DELETE_USER_DATA":
            c_uid = UserRepository._sanitize_id(uid)
            await UserRepository.delete_user(c_uid)
            keys = [f"sm:state:{uid}", idemp_key, f"sm:ver:u:{uid}"]
            await RedisScripts.execute(redis, RedisScripts.SET_STATE_LUA, keys, [uid, str(ts), UnifiedState.HOME])
        elif etype == "KARMA_BOOST":
            from state.match_state import match_state
            c_uid = str(UserRepository._sanitize_id(uid))
            partner_id = await match_state.get_partner(uid)
            if not partner_id:
                return {"success": False, "error": "You are not in a chat!"}
            
            partner = await UserRepository.get_by_telegram_id(partner_id)
            partner_karma = partner.get("karma", 0) if partner else 0
            return {"success": True, "partner_karma": partner_karma}
        elif etype == "SEND_GIFT":
            from services.economy_service import EconomyService, GIFT_TYPES
            from services.user_service import UserService
            gift_key = payload.get("gift_key")
            c_uid = str(UserRepository._sanitize_id(uid))
            partner_id = await match_state.get_partner(uid)
            
            if not partner_id:
                return {"success": False, "error": "Partner disconnected."}
            
            result = await EconomyService.send_gift(c_uid, partner_id, gift_key)
            if result["success"]:
                gift = GIFT_TYPES.get(gift_key, {"name": "Gift"})
                # Notify partner via Adapter
                await PlatformAdapter.send_cross_platform(
                    app_state.telegram_app, partner_id, 
                    f"🎁 **You received a gift!**\nYour partner sent you a {gift['name']}!", 
                    None
                )
                return {"success": True, "gift": gift_key, "reveal_data": result.get("reveal_data")}
            else:
                return {"success": False, "error": result.get("message", "Gift failed.")}
        
        elif etype == "SHOW_GIFTS":
            return {"success": True, "show_gifts": True}

        # DUAL-RELAY NOTE: This handles engine-routed messages (Messenger + cross-platform).
        # Telegram-originated messages are relayed in handlers/chat.py directly.
        # Do NOT consolidate until both paths are fully audited.
        elif etype == "SEND_MESSAGE":
            from state.match_state import match_state
            from utils.content_filter import check_message, apply_enforcement, get_user_warning
            from services.user_service import UserService
            from services.matchmaking import MatchmakingService
            
            # CRITICAL: Use RAW uid for Redis/Partner lookup. 
            # Redis keys (sm:partner:...) preserve the msg_ prefix.
            partner_id = await match_state.get_partner(uid)
            text = payload.get("text", "")
            from utils.rate_limiter import rate_limiter
            
            c_uid = UserRepository._sanitize_id(uid)
            can_send, reason = await rate_limiter.can_send_message(c_uid)
            if not can_send:
                if reason.startswith("MUTED:"):
                    ttl = reason.split(":")[-1]
                    return {"success": False, "error": f"🚫 You have been muted for {ttl} seconds for spamming."}
                elif reason == "DAILY_CAP":
                    return {"success": False, "error": "📈 You have reached your daily message limit."}
                return {"success": False, "error": "⚠️ Please slow down! (1s cooldown)"}
            
            if not partner_id:
                return {"success": False, "error": "You're not chatting with anyone yet."}
            else:
                is_safe, violation = check_message(text)
                if not is_safe:
                    EventLogger.log_event(event="MESSAGE_FILTERED", layer="content_filter", status=TelemetryEvent.WARNING, user_id=c_uid, peer_id=partner_id, data={"violation": violation})
                    decision = await apply_enforcement(c_uid, violation)
                    action = decision["action"]
                    penalty = decision["penalty"]
                    if penalty > 0: await UserService.deduct_coins(c_uid, penalty)
                    warning = get_user_warning(decision["final_severity"], decision["description"], penalty)
                    if action in ("terminate_chat", "auto_ban_user"):
                        await MatchmakingService.disconnect(c_uid)
                        if action == "auto_ban_user": await UserRepository.set_blocked(c_uid, True)
                        return {"success": False, "error": warning, "terminated": True}
                    else: return {"success": False, "error": warning}
                else:
                    await UserService.increment_challenge(c_uid, "messages_sent")
                    await distributed_state.increment_message_count(c_uid, partner_id)
                    try:
                        await PlatformAdapter.send_cross_platform(app_state.telegram_app, partner_id, f"💬 {text}", None)
                        return {"success": True}
                    except Exception as e:
                        return {"success": False, "error": "Delivery failed"}

        elif etype == "SEND_MEDIA":
            from state.match_state import match_state
            c_uid = str(UserRepository._sanitize_id(uid))
            partner_id = await match_state.get_partner(uid)
            if not partner_id:
                return {"success": False, "error": "❌ Partner disconnected."}
            
            m_type = payload.get("media_type")
            file_id = payload.get("file_id")
            url = payload.get("url")
            caption = payload.get("caption", "")
            
            try:
                # Use PlatformAdapter to handle cross-platform delivery
                await PlatformAdapter.send_cross_platform(
                    app_state.telegram_app, partner_id, caption, 
                    media_type=m_type, media_url=url or file_id
                )
                return {"success": True}
            except Exception as e:
                logger.error(f"Engine media relay failed: {e}")
                return {"success": False, "error": "Delivery failed"}

        elif etype == "KARMA_BOOST":
            from state.match_state import match_state
            c_uid = UserRepository._sanitize_id(uid)
            partner_id = await match_state.get_partner(c_uid)
            if not partner_id:
                return {"success": False, "error": "❌ You are not in a chat!"}
            
            partner = await UserRepository.get_by_telegram_id(partner_id)
            partner_karma = partner.get("karma", 0) if partner else 0
            
            return {
                "success": True,
                "text": f"⭐ **Partner Karma Score:** {partner_karma}\n\nSend a Rose to boost their karma! Each rose adds +1 Karma and costs 10 coins.",
                "reply_markup": [
                    {"title": "🌹 Send Rose (+1 Karma, 10 coins)", "payload": "send_gift_rose"},
                    {"title": "🔙 Back to Chat", "payload": "RECOVER"}
                ]
            }

        elif etype == "SEND_GIFT":
            from state.match_state import match_state
            from services.economy_service import EconomyService
            c_uid = UserRepository._sanitize_id(uid)
            partner_id = await match_state.get_partner(c_uid)
            if not partner_id:
                return {"success": False, "error": "❌ Partner disconnected."}
            
            gift_key = payload.get("gift_key")
            result = await EconomyService.send_gift(c_uid, partner_id, gift_key)
            
            if not result.get("success"):
                return {"success": False, "error": result.get("error", "Transaction failed")}
            
            # Send result back to UI
            return {
                "success": True,
                "alert": result.get("alert"),
                "show_alert": True,
                "text": result.get("text"),
                "reply_markup": [
                    {"title": "🔙 Back to Chat", "payload": "RECOVER"}
                ],
                "notify_partner": {
                    "user_id": str(partner_id),
                    "text": result.get("notify_partner", {}).get("text"),
                    "force_render": True
                }
            }

        elif etype == "SEND_MEDIA":
            from state.match_state import match_state
            from utils.behavior_tracker import behavior_tracker
            
            # Use RAW uid for Redis lookup
            partner_id = await match_state.get_partner(uid)
            c_uid = UserRepository._sanitize_id(uid)
            
            media_type = payload.get("media_type")
            url = payload.get("url")
            file_id = payload.get("file_id")
            from utils.rate_limiter import rate_limiter
            
            if not partner_id: return {"success": False, "error": "No partner."}
            
            can_send, reason = await rate_limiter.can_send_message(c_uid)
            if not can_send:
                if reason.startswith("MUTED:"):
                    ttl = reason.split(":")[-1]
                    return {"success": False, "error": f"🚫 Muted for {ttl}s."}
                return {"success": False, "error": "⚠️ Rate limit exceeded."}
            
            if not partner_id: return {"success": False, "error": "No partner."}
            else:
                if media_type in ("voice", "video", "video_note"):
                    user = await UserRepository.get_by_telegram_id(c_uid)
                    if not user or not user.get("vip_status"): return {"success": False, "error": "VIP required for this media type."}
                await behavior_tracker.record_message_sent(c_uid, f"[Media:{media_type}]")
                await behavior_tracker.record_message_received(partner_id)
                await distributed_state.increment_message_count(c_uid, partner_id)
                try:
                    await PlatformAdapter.send_cross_platform(app_state.telegram_app, partner_id, text=payload.get("caption", ""), media_type=media_type, media_url=url or file_id)
                    return {"success": True}
                except Exception as e: return {"success": False, "error": "Media delivery failed"}

        elif etype == "SHOW_SHOP": return {"success": True, "show_shop": True}

        elif etype == "PURCHASE_ITEM":
            from services.user_service import UserService
            c_uid = UserRepository._sanitize_id(uid)
            item_id = payload.get("item_id")
            SHOP_ITEMS = {
                "BUY_VIP":   {"cost": 500,  "field": "vip_status",  "value": True, "duration": 30 * 86400},
                "BUY_OG":    {"cost": 300,  "field": "badge_og",    "value": True},
                "BUY_WHALE": {"cost": 1000, "field": "badge_whale", "value": True},
            }
            item = SHOP_ITEMS.get(item_id)
            if not item: return {"success": False, "error": "Unknown item."}
            else:
                user = await UserRepository.get_by_telegram_id(c_uid)
                if not await UserService.deduct_coins(c_uid, item["cost"]): return {"success": False, "error": f"Insufficient coins! (Need {item['cost']})"}
                else:
                    update_data = {item["field"]: item["value"]}
                    if "duration" in item:
                        current_expires = user.get("vip_expires_at", 0)
                        base_time = max(time.time(), current_expires)
                        update_data["vip_expires_at"] = int(base_time) + item["duration"]
                    await UserRepository.update(c_uid, **update_data)
                    return {"success": True, "item_name": item_id}

        elif etype == "REVEAL_IDENTITY":
            # INLINED from EconomyHandler.handle_reveal() — do NOT import from handlers/ here.
            # EconomyHandler.handle_reveal() is preserved in handlers/actions/economy.py
            # for CALLBACK_MAP legacy path and admin flows.
            from state.match_state import match_state as _ms
            from services.economy_service import EconomyService
            from database.repositories.user_repository import UserRepository as _UR
            from services.distributed_state import distributed_state as _ds
            c_uid = _UR._sanitize_id(uid)
            partner_id = await _ms.get_partner(c_uid)
            if not partner_id:
                return {"success": False, "error": "❌ Partner disconnected!", "force_render": True}
            cost = await EconomyService.get_dynamic_cost(c_uid, "identity_reveal", partner_id)
            user = await _UR.get_by_telegram_id(c_uid)
            msg_count = await _ds.get_message_count(c_uid, partner_id)
            if cost == -1:
                return {
                    "success": False,
                    "error": f"🔒 Reveal Locked — need 50 messages ({msg_count}/50)",
                    "force_render": True
                }
            if user and user.get("is_guest", 1):
                return {"success": False, "error": "❌ Create a profile first!", "force_render": True}
            if user and user["coins"] < cost:
                return {"success": False, "error": f"❌ Need {cost} coins!", "force_render": True}
            if msg_count < 200:
                tier_name, reveal_desc = "🥉 Tier 1: Basic", "Reveals: Gender, Age"
            elif msg_count < 500:
                tier_name, reveal_desc = "🥈 Tier 2: Detailed", "Reveals: Age, Location, Bio, Interests"
            else:
                tier_name, reveal_desc = "🥇 Tier 3: Full Profile", "Reveals: Full Name, Profile Photo, and all Bio details"
            from adapters.telegram.keyboards import confirm_reveal_menu
            from state.match_state import UserState
            return {
                "success": True,
                "text": f"🔍 **Unmask Partner: {tier_name}**\n\n{reveal_desc}\n\nCost: **{cost} coins**\n"
                        f"(Conversation: {msg_count} msgs)\n\nContinue?",
                "reply_markup": confirm_reveal_menu(cost, partner_id, UserState.CHATTING),
                "force_render": True
            }

        elif etype == "CONFIRM_REVEAL":
            # INLINED from EconomyHandler.handle_confirm_reveal() — do NOT import from handlers/ here.
            # EconomyHandler.handle_confirm_reveal() is preserved in handlers/actions/economy.py
            # for the confirm_reveal_ dynamic prefix path in on_callback().
            from state.match_state import match_state as _ms
            from services.user_service import UserService as _US
            from database.repositories.user_repository import UserRepository as _UR
            from services.distributed_state import distributed_state as _ds
            c_uid = _UR._sanitize_id(uid)
            cost = payload.get("cost", 15)
            partner_id = await _ms.get_partner(c_uid)
            if not partner_id:
                return {"success": False, "error": "❌ Partner disconnected!", "force_render": True}
            if not await _US.deduct_coins(c_uid, cost):
                return {"success": False, "error": "❌ Not enough coins!", "force_render": True}
            partner = await _UR.get_by_telegram_id(partner_id)
            msg_count = await _ds.get_message_count(c_uid, partner_id)
            if not partner:
                reveal_text = "🌟 **Identity Unmasked!**\n🆔 **ID:** `1`\n🏷 **Name:** System AI (Echo)"
                notify_text = None
            else:
                age = partner.get("age", "Unknown")
                interests = partner.get("interests", "None specified")
                gender = partner.get("gender", "Secret")
                location = partner.get("location", "Hidden")
                bio = partner.get("bio", "No bio")
                name = partner.get("first_name", "Stranger")
                if msg_count < 200:
                    reveal_text = f"🥉 Basic Reveal (Tier 1)\n━━━━━━━━━━━━━━━━━━\n🚻 **Gender:** {gender}\n🎂 **Age:** {age}\n\n_Chat more for more details!_"
                    notify_text = "⚠️ Someone unmasked your **Gender & Age**!"
                elif msg_count < 500:
                    reveal_text = f"🥈 Detailed Reveal (Tier 2)\n━━━━━━━━━━━━━━━━━━\n🚻 **Gender:** {gender}\n🎂 **Age:** {age}\n📍 **Loc:** {location}\n🎨 **Interests:** {interests}\n📝 **Bio:** {bio}"
                    notify_text = "⚠️ Someone unmasked your **Bio, Location & Interests**!"
                else:
                    reveal_text = f"🥇 Full Reveal (Tier 3)\n━━━━━━━━━━━━━━━━━━\n🏷 **Name:** {name}\n🚻 **Gender:** {gender}\n🎂 **Age:** {age}\n📍 **Loc:** {location}\n🎨 **Interests:** {interests}\n📝 **Bio:** {bio}"
                    notify_text = "⚠️ Someone just performed a **Full Identity Unmask** on you!"
            if partner_id != 1:
                from database.repositories.reveal_repository import RevealRepository
                await RevealRepository.log_reveal(c_uid, partner_id, "tiered", cost)
            from adapters.telegram.keyboards import chat_menu
            from state.match_state import UserState
            resp = {
                "success": True,
                "text": reveal_text,
                "reply_markup": chat_menu(UserState.CHATTING, partner_id),
                "force_render": True
            }
            if notify_text and partner_id != 1:
                resp["notify_partner"] = {"user_id": str(partner_id), "text": notify_text, "force_render": False}
            return resp

        elif etype == "SEND_ICEBREAKER":
            # INLINED from MatchingHandler.handle_icebreaker() — do NOT import from handlers/ here.
            # MatchingHandler.handle_icebreaker() is preserved in handlers/actions/matching.py
            # for CALLBACK_MAP legacy path and admin flows.
            import random
            from state.match_state import match_state as _ms
            from services.user_service import UserService as _US
            from database.repositories.user_repository import UserRepository as _UR
            from state.match_state import UserState
            c_uid = _UR._sanitize_id(uid)
            partner_id = await _ms.get_partner(c_uid)
            if not partner_id:
                return {"success": False, "error": "❌ You are not connected to anyone!", "force_render": True}
            questions = [
                "Truth or Dare: What's the most embarrassing thing you've done on a date? 😳",
                "Deep Question: What's a controversial opinion you have? 🤔",
                "Fun Fact: If you could only eat one food for the rest of your life, what would it be? 🍕",
                "Spicy: What's the worst pickup line you've ever used or heard? 🔥",
                "Icebreaker: If you had to describe yourself in 3 emojis, what would they be? 🙈"
            ]
            if not await _US.deduct_coins(c_uid, 5):
                return {"success": False, "error": "❌ Icebreakers cost 5 coins!", "force_render": True}
            question = random.choice(questions)
            from adapters.telegram.keyboards import chat_menu
            return {
                "success": True,
                "text": f"🎲 **You activated an Icebreaker!**\n\n{question}",
                "reply_markup": chat_menu(UserState.CHATTING, partner_id),
                "force_render": True,
                "notify_partner": {
                    "user_id": str(partner_id),
                    "text": f"🎲 **Your partner activated an Icebreaker!**\n\n{question}",
                    "force_render": False
                }
            }

        elif etype == "RECOVER":
            from state.match_state import match_state
            c_uid = UserRepository._sanitize_id(uid)
            current_state = await match_state.get_user_state(uid) or UnifiedState.HOME
            mid = None
            
            # SELF-HEALING: If in a chat state but no partner exists, force reset to HOME
            if current_state in {UnifiedState.CHAT_ACTIVE, UnifiedState.MATCHED, UnifiedState.CONNECTING}:
                p_id = await match_state.get_partner(uid)
                if p_id: 
                    u1, u2 = (str(uid), str(p_id))
                    mid = f"m_{min(u1, u2)}_{max(u1, u2)}"
                else:
                    logger.warning(f"RECOVER: Found ghost state '{current_state}' for {uid}. Force resetting to HOME.")
                    current_state = UnifiedState.HOME
                    await redis.set(f"sm:state:{uid}", UnifiedState.HOME)
                    await redis.delete(f"sm:partner:{uid}")
            
            await cls._rehydrate_ui(uid, current_state, mid, {"force_render": True})
            return {"success": True, "state": current_state}

        elif etype == "SET_STATE":
            new_s = payload.get("new_state", "HOME")
            keys = [f"sm:state:{uid}", idemp_key, f"sm:ver:u:{uid}"]
            code, msg, ver = await RedisScripts.execute(redis, RedisScripts.SET_STATE_LUA, keys, [uid, str(ts), new_s])
            return {"success": code in {1, 2}, "state": msg, "version": ver}

        elif etype == "SHOW_GIFTS":
            from services.economy_service import GIFT_TYPES
            from state.match_state import match_state
            
            partner_id = await match_state.get_partner(uid)
            if not partner_id:
                return {"success": False, "error": "You must be in a chat to send gifts!"}
            
            # Generate gift buttons
            buttons = []
            for key, gift in GIFT_TYPES.items():
                buttons.append({
                    "title": f"{gift['name']} ({gift['cost']} 💰)",
                    "payload": f"SEND_GIFT:{key}"
                })
            buttons.append({"title": "🔙 Back", "payload": "RECOVER"})
            
            return {
                "success": True,
                "text": "🎁 *Gift Shop*\nSurprise your partner with a gift! Gifts boost Karma and reveal special perks.",
                "reply_markup": buttons,
                "force_render": True
            }

        elif etype == "SHOW_TOOLS":
            from state.match_state import match_state
            partner_id = await match_state.get_partner(uid)
            if not partner_id:
                return {"success": False, "error": "Not in a chat."}
                
            buttons = [
                {"title": "🎭 Reactions", "payload": "SHOW_REACTIONS"},
                {"title": "👁️ Reveal Identity", "payload": "REVEAL"},
                {"title": "🎁 Send Gift", "payload": "SHOW_GIFTS"},
                {"title": "🔙 Back", "payload": "RECOVER"}
            ]
            return {
                "success": True,
                "text": "🛠 *Companion Tools*\nEnhance your chat with these features!",
                "reply_markup": buttons,
                "force_render": True
            }

        elif etype == "SHOW_REACTIONS":
            from state.match_state import match_state
            partner_id = await match_state.get_partner(uid)
            if not partner_id:
                return {"success": False, "error": "Not in a chat."}
            
            # Emoji picker
            buttons = [
                [
                    {"title": "❤️", "payload": "react_heart"},
                    {"title": "😂", "payload": "react_joy"},
                    {"title": "😮", "payload": "react_wow"},
                    {"title": "😢", "payload": "react_sad"},
                    {"title": "👍", "payload": "react_up"}
                ],
                [{"title": "🔙 Back", "payload": "RECOVER"}]
            ]
            return {
                "success": True,
                "text": "🎭 *Select a Reaction*\nYour partner will see a popup with your reaction.",
                "reply_markup": buttons,
                "force_render": True
            }

        elif etype == "SUBMIT_REACTION":
            from state.match_state import match_state
            partner_id = await match_state.get_partner(uid)
            if not partner_id:
                return {"success": False, "error": "Not in a chat."}
            
            reaction = payload.get("value", "❤️")
            # Reactions are essentially special messages
            return {
                "success": True,
                "notify_partner": {
                    "user_id": str(partner_id),
                    "text": f"✨ Your partner sent a reaction: {reaction}",
                    "force_render": False
                }
            }

        return {"success": False, "error": f"Unknown event type: {etype}"}

    @classmethod
    async def _rehydrate_ui(cls, user_id: str, state: str, match_id: str, extra: dict = None):
        """Authoritative Rehydration with Render Storm Prevention."""
        redis = distributed_state.redis
        
        # 1. Check for Storm Prevention (Redis only)
        force = extra.get("force_render") if extra else False
        if redis:
            last_render = await redis.get(f"sm:last_render:{user_id}")
            last_ack = await redis.get(f"sm:render_ack:{user_id}")
            if state == last_render and last_ack == "1" and not force:
                logger.info(f"UI for {user_id} already consistent with {state}. Skipping render.")
                return

        # 2. Render via Platform Adapter
        success = await PlatformAdapter.render_state(user_id, state, extra)
        
        # 3. Update Sync Marker
        if success and redis:
            await redis.set(f"sm:last_render:{user_id}", state, ex=3600)
            await redis.set(f"sm:render_ack:{user_id}", "1", ex=3600)
