
let socket = null;
let token = localStorage.getItem("debug_token") || "";

async function authenticate() {
    const input = document.getElementById("auth-token");
    const errorDiv = document.getElementById("auth-error");
    token = input.value.trim();
    
    if (!token) return;
    
    errorDiv.innerText = "Verifying...";
    
    try {
        const res = await fetch("/admin/verify", {
            headers: { "Authorization": `Bearer ${token}` }
        });
        
        if (res.ok) {
            localStorage.setItem("debug_token", token);
            errorDiv.innerText = "";
            connectWS();
        } else {
            errorDiv.innerText = "❌ Invalid Secret Code";
        }
    } catch (e) {
        errorDiv.innerText = "❌ Server Unavailable";
    }
}

async function connectWS() {
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const url = `${protocol}//${window.location.host}/admin/ws?token=${token}`;
    
    socket = new WebSocket(url);
    
    socket.onopen = () => {
        document.getElementById("ws-status").innerText = "🟢 Online";
        document.getElementById("ws-status").className = "connection-status online";
        document.getElementById("auth-overlay").style.display = "none";
        refreshStats();
    };
    
    socket.onclose = () => {
        document.getElementById("ws-status").innerText = "🔴 Disconnected";
        document.getElementById("ws-status").className = "connection-status";
        document.getElementById("auth-overlay").style.display = "flex";
        setTimeout(connectWS, 5000);
    };
    
    socket.onmessage = (event) => {
        const data = JSON.parse(event.data);
        if (data.type === "event") {
            appendTrace(data.payload);
        }
    };
}

function appendTrace(payload) {
    const timeline = document.getElementById("timeline");
    const entry = document.createElement("div");
    
    // Determine status class
    let statusClass = payload.success ? "success" : "error";
    if (payload.event_type === "CMD_START") statusClass = "success";
    if (payload.event_type === "SYSTEM_ERROR") statusClass = "fatal";
    if (payload.event_type === "SYSTEM_WARNING") statusClass = "warning";
    
    entry.className = `trace-entry ${statusClass}`;
    
    const timeStr = new Date().toLocaleTimeString();
    const duration = payload.duration_ms ? `${payload.duration_ms.toFixed(1)}ms` : "??ms";
    
    entry.innerHTML = `
        <div class="trace-header">
            <span>[${timeStr}] <span class="trace-function">${payload.event_type}</span></span>
            <span class="tag">${duration}</span>
        </div>
        <div class="trace-meta">
            <span class="tag">UID: ${payload.user_id}</span>
            <span class="tag">MID: ${payload.match_id || "global"}</span>
            <span class="tag">STATE: ${payload.state || "unknown"}</span>
        </div>
        <div class="trace-payload">${JSON.stringify(payload.payload || {}, null, 2)}</div>
        ${payload.error ? `<div style="color: var(--danger); font-size: 0.75rem; margin-top: 5px;">⚠️ ERROR: ${payload.error}</div>` : ""}
    `;
    
    timeline.prepend(entry);
    
    // Limit log size
    if (timeline.children.length > 200) {
        timeline.removeChild(timeline.lastChild);
    }
}

async function refreshStats() {
    try {
        const qRes = await fetch("/admin/queue", { headers: { "Authorization": `Bearer ${token}` } });
        const sRes = await fetch("/admin/sessions", { headers: { "Authorization": `Bearer ${token}` } });
        
        const queue = await qRes.json();
        const sessions = await sRes.json();
        
        document.getElementById("stat-queue-len").innerText = queue.queue_length || 0;
        document.getElementById("stat-active-sessions").innerText = sessions.active_sessions || 0;
    } catch (e) {
        console.error("Stats refresh failed", e);
    }
    setTimeout(refreshStats, 30000);
}

async function inspectUser() {
    const uid = document.getElementById("inspect-user-id").value;
    if (!uid) return;
    
    try {
        const res = await fetch(`/admin/user/${uid}`, { headers: { "Authorization": `Bearer ${token}` } });
        const data = await res.json();
        
        document.getElementById("ui-state").innerText = data.state;
        document.getElementById("ui-partner").innerText = data.partner_id || "None";
        document.getElementById("ui-chat-start").innerText = data.chat_start_ts ? new Date(data.chat_start_ts * 1000).toLocaleString() : "N/A";
    } catch (e) {
        alert("Failed to inspect user");
    }
}

async function forceDisconnect() {
    const uid = document.getElementById("inspect-user-id").value;
    if (!uid) return;
    
    if (!confirm(`Are you sure you want to force disconnect ${uid}?`)) return;
    
    try {
        await fetch(`/admin/disconnect/${uid}`, { 
            method: "POST",
            headers: { "Authorization": `Bearer ${token}` } 
        });
        alert("Force disconnect sent");
        inspectUser();
    } catch (e) {
        alert("Force disconnect failed");
    }
}

function clearTimeline() {
    document.getElementById("timeline").innerHTML = "";
}

// Initial connection
if (token) {
    connectWS();
}
