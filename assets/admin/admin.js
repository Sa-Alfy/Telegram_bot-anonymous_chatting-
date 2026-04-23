
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
            const payload = data.payload;
            appendTrace(payload);
            
            // Check for violations
            if (payload.event === "INVARIANT_VIOLATION") {
                appendViolation(payload);
            }
        }
    };
}

function appendTrace(payload) {
    const timeline = document.getElementById("timeline");
    const entry = document.createElement("div");
    
    // Determine status class
    let statusClass = payload.success ? "success" : "error";
    const etype = payload.event || payload.event_type || "UNKNOWN";
    
    if (etype === "ACTION_START") statusClass = "success";
    if (etype === "SYSTEM_ERROR" || etype === "INVARIANT_VIOLATION") statusClass = "fatal";
    if (etype === "SYSTEM_WARNING") statusClass = "warning";
    
    entry.className = `trace-entry ${statusClass}`;
    
    const timeStr = new Date().toLocaleTimeString();
    const duration = payload.duration_ms ? `${payload.duration_ms.toFixed(1)}ms` : "??ms";
    
    entry.innerHTML = `
        <div class="trace-header">
            <span>[${timeStr}] <span class="trace-function">${etype}</span></span>
            <span class="tag">${duration}</span>
        </div>
        <div class="trace-meta">
            <span class="tag">UID: ${payload.user_id || "system"}</span>
            <span class="tag">MID: ${payload.match_id || "global"}</span>
            <span class="tag">STATE: ${payload.state || "unknown"}</span>
        </div>
        <div class="trace-payload">${JSON.stringify(payload.data || payload.payload || {}, null, 2)}</div>
        ${payload.error ? `<div style="color: var(--danger); font-size: 0.75rem; margin-top: 5px;">⚠️ ERROR: ${payload.error}</div>` : ""}
    `;
    
    timeline.prepend(entry);
    
    // Limit log size
    if (timeline.children.length > 200) {
        timeline.removeChild(timeline.lastChild);
    }
}

function appendViolation(payload) {
    const list = document.getElementById("violations-list");
    const entry = document.createElement("div");
    entry.className = "violation-entry";
    
    const timeStr = new Date().toLocaleTimeString();
    const data = payload.data || {};
    
    entry.innerHTML = `
        <div class="violation-header">
            <span class="tag danger">🚨 ${data.violation || "INVARIANT_VIOLATION"}</span>
            <span class="time">${timeStr}</span>
        </div>
        <div class="violation-msg">${data.message || "Unknown violation"}</div>
        <div class="violation-meta">User: ${payload.user_id} | Peer: ${payload.peer_id || "None"}</div>
    `;
    
    list.prepend(entry);
}

async function refreshStats() {
    try {
        const headers = { "Authorization": `Bearer ${token}` };
        const [qRes, sRes, dRes, srvRes] = await Promise.all([
            fetch("/admin/queue", { headers }),
            fetch("/admin/sessions", { headers }),
            fetch("/admin/stats/distribution", { headers }),
            fetch("/admin/server_status", { headers }).catch(() => null)
        ]);
        
        const queue = await qRes.json();
        const sessions = await sRes.json();
        const dist = await dRes.json();
        
        document.getElementById("stat-queue-len").innerText = queue.queue_length || 0;
        document.getElementById("stat-active-sessions").innerText = sessions.active_sessions || 0;
        
        updateStuckUsers(queue.users || []);
        renderDistribution(dist.distribution || {});
        
        if (srvRes && srvRes.ok) {
            const srvData = await srvRes.json();
            renderServerStatus(srvData);
        } else {
            renderServerStatus({status: "error"});
        }
    } catch (e) {
        console.error("Stats refresh failed", e);
    }
    setTimeout(refreshStats, 5000); // More frequent updates for debugging
}

function renderServerStatus(data) {
    const setStatus = (id, stateStr) => {
        const el = document.getElementById(id);
        if (!el) return;
        el.innerText = stateStr ? stateStr.toUpperCase() : "UNKNOWN";
        el.className = "tag"; // reset
        if (stateStr === "online" || stateStr === "connected" || stateStr === "running" || stateStr === "ENABLED") {
            el.classList.add("success");
        } else if (stateStr === "error" || stateStr === "disconnected" || stateStr === "stopped") {
            el.classList.add("danger");
        } else {
            el.classList.add("warning");
        }
    };
    
    if (data.status === "error") {
        setStatus("status-bot", "error");
        setStatus("status-telegram", "error");
        setStatus("status-messenger", "error");
        setStatus("status-db", "error");
        setStatus("status-redis", "error");
        return;
    }

    setStatus("status-bot", data.bot_loop);
    setStatus("status-telegram", data.telegram);
    setStatus("status-messenger", data.messenger);
    setStatus("status-db", data.database);
    setStatus("status-redis", data.redis);
}


function renderDistribution(dist) {
    const container = document.getElementById("state-distribution");
    if (!container) return;
    
    if (Object.keys(dist).length === 0) {
        container.innerHTML = '<div class="empty-state">No active users</div>';
        return;
    }
    
    // Sort states by count descending
    const sorted = Object.entries(dist).sort((a, b) => b[1] - a[1]);
    
    container.innerHTML = sorted.map(([state, count]) => `
        <div class="dist-item">
            <span class="dist-label">${state}</span>
            <span class="dist-count">${count}</span>
        </div>
    `).join('');
}

function updateStuckUsers(users) {
    const list = document.getElementById("stuck-users-list");
    if (!users.length) {
        list.innerHTML = '<div class="empty-state">No users in queue</div>';
        return;
    }
    
    list.innerHTML = users.map(u => `
        <div class="warning-item" onclick="document.getElementById('inspect-user-id').value='${u.user_id}'; inspectUser();">
            <div class="warning-header">
                <span class="warning-uid">${u.user_id}</span>
                <span class="tag">${u.prefs.pref || 'Any'}</span>
            </div>
            <div class="warning-meta">Gender: ${u.prefs.gender || 'N/A'}</div>
        </div>
    `).join('');
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

async function clearQueue() {
    if (!confirm("Are you sure you want to CLEAR THE ENTIRE QUEUE?")) return;
    
    try {
        await fetch("/admin/queue", { 
            method: "DELETE",
            headers: { "Authorization": `Bearer ${token}` } 
        });
        alert("Queue cleared");
        refreshStats();
    } catch (e) {
        alert("Clear queue failed");
    }
}

function clearTimeline() {
    document.getElementById("timeline").innerHTML = "";
}

// Initial connection
if (token) {
    connectWS();
}
