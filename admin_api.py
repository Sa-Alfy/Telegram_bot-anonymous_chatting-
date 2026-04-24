import asyncio
import json
import os
import time
import requests
from typing import Dict, Any, List
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends, HTTPException, status, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import redis.asyncio as redis_async
import redis.exceptions as redis_exceptions
from dotenv import load_dotenv
from database.connection import db

load_dotenv()

app = FastAPI(title="Matchmaking Debug Dashboard")

# Security
DEBUG_SECRET = os.getenv("DEBUG_SECRET", "1532456870")  # Updated per user request
print(f"ADMIN SECURITY: Secret loaded (Length: {len(DEBUG_SECRET)}, Starts with: {DEBUG_SECRET[:2]}...)")
security = HTTPBearer()

def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    if credentials.credentials != DEBUG_SECRET:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return credentials.credentials

async def verify_ws_token(websocket: WebSocket) -> bool:
    token = websocket.query_params.get("token")
    if token != DEBUG_SECRET:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return False
    return True

# Redis Connection
redis_client = None

@app.on_event("startup")
async def startup_event():
    global redis_client
    redis_url = os.getenv("REDIS_URL")
    if not redis_url:
        print("❌ CRITICAL: REDIS_URL not set in env.")
        return

    print(f"Connecting to Redis at {redis_url[:15]}...")
    redis_client = redis_async.from_url(redis_url, decode_responses=True)
    try:
        await redis_client.ping()
        print("✅ Admin API connected to Redis.")
    except Exception as e:
        print(f"❌ Failed to connect Admin API to Redis: {e}")
        redis_client = None
        return

    try:
        # Setup Database connection
        print("Connecting to Database...")
        await db.connect()
        print("✅ Admin API connected to Database.")
    except Exception as e:
        print(f"❌ Failed to connect Admin API to Database: {e}")
        # We don't set redis_client to None here, let it continue if Redis is ok
    
    # Setup Consumer Group
    try:
        await redis_client.xgroup_create("admin:events", "dashboard", id="0", mkstream=True)
        print("✅ Consumer group 'dashboard' ready.")
    except redis_exceptions.ResponseError as e:
        if "BUSYGROUP" not in str(e):
            print(f"ℹ️ Consumer group info: {e}")
    
    # Start event consumer task
    asyncio.create_task(consume_events())


class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def broadcast(self, message: str):
        failed = []
        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except Exception:
                failed.append(connection)
        for f in failed:
            if f in self.active_connections:
                self.active_connections.remove(f)

manager = ConnectionManager()

async def consume_events():
    global redis_client
    if not redis_client: return
    
    print("Started consuming admin events...")
    # Generate a unique consumer name for this process
    consumer_name = f"admin_ws_{os.getpid()}"
    
    while True:
        try:
            # Block for up to 1 second waiting for new events
            streams = await redis_client.xreadgroup(
                "dashboard", consumer_name, {"admin:events": ">"}, count=100, block=1000
            )
            
            if streams:
                for stream, events in streams:
                    for message_id, payload in events:
                        # Broadcast to all connected clients
                        # Un-stringify nested JSON
                        clean_payload = {}
                        for k, v in payload.items():
                            try:
                                clean_payload[k] = json.loads(v)
                            except:
                                clean_payload[k] = v
                                
                        await manager.broadcast(json.dumps({
                            "type": "event",
                            "message_id": message_id,
                            "payload": clean_payload
                        }))
                        # Acknowledge the message
                        await redis_client.xack("admin:events", "dashboard", message_id)
        except asyncio.CancelledError:
            break
        except Exception as e:
            print(f"Event consumer error: {e}")
            await asyncio.sleep(2)


# --- REST API Endpoints ---

@app.get("/admin/verify")
async def verify_admin_token(_=Depends(verify_token)):
    return {"status": "ok"}

@app.get("/admin/user/{user_id}")
async def get_user_state(user_id: str, _=Depends(verify_token)):
    # Smart Lookup: Try raw ID first, then msg_ prefix for Messenger users
    lookup_id = user_id
    state = await redis_client.get(f"sm:state:{lookup_id}")
    
    if state is None and not lookup_id.startswith("msg_") and not lookup_id.isdigit():
        # Might be a PSID string without prefix
        alt_id = f"msg_{lookup_id}"
        alt_state = await redis_client.get(f"sm:state:{alt_id}")
        if alt_state:
            lookup_id = alt_id
            state = alt_state
    elif state is None and lookup_id.isdigit() and len(lookup_id) > 12:
        # Long digits usually mean PSID
        alt_id = f"msg_{lookup_id}"
        alt_state = await redis_client.get(f"sm:state:{alt_id}")
        if alt_state:
            lookup_id = alt_id
            state = alt_state

    partner = await redis_client.get(f"sm:partner:{lookup_id}")
    start = await redis_client.get(f"sm:chat_start:{lookup_id}")
    
    # Fetch DB Data
    from database.repositories.user_repository import UserRepository
    user_db = await UserRepository.get_by_telegram_id(UserRepository._sanitize_id(lookup_id))
    
    return {
        "user_id": lookup_id,
        "state": state or "HOME",
        "partner_id": partner,
        "chat_start_ts": float(start) if start else None,
        "db": user_db
    }

