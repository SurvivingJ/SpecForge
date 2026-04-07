// IdeaForge Frontend

let projectId = null;
let currentRound = 0;
let currentDepth = 'medium';
let totalRounds = 4;
let eventSource = null;
let wikiData = {};
let activeTab = null;
let pollInterval = null;

// ─── Idea Submission ───

document.getElementById('submit-idea').addEventListener('click', async () => {
    const idea = document.getElementById('idea-input').value.trim();
    const depthEl = document.querySelector('input[name="depth"]:checked');
    if (!idea) return alert('Please enter an idea.');
    currentDepth = depthEl ? depthEl.value : 'medium';

    const depthRounds = { shallow: 2, medium: 4, deep: 6, abyss: -1 };
    totalRounds = depthRounds[currentDepth];

    const res = await fetch('/api/projects', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ idea_description: idea, depth: currentDepth }),
    });
    const data = await res.json();
    projectId = data.project_id;

    // Store in localStorage for session recovery
    localStorage.setItem('ideaforge_project_id', projectId);
    localStorage.setItem('ideaforge_idea', idea);
    localStorage.setItem('ideaforge_depth', currentDepth);

    // Switch to workspace view
    document.getElementById('idea-form').classList.add('hidden');
    document.getElementById('workspace').classList.remove('hidden');

    // Set idea summary
    document.querySelector('.idea-summary-content').textContent = idea;
    document.getElementById('depth-indicator').textContent = currentDepth.charAt(0).toUpperCase() + currentDepth.slice(1);

    // Connect SSE
    connectSSE();

    // Poll for questions
    pollForQuestions();
});

// ─── SSE Activity Feed ───

function connectSSE() {
    if (eventSource) eventSource.close();
    eventSource = new EventSource(`/api/projects/${projectId}/status`);
    eventSource.onmessage = (event) => {
        const data = JSON.parse(event.data);
        addActivityEntry(data.agent, data.message, data.timestamp);
    };
}

function addActivityEntry(agent, message, timestamp) {
    const log = document.getElementById('activity-log');
    const entry = document.createElement('div');
    entry.className = 'activity-entry';
    const time = timestamp ? new Date(timestamp).toLocaleTimeString() : '';
    entry.innerHTML = `<span class="agent-name">${agent}:</span> <span class="message">${message}</span><span class="timestamp">${time}</span>`;
    log.appendChild(entry);
    log.scrollTop = log.scrollHeight;
}

// ─── Question Polling ───

function pollForQuestions() {
    if (pollInterval) clearInterval(pollInterval);
    pollInterval = setInterval(async () => {
        const res = await fetch(`/api/projects/${projectId}/questions`);
        const data = await res.json();

        if (data.status === 'questions_ready') {
            clearInterval(pollInterval);
            renderQuestions(data.questions, data.round);
        } else if (data.status === 'complete') {
            clearInterval(pollInterval);
            showFinalWiki();
        }
    }, 2000);
}

// ─── Question Rendering ───

