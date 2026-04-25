
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
            errorDiv.style.display = "none";
            connectWS();
        } else {
            errorDiv.innerText = "❌ Invalid Secret Code";
            errorDiv.style.display = "block";
        }
    } catch (e) {
        errorDiv.innerText = "❌ Server Unavailable";
        errorDiv.style.display = "block";
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
        fetchRecentEvents();
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
    
    entry.className = `trace-line ${statusClass}`;
    
    const timeStr = new Date().toLocaleTimeString();
    
    entry.innerHTML = `
        <div class="trace-header">
            [${timeStr}] [${etype}] user=${payload.user_id || 'sys'} state=${payload.state || 'unknown'}
        </div>
        <div class="trace-payload">${JSON.stringify(payload.data || payload.payload || {}, null, 1)}</div>
        ${payload.error ? `<div style="color: var(--danger); font-size: 0.75rem; margin-top: 2px;">⚠️ ${payload.error}</div>` : ""}
    `;
    
    timeline.prepend(entry);
    
    // Limit log size
    if (timeline.children.length > 200) {
        timeline.removeChild(timeline.lastChild);
    }
}

async function fetchRecentEvents() {
    try {
        const res = await fetch("/admin/events", {
            headers: { "Authorization": `Bearer ${token}` }
        });
        if (res.ok) {
            const events = await res.json();
            // Clear current timeline first
            document.getElementById("timeline").innerHTML = "";
            // Add them in reverse (oldest first) so prepend works correctly
            events.reverse().forEach(ev => {
                // The API returns fields like 'event_type', 'user_id', etc.
                // map them to the format appendTrace expects
                appendTrace({
                    event: ev.event || ev.event_type,
                    user_id: ev.user_id,
                    state: ev.state,
                    data: ev.data ? JSON.parse(ev.data) : (ev.payload ? JSON.parse(ev.payload) : {}),
                    error: ev.error
                });
            });
        }
    } catch (e) {
        console.error("Failed to fetch recent events:", e);
    }
}