@app.get("/admin/queue")
async def get_queue(_=Depends(verify_token)):
    if not redis_client: raise HTTPException(status_code=503, detail="Redis unavailable")
    members = await redis_client.lrange("sm:queue", 0, -1)
    
    queue_data = []
    for m in members:
        prefs = await redis_client.hgetall(f"sm:match:pref:{m}")
        queue_data.append({"user_id": m, "prefs": prefs})
        
    return {"queue_length": len(members), "users": queue_data}
    
@app.delete("/admin/queue")
async def clear_queue_api(_=Depends(verify_token)):
    from services.distributed_state import distributed_state
    await distributed_state.clear_queue()
    return {"status": "Queue cleared"}

@app.get("/admin/sessions")
async def get_active_sessions(_=Depends(verify_token)):
    if not redis_client: raise HTTPException(status_code=503, detail="Redis unavailable")
    keys = await redis_client.keys("sm:partner:*")
    sessions = []
    seen = set()
    for k in keys:
        uid = k.split(":")[-1]
        if uid in seen: continue
        
        pid = await redis_client.get(k)
        if pid:
            seen.add(uid)
            seen.add(pid)
            start_val = await redis_client.get(f"sm:chat_start:{uid}")
            sessions.append({
                "user1": uid,
                "user2": pid,
                "start_ts": float(start_val) if start_val else None
            })
    return {"active_sessions": len(sessions), "sessions": sessions}

@app.get("/admin/stats/distribution")
async def get_state_distribution(_=Depends(verify_token)):
    if not redis_client: raise HTTPException(status_code=503, detail="Redis unavailable")
    
    distribution = {}
    cursor = 0
    while True:
        cursor, keys = await redis_client.scan(cursor=cursor, match="sm:state:*", count=1000)
        if keys:
            states = await redis_client.mget(keys)
            for s in states:
                if s: distribution[s] = distribution.get(s, 0) + 1
        if cursor == 0: break
    return {"distribution": distribution}

@app.get("/admin/stats/global")
async def get_global_stats(_=Depends(verify_token)):
    """Fetch global aggregates from the database."""
    try:
        stats = await db.fetchone("""
            SELECT 
                COUNT(*) as total_users,
                SUM(COALESCE(coins, 0)) as total_coins,
                SUM(COALESCE(total_matches, 0)) as total_matches_all_time,
                COUNT(*) FILTER (WHERE vip_status = true) as total_vip
            FROM users
        """)
        return dict(stats) if stats else {}
    except Exception as e:
        return {"error": str(e)}

@app.get("/admin/event_status")
async def get_event_status(_=Depends(verify_token)):
    """Fetches the current active global event status."""
    from services.event_manager import get_active_event
    return {"event": get_active_event()}


@app.get("/health")
async def self_health():
    """Self-health check for the Admin API itself (prevents 404s on Render/load balancers)."""
    return {"status": "ok", "service": "admin_api"}

@app.get("/admin/server_status")
async def get_server_status(_=Depends(verify_token)):
    """Proxies the health status from the main webhook server."""
    from config import PORT
    
    # Check if an explicit bot URL is provided (useful for multi-service deployments)
    bot_url = os.getenv("BOT_SERVER_URL")
    if bot_url:
        try:
            response = await asyncio.to_thread(requests.get, f"{bot_url.rstrip('/')}/health", timeout=5)
            if response.status_code == 200: return response.json()
        except: pass

    # Fallback to local discovery
    ports_to_try = [PORT]
    if PORT == 10000: # If we are on Render's default, the bot might be elsewhere or we might be hitting ourselves
        ports_to_try.extend([8000, 5000])
    
    hosts = ["127.0.0.1", "localhost"]
    last_error = "Bot unreachable"
    
    for p in ports_to_try:
        for host in hosts:
            url = f"http://{host}:{p}/health"
            try:
                response = await asyncio.to_thread(requests.get, url, timeout=2)
                # If we hit ourselves (the admin_api), it will return {"service": "admin_api"}
                # We skip that and keep looking for the bot
                data = response.json()
                if data.get("service") == "admin_api":
                    continue
                    
                if response.status_code == 200:
                    return data
            except Exception as e:
                last_error = str(e)
    
    return {"status": "error", "message": f"Main Server Unreachable (Tried ports {ports_to_try}). {last_error}"}

