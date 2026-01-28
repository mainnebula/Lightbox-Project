/**
 * Lightbox Web GUI — Client-side application
 *
 * Vanilla JS single-page application for browsing sessions,
 * viewing event timelines, real-time updates via SSE, and
 * integrity verification.
 */

// === State ===
let currentSessionId = null;
let allEvents = [];
let filteredEvents = [];
let eventSource = null;
let liveMode = false;
let autoRefreshTimer = null;

// === Initialization ===
document.addEventListener('DOMContentLoaded', () => {
    loadSessions();
    startAutoRefresh();
});

// === Session List ===

function startAutoRefresh() {
    if (autoRefreshTimer) clearInterval(autoRefreshTimer);
    autoRefreshTimer = setInterval(() => {
        if (!currentSessionId) {
            loadSessions();
        }
    }, 5000);
}

async function loadSessions() {
    const loading = document.getElementById('sessions-loading');
    const table = document.getElementById('sessions-table');
    const empty = document.getElementById('sessions-empty');

    loading.classList.remove('hidden');
    table.classList.add('hidden');
    empty.classList.add('hidden');

    try {
        const res = await fetch('/api/sessions');
        const sessions = await res.json();

        loading.classList.add('hidden');

        if (sessions.length === 0) {
            empty.classList.remove('hidden');
            return;
        }

        table.classList.remove('hidden');
        const tbody = document.getElementById('sessions-tbody');
        tbody.innerHTML = '';

        for (const s of sessions) {
            const tr = document.createElement('tr');
            tr.onclick = () => showSessionDetail(s.session_id);

            const tools = (s.tools_used || []).slice(0, 3).join(', ');
            const toolsMore = (s.tools_used || []).length > 3 ? ', ...' : '';
            const time = s.first_event ? formatTime(s.first_event) : 'N/A';

            let statusBadge = '<span class="verify-badge unknown">--</span>';
            if (s.has_truncation) {
                statusBadge = '<span class="verify-badge truncated">Truncated</span>';
            } else if (s.has_errors) {
                statusBadge = '<span class="verify-badge parse-error">Parse Error</span>';
            }

            tr.innerHTML = `
                <td><span class="session-id">${escapeHtml(s.session_id)}</span></td>
                <td><span class="event-count">${s.event_count}</span></td>
                <td><span class="tools-list">${escapeHtml(tools + toolsMore)}</span></td>
                <td><span class="time-range">${escapeHtml(time)}</span></td>
                <td>${statusBadge}</td>
            `;
            tbody.appendChild(tr);
        }
    } catch (err) {
        loading.classList.add('hidden');
        empty.classList.remove('hidden');
        empty.querySelector('p').textContent = 'Error loading sessions: ' + err.message;
    }
}

// === Session Detail ===

async function showSessionDetail(sessionId) {
    currentSessionId = sessionId;

    document.getElementById('session-list-view').classList.add('hidden');
    document.getElementById('session-detail-view').classList.remove('hidden');
    document.getElementById('detail-session-id').textContent = sessionId;
    document.getElementById('verify-result').classList.add('hidden');
    document.getElementById('filter-tool').value = '';
    document.getElementById('filter-status').value = '';

    await loadEvents(sessionId);
}

function showSessionList() {
    currentSessionId = null;
    allEvents = [];
    filteredEvents = [];
    disconnectSSE();

    document.getElementById('session-list-view').classList.remove('hidden');
    document.getElementById('session-detail-view').classList.add('hidden');

    // Update live button state
    liveMode = false;
    document.getElementById('live-btn').classList.remove('active');
    document.getElementById('connection-status').classList.add('hidden');

    loadSessions();
}

async function loadEvents(sessionId) {
    const loading = document.getElementById('events-loading');
    const timeline = document.getElementById('event-timeline');
    const empty = document.getElementById('events-empty');

    loading.classList.remove('hidden');
    timeline.innerHTML = '';
    empty.classList.add('hidden');

    try {
        const res = await fetch(`/api/sessions/${sessionId}`);
        const data = await res.json();

        loading.classList.add('hidden');
        allEvents = data.events || [];

        if (allEvents.length === 0) {
            empty.classList.remove('hidden');
            return;
        }

        applyFilters();
    } catch (err) {
        loading.classList.add('hidden');
        empty.classList.remove('hidden');
        empty.querySelector('p').textContent = 'Error loading events: ' + err.message;
    }
}

// === Filtering ===

function applyFilters() {
    const toolFilter = document.getElementById('filter-tool').value.toLowerCase();
    const statusFilter = document.getElementById('filter-status').value;

    filteredEvents = allEvents.filter(e => {
        if (toolFilter && !e.tool.toLowerCase().includes(toolFilter)) return false;
        if (statusFilter && e.status !== statusFilter) return false;
        return true;
    });

    renderTimeline(filteredEvents);
}

// === Timeline Rendering ===