function renderQuestions(questions, round) {
    currentRound = round;
    document.getElementById('round-badge').textContent = `Round ${round}`;

    // Update progress
    if (totalRounds > 0) {
        const pct = Math.min(100, Math.round((round / totalRounds) * 100));
        document.getElementById('progress-fill').style.width = pct + '%';
    }

    document.getElementById('loading-questions').classList.add('hidden');
    const list = document.getElementById('questions-list');
    list.classList.remove('hidden');
    list.innerHTML = '';

    questions.forEach((q) => {
        const card = document.createElement('div');
        card.className = 'question-card';
        card.dataset.questionId = q.id;

        let inputHtml = '';
        if (q.type === 'multiple_choice' && q.options) {
            const radios = q.options.map((opt, i) => {
                const isOther = opt.toLowerCase() === 'other';
                return `<label>
                    <input type="radio" name="q_${q.id}" value="${opt}" data-is-other="${isOther}">
                    ${opt}
                </label>`;
            }).join('');
            inputHtml = `<div class="radio-group">${radios}</div>
                <textarea class="other-textarea" data-for="${q.id}" placeholder="Please specify..." rows="2"></textarea>`;
        } else {
            inputHtml = `<textarea data-for="${q.id}" placeholder="Your answer..." rows="3"></textarea>`;
        }

        card.innerHTML = `
            <div class="question-header">
                <span class="question-text">${q.text}</span>
                <span class="question-agent">${q.agent}</span>
                <button class="break-down-btn" onclick="breakDown('${q.id}')">Split</button>
            </div>
            ${inputHtml}
        `;
        list.appendChild(card);
    });

    // Wire up "Other" radio listeners
    list.querySelectorAll('input[type="radio"]').forEach((radio) => {
        radio.addEventListener('change', (e) => {
            const card = e.target.closest('.question-card');
            const otherTA = card.querySelector('.other-textarea');
            if (e.target.dataset.isOther === 'true') {
                otherTA.classList.add('visible');
            } else {
                otherTA.classList.remove('visible');
            }
        });
    });

    // Show action buttons
    const actions = document.getElementById('action-buttons');
    actions.classList.remove('hidden');

    // Enable finalise from round 2
    const finalBtn = document.getElementById('finalise-btn');
    finalBtn.disabled = currentRound < 2;
}

// ─── Answer Submission ───

document.getElementById('submit-answers').addEventListener('click', async () => {
    const cards = document.querySelectorAll('.question-card');
    const answers = [];

    cards.forEach((card) => {
        const qId = card.dataset.questionId;
        const radio = card.querySelector('input[type="radio"]:checked');
        const textarea = card.querySelector(`textarea[data-for="${qId}"]`);
        const otherTA = card.querySelector('.other-textarea');

        let answer = '';
        if (radio) {
            if (radio.dataset.isOther === 'true' && otherTA) {
                answer = otherTA.value.trim() || 'Other';
            } else {
                answer = radio.value;
            }
        } else if (textarea) {
            answer = textarea.value.trim();
        }

        answers.push({ question_id: qId, answer: answer });
    });

    // Show loading
    document.getElementById('questions-list').classList.add('hidden');
    document.getElementById('loading-questions').classList.remove('hidden');
    document.getElementById('loading-questions').querySelector('p').textContent = 'Processing your answers...';
    document.getElementById('action-buttons').classList.add('hidden');

    await fetch(`/api/projects/${projectId}/answers`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ answers }),
    });

    pollForQuestions();
});

// ─── Finalise ───

document.getElementById('finalise-btn').addEventListener('click', async () => {
    await fetch(`/api/projects/${projectId}/finalise`, { method: 'POST' });
    document.getElementById('questions-list').classList.add('hidden');
    document.getElementById('loading-questions').classList.remove('hidden');
    document.getElementById('loading-questions').querySelector('p').textContent = 'Finalising specification...';
    document.getElementById('action-buttons').classList.add('hidden');

    // Poll until complete
    const checkComplete = setInterval(async () => {
        const res = await fetch(`/api/projects/${projectId}/questions`);
        const data = await res.json();
        if (data.status === 'complete') {
            clearInterval(checkComplete);
            showFinalWiki();
        }
    }, 2000);
});

// ─── Wiki Renderer ───

async function showFinalWiki() {
    const res = await fetch(`/api/projects/${projectId}/wiki`);
    const data = await res.json();
    wikiData = data.files || {};

    // Hide activity/query panels, show wiki
    document.getElementById('right-panel-toggle').classList.add('hidden');
    document.getElementById('activity-panel').classList.add('hidden');
    document.getElementById('query-panel').classList.add('hidden');
    document.getElementById('wiki-panel').classList.remove('hidden');

    // Build tabs
    const tabsContainer = document.getElementById('wiki-tabs');
    tabsContainer.innerHTML = '';
    const files = Object.keys(wikiData);
    files.forEach((f, i) => {
        const btn = document.createElement('button');
        btn.className = 'wiki-tab' + (i === 0 ? ' active' : '');
        btn.textContent = f.replace('.md', '');
        btn.addEventListener('click', () => switchTab(f));
        tabsContainer.appendChild(btn);
    });

    if (files.length > 0) {
        switchTab(files[0]);
    }

    // Update left panel
    document.getElementById('loading-questions').classList.add('hidden');
    const list = document.getElementById('questions-list');
    list.classList.remove('hidden');
    list.innerHTML = '<div class="loading"><p>Specification complete! Browse the wiki on the right.</p></div>';

    // Set up respec listener
    setupRespec();
}

