# core/engine/reconciler.py

from typing import Tuple, Optional
from utils.logger import logger
from core.engine.state_machine import UnifiedState
from services.distributed_state import distributed_state

class Reconciler:
    """Internal reconciliation layer for healing orphaned/broken sessions.
    Safe Output States: CHAT_ACTIVE, CHAT_END, VOTING.
    """

    @staticmethod
    async def reconcile_user(user_id: str) -> Tuple[str, Optional[str]]:
        """Checks invariants and force-transitions user to a safe output state.
        Returns (new_state, partner_id).
        """
        redis = distributed_state.redis
        if not redis:
            return UnifiedState.HOME, None

        state = await redis.get(f"sm:state:{user_id}") or UnifiedState.HOME
        partner_id = await redis.get(f"sm:partner:{user_id}")
        match_id = "global" # Fallback if no partner
        if partner_id:
            # We derive match_id from user IDs to be stable
            u1, u2 = sorted([str(user_id), str(partner_id)])
            match_id = f"m_{u1}_{u2}"

        # 1. ANTI-FLAPPING LOCK (Issue 4)
        lock_key = f"sm:lock:reconcile:{match_id}"
        if await redis.get(lock_key):
            logger.info(f"Reconciliation locked for {match_id}. Skipping.")
            return state, partner_id

        # 2. CONVERGENCE GUARD (Issue 3)
        # Only reconcile if the current mismatch is DIFFERENT from the last stable mismatch
        last_stable = await redis.get(f"sm:stable:{match_id}")
        current_snapshot = f"{user_id}:{state}|{partner_id or 'none'}"
        if last_stable == current_snapshot:
            logger.info(f"State matches last stable snapshot for {match_id}. Convergence reached.")
            return state, partner_id

        logger.info(f"Reconciling User:{user_id} (Current:{state}, Partner:{partner_id})")
        # Set lock for 5s to prevent oscillation
        await redis.set(lock_key, "1", ex=5)


        # 1. Invariant: CHAT_ACTIVE but no partner
        if state == UnifiedState.CHAT_ACTIVE and not partner_id:
            logger.warning(f"Orphaned CHAT_ACTIVE detected for {user_id}. Forcing VOTING gate.")
            await redis.set(f"sm:state:{user_id}", UnifiedState.VOTING)
            return UnifiedState.VOTING, None

        # 2. Invariant: Partners but missing symmetric bond
        if partner_id:
            p_state = await redis.get(f"sm:state:{partner_id}")
            p_back_bond = await redis.get(f"sm:partner:{partner_id}")

            if p_back_bond != user_id:
                logger.warning(f"Symmetry breach for {user_id} <-> {partner_id}. Forcing CHAT_END.")
                # Force both to CHAT_END/VOTING if they are in active states
                await redis.set(f"sm:state:{user_id}", UnifiedState.VOTING)
                await redis.delete(f"sm:partner:{user_id}")
                return UnifiedState.VOTING, None

        # 3. Validation: If in CHAT_END, force move to VOTING (NO BYPASS)
        if state == UnifiedState.CHAT_END:
            await redis.set(f"sm:state:{user_id}", UnifiedState.VOTING)
            return UnifiedState.VOTING, partner_id

        # 4. Safe state return
        if state in {UnifiedState.CHAT_ACTIVE, UnifiedState.CHAT_END, UnifiedState.VOTING}:
            return state, partner_id
        
        # Default fallback for transients
        if state in {UnifiedState.MATCHED, UnifiedState.CONNECTING}:
            # If stuck in handshake, fallback to HOME or re-render?
            # Spec says safe output states only. So we'll push to CHAT_END or HOME?
            logger.info(f"User {user_id} stuck in {state}. Resetting to HOME.")
            await redis.set(f"sm:state:{user_id}", UnifiedState.HOME)
            state = UnifiedState.HOME

        # Post-Repair: Update last stable state to prevent immediate re-trigger
        new_snapshot = f"{user_id}:{state}|{partner_id or 'none'}"
        await redis.set(f"sm:stable:{match_id}", new_snapshot, ex=60)
        
        return state, partner_id