function renderTimeline(events) {
    const timeline = document.getElementById('event-timeline');
    const empty = document.getElementById('events-empty');

    if (events.length === 0) {
        timeline.innerHTML = '';
        empty.classList.remove('hidden');
        return;
    }

    empty.classList.add('hidden');
    timeline.innerHTML = '';

    for (const event of events) {
        timeline.appendChild(createEventCard(event));
    }
}

function createEventCard(event, isNew) {
    const card = document.createElement('div');
    card.className = `event-card status-${event.status}`;
    if (isNew) card.classList.add('new-event');
    card.dataset.invocationId = event.invocation_id;

    const statusIcon = getStatusIcon(event.status);
    const duration = formatDuration(event.timestamp_start, event.timestamp_end);
    const shortHash = event.hash ? event.hash.substring(0, 8) : '';
    const prevHash = event.prev_hash ? event.prev_hash.substring(0, 8) : 'genesis';

    card.innerHTML = `
        <div class="event-header" onclick="toggleEventDetail(this)">
            <span class="event-status-icon ${event.status}">${statusIcon}</span>
            <span class="event-inv-id">${escapeHtml(event.invocation_id)}</span>
            <span class="event-tool">${escapeHtml(event.tool)}</span>
            <span class="event-duration">${escapeHtml(duration)}</span>
            <span class="event-hash">${escapeHtml(shortHash)}</span>
        </div>
        <div class="event-detail">
            ${renderEventDetail(event)}
            <div class="hash-chain">
                <span class="hash-value">${escapeHtml(prevHash)}</span>
                <span class="arrow">&rarr;</span>
                <span class="hash-value current">${escapeHtml(shortHash)}</span>
            </div>
        </div>
    `;

    return card;
}

function renderEventDetail(event) {
    let html = '';

    // Input
    if (event.input && Object.keys(event.input).length > 0) {
        html += `
            <div class="detail-section">
                <div class="detail-label">Input</div>
                <div class="detail-content">${escapeHtml(JSON.stringify(event.input, null, 2))}</div>
            </div>
        `;
    }

    // Canonical output
    if (event.canonical_output !== undefined && event.canonical_output !== null) {
        html += `
            <div class="detail-section">
                <div class="detail-label">Value</div>
                <div class="detail-content canonical-content">${escapeHtml(JSON.stringify(event.canonical_output, null, 2))}</div>
            </div>
        `;
    }

    // Output
    if (event.output && Object.keys(event.output).length > 0) {
        const label = event.canonical_output !== undefined && event.canonical_output !== null
            ? 'Raw Output' : 'Output';
        html += `
            <div class="detail-section">
                <div class="detail-label">${label}</div>
                <div class="detail-content">${escapeHtml(JSON.stringify(event.output, null, 2))}</div>
            </div>
        `;
    }

    // Error
    if (event.error) {
        html += `
            <div class="detail-section">
                <div class="detail-label">Error</div>
                <div class="detail-content error-content">${escapeHtml(JSON.stringify(event.error, null, 2))}</div>
            </div>
        `;
    }

    // Metadata
    const metaItems = [];
    if (event.actor) metaItems.push(`Actor: ${event.actor}`);
    if (event.originating_actor) metaItems.push(`Originating: ${event.originating_actor}`);
    if (event.parent_invocation) metaItems.push(`Parent: ${event.parent_invocation}`);
    if (event.retry_of) metaItems.push(`Retry of: ${event.retry_of}`);
    if (event.timestamp_start) metaItems.push(`Start: ${event.timestamp_start}`);
    if (event.timestamp_end) metaItems.push(`End: ${event.timestamp_end}`);

    if (metaItems.length > 0) {
        html += `
            <div class="detail-section">
                <div class="detail-label">Metadata</div>
                <div class="detail-content">${escapeHtml(metaItems.join('\n'))}</div>
            </div>
        `;
    }

    return html;
}

function toggleEventDetail(headerEl) {
    const card = headerEl.closest('.event-card');
    card.classList.toggle('expanded');
}

// === Verification ===