function switchTab(filename) {
    activeTab = filename;
    const content = wikiData[filename] || '';
    document.getElementById('wiki-content').innerHTML = marked.parse(content);

    // Update active tab styling
    document.querySelectorAll('.wiki-tab').forEach((t) => {
        t.classList.toggle('active', t.textContent === filename.replace('.md', ''));
    });
}

// ─── Respec Flow ───

let respecTooltip = null;

function setupRespec() {
    const wikiContent = document.getElementById('wiki-content');

    wikiContent.addEventListener('mouseup', () => {
        const selection = window.getSelection();
        const text = selection.toString().trim();

        // Remove existing tooltip
        if (respecTooltip) {
            respecTooltip.remove();
            respecTooltip = null;
        }

        if (text.length < 5) return;

        const range = selection.getRangeAt(0);
        const rect = range.getBoundingClientRect();

        respecTooltip = document.createElement('div');
        respecTooltip.className = 'respec-tooltip';
        respecTooltip.textContent = 'Respec this section';
        respecTooltip.style.top = (rect.top - 40 + window.scrollY) + 'px';
        respecTooltip.style.left = (rect.left + rect.width / 2 - 60) + 'px';

        respecTooltip.addEventListener('click', () => {
            openRespecModal(text);
            respecTooltip.remove();
            respecTooltip = null;
        });

        document.body.appendChild(respecTooltip);
    });

    // Close tooltip on click elsewhere
    document.addEventListener('mousedown', (e) => {
        if (respecTooltip && !respecTooltip.contains(e.target)) {
            respecTooltip.remove();
            respecTooltip = null;
        }
    });
}

function openRespecModal(selectedText) {
    const modal = document.getElementById('respec-modal');
    document.getElementById('respec-selection').textContent = `"${selectedText.substring(0, 200)}${selectedText.length > 200 ? '...' : ''}"`;
    document.getElementById('respec-instruction').value = '';
    modal.classList.remove('hidden');
}

document.getElementById('respec-cancel').addEventListener('click', () => {
    document.getElementById('respec-modal').classList.add('hidden');
});

document.getElementById('respec-submit').addEventListener('click', async () => {
    const selectedText = document.getElementById('respec-selection').textContent.slice(1, -1); // Remove quotes
    const instruction = document.getElementById('respec-instruction').value.trim();
    if (!instruction) return;

    document.getElementById('respec-modal').classList.add('hidden');

    // Add shimmer to wiki content
    const wikiContent = document.getElementById('wiki-content');
    wikiContent.classList.add('shimmer');

    const res = await fetch(`/api/projects/${projectId}/respec`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            file: activeTab,
            selected_text: selectedText,
            instruction: instruction,
        }),
    });

    const data = await res.json();
    if (data.updated_content) {
        wikiData[activeTab] = data.updated_content;
        wikiContent.innerHTML = marked.parse(data.updated_content);
    }

    wikiContent.classList.remove('shimmer');
});

// ─── Wiki Query ───

document.querySelectorAll('.toggle-btn').forEach((btn) => {
    btn.addEventListener('click', () => {
        document.querySelectorAll('.toggle-btn').forEach((b) => b.classList.remove('active'));
        btn.classList.add('active');

        const panel = btn.dataset.panel;
        document.getElementById('activity-panel').classList.toggle('hidden', panel !== 'activity');
        document.getElementById('query-panel').classList.toggle('hidden', panel !== 'query');
    });
});

