let ws = null;
let authToken = "";
let currentInspectUser = null;

// Track active traces for pipeline grouping
const activeTraces = new Map();

function authenticate() {
    authToken = document.getElementById("auth-token").value.trim();
    if (!authToken) return;
    
    document.getElementById("auth-overlay").style.display = "none";
    connectWebSocket();
    fetchStats();
    setInterval(fetchStats, 5000);
}

function connectWebSocket() {
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const wsUrl = `${protocol}//${window.location.host}/admin/ws?token=${encodeURIComponent(authToken)}`;
    
    ws = new WebSocket(wsUrl);
    
    ws.onopen = () => {
        document.getElementById("ws-status").textContent = "🟢 Connected";
        document.getElementById("ws-status").style.color = "var(--success)";
    };
    
    ws.onmessage = (event) => {
        const data = JSON.parse(event.data);
        if (data.type === "event") {
            processEvent(data.payload);
        }
    };
    
    ws.onclose = () => {
        document.getElementById("ws-status").textContent = "🔴 Disconnected";
        document.getElementById("ws-status").style.color = "var(--danger)";
        setTimeout(connectWebSocket, 3000); // Reconnect
    };
}

function processEvent(payload) {
    // 1. Live Timeline / Pipeline View
    renderTimelineEvent(payload);
    
    // 2. Failure Highlight Engine
    if (payload.event === "INVARIANT_VIOLATION" || payload.status === "fail") {
        renderViolation(payload);
    }
    
    // 3. Auto-refresh Inspector if watching this user
    if (currentInspectUser && (payload.user_id == currentInspectUser || payload.peer_id == currentInspectUser)) {
        inspectUser(currentInspectUser);
    }
}

function getTagClass(event) {
    if (event === "ACTION_START") return "tag-start";
    if (event === "ACTION_END") return "tag-end";
    if (event === "REDIS_CALL" || event === "REDIS_RESULT") return "tag-redis";
    if (event === "STATE_CHANGE") return "tag-state";
    if (event === "INVARIANT_VIOLATION") return "tag-violation";
    return "";
}

function renderTimelineEvent(payload) {
    const filterTrace = document.getElementById("filter-trace").value.trim();
    const filterUser = document.getElementById("filter-user").value.trim();
    
    if (filterTrace && payload.trace_id !== filterTrace) return;
    if (filterUser && String(payload.user_id) !== filterUser && String(payload.peer_id) !== filterUser) return;

    const timeline = document.getElementById("timeline");
    const div = document.createElement("div");
    div.className = "log-entry";
    
    let statusClass = "status-success";
    if (payload.status === "fail") statusClass = "status-fail";
    if (payload.status === "warning") statusClass = "status-warning";

    let diffHtml = "";
    if (payload.expected || payload.actual) {
        const isFail = payload.expected && payload.actual && payload.expected !== payload.actual;
        diffHtml = `
            <div class="diff-box ${isFail ? 'fail' : ''}">
                <div><strong>Expected:</strong> ${payload.expected || 'N/A'}</div>
                <div><strong>Actual:</strong> ${payload.actual || 'N/A'}</div>
            </div>
        `;
    }

    if (payload.event === "STATE_CHANGE" && payload.data) {
        diffHtml = `
            <div class="diff-box">
                <div><strong>BEFORE:</strong> state=${payload.data.old_state}</div>
                <div><strong>AFTER:</strong> state=${payload.data.new_state}</div>
            </div>
        `;
    }

    div.innerHTML = `
        <div class="log-meta">
            <span>[${new Date(payload.timestamp * 1000).toLocaleTimeString()}]</span>
            <span class="log-tag ${getTagClass(payload.event)}">${payload.event}</span>
            <span>[${payload.layer}]</span>
            <span class="log-tag" style="background:#444; cursor:pointer;" onclick="setTraceFilter('${payload.trace_id}')">${payload.trace_id.substring(0,8)}</span>
        </div>
        <div>
            User: <strong>${payload.user_id || 'N/A'}</strong> 
            ${payload.peer_id ? `↔ Peer: <strong>${payload.peer_id}</strong>` : ''} 
            | Status: <span class="${statusClass}">${payload.status.toUpperCase()}</span>
        </div>
        ${diffHtml}
        <div style="color:var(--text-muted); font-size: 0.9em; margin-top:4px;">
            ${JSON.stringify(payload.data || {})}
        </div>
    `;

    // Pipeline grouping (simple visual indent for same trace_id if consecutive, else just append)
    timeline.prepend(div);
    if (timeline.children.length > 200) {
        timeline.lastChild.remove();
    }
}