function clearTimeline() {
    document.getElementById("timeline").innerHTML = "";
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
        
        // Helper to prevent HTML 502 errors from crashing the Promise.all
        const safeFetch = async (url) => {
            try {
                const r = await fetch(url, { headers });
                if (!r.ok) return { error: true, status: r.status };
                return await r.json();
            } catch (e) {
                return { error: true, message: String(e) };
            }
        };

        const [dist, queue, sessions, srvData, globalData] = await Promise.all([
            safeFetch('/admin/stats/distribution'),
            safeFetch('/admin/queue'),
            safeFetch('/admin/sessions'),
            safeFetch('/admin/server_status'),
            safeFetch('/admin/stats/global')
        ]);

        renderDistribution(dist.distribution || {});
        renderGlobalStats(globalData.error ? {} : globalData);

        // Queue + sessions
        document.getElementById("stat-queue-len").innerText = queue.queue_length ?? 0;
        document.getElementById("stat-active-sessions").innerText = sessions.active_sessions ?? 0;
        updateStuckUsers(queue.users || []);

        // Server status
        if (srvData.error) {
            renderServerStatus({ status: "error", message: "Network/API failure reaching admin server" });
        } else {
            renderServerStatus(srvData);
        }

    } catch (e) {
        console.error("Stats refresh failed catastrophically", e);
    }
    setTimeout(refreshStats, 5000);
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
        const errEl = document.getElementById("server-error-msg");
        if (errEl) {
            let msg = data.message || "Unknown error";
            if (msg.includes("timeout") || msg.includes("404")) {
                msg += " | 💡 Hint: The bot might be sleeping or deploying. Try refreshing in 30s.";
            }
            errEl.innerText = msg;
        }
        return;
    }
    const errEl = document.getElementById("server-error-msg");
    if (errEl) errEl.innerText = "";

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
        <div style="display: flex; justify-content: space-between; border-bottom: 1px solid var(--border); padding: 4px 0;">
            <span style="color: var(--text-dim);">${state}</span>
            <span style="font-weight: bold;">${count}</span>
        </div>
    `).join('');
}

function renderGlobalStats(data) {
    const el = document.getElementById("global-stats");
    if (!el) return;
    
    el.innerHTML = `
        <div class="stat-grid">
            <div class="stat-card">
                <div class="stat-label">Total Users</div>
                <div class="stat-value">${data.total_users || 0}</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Total Coins</div>
                <div class="stat-value">${data.total_coins || 0}</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Total Matches</div>
                <div class="stat-value">${data.total_matches_all_time || 0}</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">VIP Users</div>
                <div class="stat-value">${data.total_vip || 0}</div>
            </div>
        </div>
    `;
}

function updateStuckUsers(users) {
    const list = document.getElementById("stuck-users-list");
    if (!users.length) {
        list.innerHTML = '<div class="empty-state">No users in queue</div>';
        return;
    }
    
    list.innerHTML = users.map(u => `
        <div class="list-item" style="padding: 8px; font-size: 0.75rem; border-bottom: 1px solid var(--border);" onclick="document.getElementById('inspect-user-id').value='${u.user_id}'; inspectUser();">
            <span>${u.user_id}</span>
            <span class="tag warning">${u.prefs.pref || 'Any'}</span>
        </div>
    `).join('');
}

async function inspectUser() {
    const uid = document.getElementById("inspect-user-id").value.trim();
    if (!uid) return;

    try {
        const res = await fetch(`/admin/user/${uid}`, { headers: { "Authorization": `Bearer ${token}` } });
        const data = await res.json();

        document.getElementById("ui-state").innerText = data.state;
        document.getElementById("ui-partner").innerText = data.partner_id || "None";
        document.getElementById("ui-chat-start").innerText = data.chat_start_ts
            ? new Date(data.chat_start_ts * 1000).toLocaleString() : "N/A";

        const dbInfo = document.getElementById("ui-db-info");
        if (data.db && !data.db_error) {
            dbInfo.innerHTML = `
                <div style="margin-top: 10px; padding-top: 10px; border-top: 1px dashed var(--border); font-size: 0.8rem;">
                    <strong>DB PROFILE</strong>
                    <span style="font-size:0.7rem; color:var(--text-dim); margin-left:6px;">id: ${data.db_id_used ?? '?'}</span><br>
                    Coins: ${data.db?.coins ?? 0} | Karma: ${data.db?.karma ?? 0} | Level: ${data.db?.level ?? 1}<br>
                    Gender: ${data.db?.gender ?? 'Unknown'} | Location: ${data.db?.location ?? 'Unknown'}<br>
                    VIP: ${data.db?.vip_status ? '🌟 YES' : 'NO'}<br>
                    <div style="margin-top: 5px; color: var(--text-dim); font-style: italic;">
                        Bio: ${data.db?.bio ?? 'No bio'}
                    </div>
                </div>
            `;
        } else {
            // Show the actual error so admin can diagnose the problem
            const errMsg = data.db_error || 'User not found in DB';
            dbInfo.innerHTML = `
                <div style="margin-top:10px; padding-top:10px; border-top:1px dashed var(--border); font-size:0.8rem;">
                    <span class="tag danger">⚠️ DB Miss</span>
                    <div style="margin-top:6px; font-family:'JetBrains Mono'; font-size:0.72rem; color:var(--danger); word-break:break-all;">${errMsg}</div>
                    <div style="margin-top:4px; color:var(--text-dim); font-size:0.72rem;">Lookup ID tried: ${data.db_id_used ?? 'none'}</div>
                </div>
            `;
        }
    } catch (e) {
        alert("Failed to inspect user: " + e);
    }
}


async function forceDisconnect() {
    const uid = document.getElementById("inspect-user-id").value.trim();
    if (!uid) return;
    
    if (!confirm(`Are you sure you want to force disconnect ${uid}?`)) return;
    
    try {
        const res = await fetch(`/admin/disconnect/${uid}`, { 
            method: "POST",
            headers: { "Authorization": `Bearer ${token}` } 
        });
        if (res.ok) alert("Force disconnect sent");
        else alert("Failed: " + (await res.text()));
        inspectUser();
    } catch (e) {
        alert("Force disconnect failed");
    }
}

async function giftCoins() {
    const uid = document.getElementById("inspect-user-id").value.trim();
    const amount = document.getElementById("gift-amount").value.trim();
    if (!uid || !amount) return;
    
    try {
        const res = await fetch(`/admin/user/${uid}/gift`, {
            method: "POST",
            headers: { 
                "Authorization": `Bearer ${token}`,
                "Content-Type": "application/json"
            },
            body: JSON.stringify({ amount: parseInt(amount) })
        });
        if (res.ok) alert(`Successfully gifted ${amount} coins to ${uid}`);
        else alert("Failed to gift coins");
    } catch (e) {
        alert("Gift failed");
    }
}

async function toggleBan() {
    const uid = document.getElementById("inspect-user-id").value.trim();
    if (!uid) return;
    const isBan = confirm(`Manage User ${uid}:\nClick OK to BAN, Cancel to UNBAN`);
    
    try {
        const res = await fetch(`/admin/user/${uid}/ban`, {
            method: "POST",
            headers: { 
                "Authorization": `Bearer ${token}`,
                "Content-Type": "application/json"
            },
            body: JSON.stringify({ banned: isBan })
        });
        if (res.ok) alert(`User ${uid} ${isBan ? 'BANNED' : 'UNBANNED'}`);
        else alert("Action failed");
    } catch (e) {
        alert("Ban toggle failed");
    }
}

async function toggleVIP() {
    const uid = document.getElementById("inspect-user-id").value.trim();
    if (!uid) return;
    const isVIP = confirm(`Manage User ${uid}:\nClick OK to Grant VIP, Cancel to Remove VIP`);
    
    try {
        const res = await fetch(`/admin/user/${uid}/vip`, {
            method: "POST",
            headers: { 
                "Authorization": `Bearer ${token}`,
                "Content-Type": "application/json"
            },
            body: JSON.stringify({ vip: isVIP })
        });
        if (res.ok) alert(`User ${uid} VIP: ${isVIP}`);
        else alert("Action failed");
    } catch (e) {
        alert("VIP toggle failed");
    }
}

async function sendBroadcast() {
    const text = document.getElementById("broadcast-text").value.trim();
    if (!text) return;
    
    if (!confirm(`Are you sure you want to broadcast this message to ALL users?\n\n"${text.substring(0, 50)}..."`)) return;
    
    try {
        const res = await fetch("/admin/broadcast", {
            method: "POST",
            headers: { 
                "Authorization": `Bearer ${token}`,
                "Content-Type": "application/json"
            },
            body: JSON.stringify({ text })
        });
        if (res.ok) {
            alert("Broadcast queued successfully!");
            document.getElementById("broadcast-text").value = "";
        } else {
            alert("Broadcast failed");
        }
    } catch (e) {
        alert("Network error during broadcast");
    }
}

async function resetSystem() {
    if (!confirm("🚨 WARNING: This will clear ALL active chats and the waiting queue!\nProceed with FULL SYSTEM RESET?")) return;
    
    try {
        const res = await fetch("/admin/system/reset", {
            method: "POST",
            headers: { "Authorization": `Bearer ${token}` }
        });
        if (res.ok) alert("System reset command dispatched.");
        else alert("Reset failed");
    } catch (e) {
        alert("Network error during reset");
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