document.getElementById('query-submit').addEventListener('click', submitQuery);
document.getElementById('query-input').addEventListener('keydown', (e) => {
    if (e.key === 'Enter') submitQuery();
});

async function submitQuery() {
    const input = document.getElementById('query-input');
    const question = input.value.trim();
    if (!question || !projectId) return;

    const messages = document.getElementById('query-messages');

    // Add user bubble
    const userBubble = document.createElement('div');
    userBubble.className = 'query-bubble user';
    userBubble.textContent = question;
    messages.appendChild(userBubble);

    input.value = '';
    messages.scrollTop = messages.scrollHeight;

    const res = await fetch(`/api/projects/${projectId}/query_wiki`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question }),
    });

    const data = await res.json();

    const aiBubble = document.createElement('div');
    aiBubble.className = 'query-bubble assistant';
    aiBubble.textContent = data.answer || data.error || 'No response';
    messages.appendChild(aiBubble);
    messages.scrollTop = messages.scrollHeight;
}

// ─── Break Down Question ───

async function breakDown(questionId) {
    const card = document.querySelector(`[data-question-id="${questionId}"]`);
    if (!card) return;

    const btn = card.querySelector('.break-down-btn');
    btn.textContent = '...';
    btn.disabled = true;

    const res = await fetch(`/api/projects/${projectId}/break_down_question`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question_id: questionId }),
    });

    const data = await res.json();
    if (data.sub_questions && data.sub_questions.length > 0) {
        // Replace the card with sub-question cards
        const parent = card.parentElement;
        data.sub_questions.forEach((sq) => {
            const newCard = document.createElement('div');
            newCard.className = 'question-card';
            newCard.dataset.questionId = sq.id;
            newCard.innerHTML = `
                <div class="question-header">
                    <span class="question-text">${sq.text}</span>
                    <span class="question-agent">${sq.agent}</span>
                </div>
                <textarea data-for="${sq.id}" placeholder="Your answer..." rows="3"></textarea>
            `;
            parent.insertBefore(newCard, card);
        });
        card.remove();
    } else {
        btn.textContent = 'Split';
        btn.disabled = false;
    }
}

// ─── Export ───

document.getElementById('export-btn').addEventListener('click', () => {
    if (projectId) {
        window.location.href = `/api/projects/${projectId}/export`;
    }
});

// ─── Idea Summary Toggle ───

function toggleIdeaSummary() {
    document.getElementById('idea-summary').classList.toggle('collapsed');
}

// ─── Session Recovery ───

(function checkExistingSession() {
    const savedId = localStorage.getItem('ideaforge_project_id');
    if (!savedId) return;

    // Try to recover
    fetch(`/api/projects/${savedId}/questions`)
        .then((r) => r.json())
        .then((data) => {
            if (data.status === 'not_found') {
                localStorage.removeItem('ideaforge_project_id');
                return;
            }

            projectId = savedId;
            currentDepth = localStorage.getItem('ideaforge_depth') || 'medium';
            const idea = localStorage.getItem('ideaforge_idea') || '';

            const depthRounds = { shallow: 2, medium: 4, deep: 6, abyss: -1 };
            totalRounds = depthRounds[currentDepth];

            document.getElementById('idea-form').classList.add('hidden');
            document.getElementById('workspace').classList.remove('hidden');
            document.querySelector('.idea-summary-content').textContent = idea;
            document.getElementById('depth-indicator').textContent =
                currentDepth.charAt(0).toUpperCase() + currentDepth.slice(1);

            connectSSE();

            if (data.status === 'questions_ready') {
                renderQuestions(data.questions, data.round);
            } else if (data.status === 'complete') {
                showFinalWiki();
            } else {
                pollForQuestions();
            }
        })
        .catch(() => {
            localStorage.removeItem('ideaforge_project_id');
        });
})();