function setTraceFilter(traceId) {
    document.getElementById("filter-trace").value = traceId;
}

function clearTimeline() {
    document.getElementById("timeline").innerHTML = "";
    document.getElementById("filter-trace").value = "";
    document.getElementById("filter-user").value = "";
}

function renderViolation(payload) {
    const list = document.getElementById("violations-list");
    const div = document.createElement("div");
    div.className = "violation-card";
    
    div.innerHTML = `
        <strong>⚠ ${payload.event === 'INVARIANT_VIOLATION' ? 'INCONSISTENCY DETECTED' : 'PIPELINE FAILURE'}</strong><br>
        User: ${payload.user_id || 'N/A'} ${payload.peer_id ? `| Peer: ${payload.peer_id}` : ''}<br>
        Layer: ${payload.layer} <br>
        Details: ${JSON.stringify(payload.data)}
        ${payload.expected ? `<br>Expected: ${payload.expected} | Actual: ${payload.actual}` : ''}
    `;
    
    list.prepend(div);
    if (list.children.length > 20) list.lastChild.remove();
}

async function apiCall(endpoint, method = "GET") {
    const response = await fetch(endpoint, {
        method: method,
        headers: {
            "Authorization": `Bearer ${authToken}`
        }
    });
    if (!response.ok) {
        if (response.status === 401) {
            document.getElementById("auth-error").textContent = "Invalid Token!";
            document.getElementById("auth-overlay").style.display = "flex";
        }
        throw new Error("API Error: " + response.statusText);
    }
    return await response.json();
}

async function fetchStats() {
    try {
        const qData = await apiCall("/admin/queue");
        document.getElementById("stat-queue-len").textContent = qData.queue_length;
        
        const sData = await apiCall("/admin/sessions");
        document.getElementById("stat-active-sessions").textContent = sData.active_sessions;
        
        // Stuck User Detector
        detectStuckUsers(qData.users);
    } catch (e) {
        console.error(e);
    }
}

function detectStuckUsers(queueUsers) {
    const stuckList = document.getElementById("stuck-users-list");
    stuckList.innerHTML = "";
    
    // Very rudimentary check: if we had enqueue timestamps we could check > 45s.
    // For now, if queue is very large, list the first few.
    // Assuming backend added timestamps to pref data in real system.
    if (queueUsers.length > 0) {
        queueUsers.slice(0, 5).forEach(u => {
            const div = document.createElement("div");
            div.textContent = `User ${u.user_id} in queue. Pref: ${u.prefs.pref || 'Any'}`;
            stuckList.appendChild(div);
        });
    } else {
        stuckList.innerHTML = "<div style='color:var(--success)'>No stuck users detected.</div>";
    }
}

async function inspectUser(forceId = null) {
    const id = forceId || document.getElementById("inspect-user-id").value.trim();
    if (!id) return;
    
    currentInspectUser = id;
    try {
        const data = await apiCall(`/admin/user/${id}`);
        document.getElementById("ui-state").textContent = data.state;
        document.getElementById("ui-partner").textContent = data.partner_id || "None";
        document.getElementById("ui-chat-start").textContent = data.chat_start_ts ? new Date(data.chat_start_ts * 1000).toLocaleString() : "N/A";
    } catch (e) {
        document.getElementById("ui-state").textContent = "Error fetching user";
    }
}

async function forceDisconnect() {
    if (!currentInspectUser) return;
    if (confirm(`Force disconnect user ${currentInspectUser}?`)) {
        try {
            await apiCall(`/admin/disconnect/${currentInspectUser}`, "POST");
            alert("Force disconnect command sent via Redis.");
            inspectUser();
        } catch (e) {
            alert(e.message);
        }
    }
}