@app.post("/admin/broadcast")
async def broadcast_message(request: Request, _=Depends(verify_token)):
    """Broadcasts a message to all users via the Engine."""
    data = await request.json()
    text = data.get("text")
    if not text:
        raise HTTPException(status_code=400, detail="Message text required")
    
    if redis_client:
        await redis_client.xadd("admin:commands", {
            "action": "BROADCAST",
            "text": text,
            "timestamp": time.time()
        })
        return {"status": "ok", "message": "Broadcast queued for background dispatch"}
    
    return {"status": "error", "message": "Redis unavailable for command dispatch"}

@app.post("/admin/user/{user_id}/gift")
async def gift_coins(user_id: str, request: Request, _=Depends(verify_token)):
    data = await request.json()
    amount = data.get("amount", 0)
    if not amount:
        raise HTTPException(status_code=400, detail="Amount required")
        
    if redis_client:
        await redis_client.xadd("admin:commands", {
            "action": "GIFT_COINS",
            "user_id": user_id,
            "amount": amount,
            "timestamp": time.time()
        })
        return {"status": "ok", "message": f"Queued gift of {amount} coins to {user_id}"}
    
    return {"status": "error", "message": "Redis unavailable"}

@app.post("/admin/user/{user_id}/ban")
async def ban_user(user_id: str, request: Request, _=Depends(verify_token)):
    data = await request.json()
    banned = data.get("banned", True)
    if redis_client:
        await redis_client.xadd("admin:commands", {
            "action": "BAN_USER",
            "user_id": user_id,
            "banned": banned,
            "timestamp": time.time()
        })
        return {"status": "ok", "message": f"Queued ban status {banned} for {user_id}"}
    return {"status": "error", "message": "Redis unavailable"}

@app.post("/admin/user/{user_id}/vip")
async def set_vip(user_id: str, request: Request, _=Depends(verify_token)):
    data = await request.json()
    vip = data.get("vip", True)
    if redis_client:
        await redis_client.xadd("admin:commands", {
            "action": "SET_VIP",
            "user_id": user_id,
            "vip": vip,
            "timestamp": time.time()
        })
        return {"status": "ok", "message": f"Queued VIP status {vip} for {user_id}"}
    return {"status": "error", "message": "Redis unavailable"}

@app.post("/admin/system/reset")
async def system_reset(_=Depends(verify_token)):
    """Triggers a full system reset via Redis command."""
    if redis_client:
        await redis_client.xadd("admin:commands", {
            "action": "RESET_SYSTEM",
            "timestamp": time.time()
        })
        return {"status": "ok", "message": "System reset command dispatched"}
    return {"status": "error", "message": "Redis unavailable"}


@app.post("/admin/disconnect/{user_id}")
async def force_disconnect(user_id: str, _=Depends(verify_token)):

    if not redis_client: raise HTTPException(status_code=503, detail="Redis unavailable")
    
    lua = """
    local partnerA = redis.call("GET", "sm:partner:" .. ARGV[1])
    if partnerA then
        redis.call("DEL", "sm:partner:" .. ARGV[1])
        redis.call("DEL", "sm:partner:" .. partnerA)
        redis.call("SET", "sm:state:" .. ARGV[1], "HOME")
        redis.call("SET", "sm:state:" .. partnerA, "HOME")
        redis.call("DEL", "sm:chat_start:" .. ARGV[1])
        redis.call("DEL", "sm:chat_start:" .. partnerA)
    else
        redis.call("SET", "sm:state:" .. ARGV[1], "HOME")
    end
    return partnerA
    """
    await redis_client.eval(lua, 0, user_id)
    return {"status": "Force disconnected via Redis. UI will re-sync on next interaction or reconcile loop."}


# --- WebSockets & Frontend ---

@app.websocket("/admin/ws")
async def websocket_endpoint(websocket: WebSocket):
    if not await verify_ws_token(websocket):
        return
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            # Handle incoming commands if needed
    except WebSocketDisconnect:
        manager.disconnect(websocket)


# Mount static assets
os.makedirs("assets/admin", exist_ok=True)
app.mount("/static", StaticFiles(directory="assets/admin"), name="static")

@app.get("/", response_class=HTMLResponse)
async def admin_dashboard():
    with open("assets/admin/index.html", "r", encoding="utf-8") as f:
        return f.read()

if __name__ == "__main__":
    import uvicorn
    # Make sure to run this via `python admin_api.py` or `uvicorn admin_api:app --port 8001`
    uvicorn.run(app, host="0.0.0.0", port=8001)

