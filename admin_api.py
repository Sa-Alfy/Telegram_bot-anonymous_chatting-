import asyncio
import json
import os
from typing import Dict, Any, List
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends, HTTPException, status, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import redis.asyncio as redis_async
import redis.exceptions as redis_exceptions
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(title="Matchmaking Debug Dashboard")

# Security
DEBUG_SECRET = os.getenv("DEBUG_SECRET", "supersecret123")  # In production, require this in env
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
        print("WARNING: REDIS_URL not set in env.")
        return

    redis_client = redis_async.from_url(redis_url, decode_responses=True)
    try:
        await redis_client.ping()
        print("Admin API connected to Redis.")
        # Setup Consumer Group
        try:
            await redis_client.xgroup_create("admin:events", "dashboard", id="0", mkstream=True)
        except redis_exceptions.ResponseError as e:
            if "BUSYGROUP" not in str(e):
                print(f"Error creating consumer group: {e}")
        
        # Start event consumer task
        asyncio.create_task(consume_events())
    except Exception as e:
        print(f"Failed to connect Admin API to Redis: {e}")
        redis_client = None


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

@app.get("/admin/user/{user_id}")
async def get_user_state(user_id: str, _=Depends(verify_token)):
    if not redis_client: raise HTTPException(status_code=503, detail="Redis unavailable")
    state = await redis_client.get(f"sm:state:{user_id}")
    partner = await redis_client.get(f"sm:partner:{user_id}")
    start = await redis_client.get(f"sm:chat_start:{user_id}")
    
    return {
        "user_id": user_id,
        "state": state or "HOME",
        "partner_id": partner,
        "chat_start_ts": float(start) if start else None
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


@app.post("/admin/disconnect/{user_id}")
async def force_disconnect(user_id: str, _=Depends(verify_token)):
    # Very crude fallback injection, ideally we'd send an event to ActionRouter
    # For now, let's just send an END_CHAT event through Redis Streams if we had an ingress stream,
    # or directly wipe it. Direct wiping might desync UI, so we push to a 'commands' stream or use the ActionRouter directly.
    # Because admin runs in a separate process, it cannot directly call MatchmakingService.disconnect()
    # unless we use Redis to signal it.
    # We will simulate a REST call or just use the Redis Lua fallback
    if not redis_client: raise HTTPException(status_code=503, detail="Redis unavailable")
    
    # We will just wipe it in Redis for a hard reset, the bot's reconciler will eventually catch it.
    # Better yet, since we have distributed_state, we can reimplement the lua script here or wait.
    # Actually, the user wants "POST /admin/disconnect/{user_id}".
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