async function verifySession() {
    if (!currentSessionId) return;

    const resultDiv = document.getElementById('verify-result');
    const btn = document.getElementById('verify-btn');

    btn.disabled = true;
    btn.innerHTML = '<span class="verify-spinner"></span>Verifying...';
    resultDiv.classList.remove('hidden', 'valid', 'tampered', 'truncated', 'parse-error');

    try {
        const res = await fetch(`/api/sessions/${currentSessionId}/verify`, { method: 'POST' });
        const data = await res.json();

        const status = data.status.toLowerCase();
        resultDiv.classList.add(status === 'parse_error' ? 'parse-error' : status);

        if (data.valid) {
            resultDiv.innerHTML = `
                <span class="verify-icon">&#10003;</span>
                All ${data.event_count} events verified
                <div class="verify-details">Hash chain intact. No tampering detected.</div>
            `;
        } else if (status === 'tampered') {
            resultDiv.innerHTML = `
                <span class="verify-icon">&#10007;</span>
                TAMPERING DETECTED
                <div class="verify-details">
                    ${escapeHtml(data.error_message || '')}
                    ${data.error_index !== null ? `<br>Event index: ${data.error_index}` : ''}
                    ${data.expected_hash ? `<br>Expected: ${data.expected_hash.substring(0, 16)}...` : ''}
                    ${data.actual_hash ? `<br>Actual: ${data.actual_hash.substring(0, 16)}...` : ''}
                </div>
            `;
            // Highlight tampered event
            if (data.error_index !== null) {
                highlightTamperedEvent(data.error_index);
            }
        } else if (status === 'truncated') {
            resultDiv.innerHTML = `
                <span class="verify-icon">&#9888;</span>
                Truncation detected (${data.event_count} complete events)
                <div class="verify-details">
                    ${escapeHtml(data.error_message || '')}
                    <br>This may indicate a crash during write.
                </div>
            `;
        } else if (status === 'parse_error') {
            resultDiv.innerHTML = `
                <span class="verify-icon">&#9888;</span>
                Parse error
                <div class="verify-details">${escapeHtml(data.error_message || '')}</div>
            `;
        }

        resultDiv.classList.remove('hidden');
    } catch (err) {
        resultDiv.classList.add('parse-error');
        resultDiv.innerHTML = `<span class="verify-icon">&#9888;</span> Verification failed: ${escapeHtml(err.message)}`;
        resultDiv.classList.remove('hidden');
    } finally {
        btn.disabled = false;
        btn.textContent = 'Verify';
    }
}

function highlightTamperedEvent(index) {
    const cards = document.querySelectorAll('.event-card');
    if (index < cards.length) {
        cards[index].classList.add('tampered');
        cards[index].scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
}

// === Live / SSE ===

function toggleLive() {
    if (liveMode) {
        disconnectSSE();
        liveMode = false;
        document.getElementById('live-btn').classList.remove('active');
        document.getElementById('connection-status').classList.add('hidden');
    } else {
        connectSSE();
        liveMode = true;
        document.getElementById('live-btn').classList.add('active');
    }
}

function connectSSE() {
    if (!currentSessionId) return;
    disconnectSSE();

    const statusBar = document.getElementById('connection-status');
    const statusDot = statusBar.querySelector('.status-dot');
    const statusText = statusBar.querySelector('.status-text');

    statusBar.classList.remove('hidden', 'disconnected');
    statusBar.classList.add('connected');
    statusDot.classList.add('pulse');
    statusText.textContent = 'Live';

    eventSource = new EventSource(`/api/sessions/${currentSessionId}/stream`);

    eventSource.onmessage = (e) => {
        try {
            const data = JSON.parse(e.data);
            if (data.type === 'event') {
                allEvents.push(data.event);
                // Apply filters and append if passes
                const toolFilter = document.getElementById('filter-tool').value.toLowerCase();
                const statusFilter = document.getElementById('filter-status').value;

                let passes = true;
                if (toolFilter && !data.event.tool.toLowerCase().includes(toolFilter)) passes = false;
                if (statusFilter && data.event.status !== statusFilter) passes = false;

                if (passes) {
                    filteredEvents.push(data.event);
                    const timeline = document.getElementById('event-timeline');
                    timeline.appendChild(createEventCard(data.event, true));
                    // Auto-scroll
                    const card = timeline.lastElementChild;
                    card.scrollIntoView({ behavior: 'smooth', block: 'end' });
                }
            }
        } catch (err) {
            // Ignore parse errors in SSE
        }
    };

    eventSource.onerror = () => {
        statusBar.classList.remove('connected');
        statusBar.classList.add('disconnected');
        statusDot.classList.remove('pulse');
        statusText.textContent = 'Disconnected';
    };
}

function disconnectSSE() {
    if (eventSource) {
        eventSource.close();
        eventSource = null;
    }
}

// === Utilities ===

function getStatusIcon(status) {
    switch (status) {
        case 'complete': return '&#10003;';
        case 'error': return '&#10007;';
        case 'pending': return '&#9676;';
        default: return '?';
    }
}

function formatDuration(start, end) {
    if (!end) return 'pending';
    try {
        const startMs = new Date(start).getTime();
        const endMs = new Date(end).getTime();
        const ms = endMs - startMs;
        if (ms < 1000) return ms + 'ms';
        if (ms < 60000) return (ms / 1000).toFixed(1) + 's';
        return (ms / 60000).toFixed(1) + 'm';
    } catch {
        return '?';
    }
}

function formatTime(isoStr) {
    try {
        const d = new Date(isoStr);
        return d.toLocaleString();
    } catch {
        return isoStr;
    }
}

function escapeHtml(str) {
    if (str === null || str === undefined) return '';
    const s = String(str);
    const div = document.createElement('div');
    div.textContent = s;
    return div.innerHTML;
}
