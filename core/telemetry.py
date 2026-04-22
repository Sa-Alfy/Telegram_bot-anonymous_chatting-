import contextvars
import time
import json
import uuid
import logging
from typing import Optional, Any, Dict
from utils.logger import logger as base_logger

# Context variables for tracing
trace_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("trace_id", default="")
user_id_var: contextvars.ContextVar[Optional[int]] = contextvars.ContextVar("user_id", default=None)

class TelemetryEvent:
    # Event Types
    ACTION_START = "ACTION_START"
    ACTION_END = "ACTION_END"
    REDIS_CALL = "REDIS_CALL"
    REDIS_RESULT = "REDIS_RESULT"
    STATE_CHANGE = "STATE_CHANGE"
    INVARIANT_VIOLATION = "INVARIANT_VIOLATION"

    # Statuses
    SUCCESS = "success"
    FAIL = "fail"
    WARNING = "warning"
    INFO = "info"


class InvariantEngine:
    @staticmethod
    def check_state_transition(user_id: int, old_state: str, new_state: str, partner_id: Optional[int] = None):
        """Self-diagnosing checks."""
        violations = []
        
        # Rule 1: IN_CHAT requires a partner
        if new_state == "CHAT_ACTIVE" and not partner_id:
            violations.append({
                "rule": "IN_CHAT_REQUIRES_PARTNER",
                "message": f"User {user_id} transitioned to CHAT_ACTIVE but has no partner_id."
            })
            
        # Rule 2: Cannot transition from SEARCHING directly to HOME without cancel/disconnect
        if old_state == "SEARCHING" and new_state == "HOME":
            # This might be valid if they cancelled, but worth noting if it happens unexpectedly
            pass
            
        for v in violations:
            EventLogger.log_event(
                event=TelemetryEvent.INVARIANT_VIOLATION,
                layer="invariant_engine",
                status=TelemetryEvent.FAIL,
                user_id=user_id,
                peer_id=partner_id,
                data={"violation": v["rule"], "message": v["message"], "old_state": old_state, "new_state": new_state}
            )


class EventLogger:
    _redis_client = None

    @classmethod
    def set_redis(cls, redis_client):
        cls._redis_client = redis_client

    @classmethod
    def log_event(
        cls,
        event: str,
        layer: str,
        status: str,
        user_id: Optional[int] = None,
        peer_id: Optional[int] = None,
        expected: Optional[Any] = None,
        actual: Optional[Any] = None,
        data: Optional[Dict[str, Any]] = None
    ):
        """Standardized structured event logger."""
        trace_id = trace_id_var.get()
        if not trace_id:
            # Generate one if missing (e.g. background task without context)
            trace_id = f"sys_{uuid.uuid4().hex[:8]}"

        u_id = user_id or user_id_var.get()

        payload = {
            "trace_id": trace_id,
            "user_id": u_id,
            "peer_id": peer_id,
            "event": event,
            "layer": layer,
            "status": status,
            "timestamp": time.time(),
            "data": data or {}
        }
        
        if expected is not None or actual is not None:
            payload["expected"] = expected
            payload["actual"] = actual

        # Log to stdout (JSON format for parsers if needed, or structured plain text)
        log_msg = f"[TRACE:{trace_id}] [{layer}] {event} status={status}"
        if u_id: log_msg += f" user={u_id}"
        if peer_id: log_msg += f" peer={peer_id}"
        if expected is not None: log_msg += f" exp={expected} act={actual}"
        
        if status == TelemetryEvent.FAIL or event == TelemetryEvent.INVARIANT_VIOLATION:
            base_logger.error(log_msg + f" data={json.dumps(payload['data'])}")
        elif status == TelemetryEvent.WARNING:
            base_logger.warning(log_msg)
        else:
            base_logger.debug(log_msg)

        # Log to Redis Stream if available
        if cls._redis_client:
            try:
                # Convert dict to string for redis hset compatibility if nested
                stringified_payload = {k: (json.dumps(v) if isinstance(v, (dict, list, tuple)) else str(v)) for k, v in payload.items()}
                # Fire and forget (in a real high-throughput system, use a background task or pipeline)
                import asyncio
                try:
                    loop = asyncio.get_running_loop()
                    loop.create_task(cls._push_to_redis(stringified_payload))
                except RuntimeError:
                    # Not in an async loop
                    pass
            except Exception as e:
                base_logger.error(f"Failed to push telemetry to Redis: {e}")

    @classmethod
    async def _push_to_redis(cls, payload: Dict[str, str]):
        if cls._redis_client:
            try:
                await cls._redis_client.xadd("admin:events", payload, maxlen=10000)
            except Exception as e:
                base_logger.error(f"Redis XADD error: {e}")

def with_trace_id(func):
    """Decorator to generate and inject trace_id for async handlers."""
    import functools
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        trace_id = f"req_{uuid.uuid4().hex[:12]}"
        token = trace_id_var.set(trace_id)
        try:
            return await func(*args, **kwargs)
        finally:
            trace_id_var.reset(token)
    return wrapper

