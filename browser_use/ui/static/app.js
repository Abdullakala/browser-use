/* ═══════════════════════════════════════════════════════
   Browser-Use Agent UI – Frontend JavaScript
   ═══════════════════════════════════════════════════════ */

'use strict';

// ── State ─────────────────────────────────────────────────────────────────────

let currentRunId = null;
let ws = null;
let wsRetryCount = 0;
const MAX_WS_RETRIES = 8;

// ── Tab navigation ────────────────────────────────────────────────────────────

document.querySelectorAll('.nav-item').forEach(btn => {
  btn.addEventListener('click', () => {
    const target = btn.dataset.tab;
    document.querySelectorAll('.nav-item').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
    btn.classList.add('active');
    document.getElementById('tab-' + target).classList.add('active');
  });
});

// ── Theme toggle ──────────────────────────────────────────────────────────────

const themeBtn = document.getElementById('themeToggle');
themeBtn.addEventListener('click', () => {
  const isDark = document.body.classList.toggle('dark');
  document.body.classList.toggle('light', !isDark);
  themeBtn.textContent = isDark ? '🌙' : '☀️';
});

// ── Provider hints ────────────────────────────────────────────────────────────

const PROVIDER_HINTS = {
  browser_use: '🔑 احصل على مفتاح API المجاني من cloud.browser-use.com – الأسرع والأدق.',
  openai: '🔑 يتطلب مفتاح OPENAI_API_KEY. اختر نموذجاً مثل gpt-4.1 أو gpt-4.1-mini.',
  anthropic: '🔑 يتطلب مفتاح ANTHROPIC_API_KEY. الافتراضي: claude-sonnet-4-5.',
  google: '🔑 يتطلب مفتاح GOOGLE_API_KEY. الافتراضي: gemini-2.0-flash.',
  groq: '🔑 يتطلب مفتاح GROQ_API_KEY. الافتراضي: llama-3.3-70b-versatile.',
  ollama: '💻 يعمل محلياً، لا يتطلب مفتاح API. الافتراضي: llama3.',
  azure_openai: '🔑 يتطلب AZURE_OPENAI_API_KEY + متغيرات Azure الأخرى.',
  mistral: '🔑 يتطلب مفتاح MISTRAL_API_KEY. الافتراضي: mistral-large-latest.',
};

function onProviderChange() {
  const provider = document.getElementById('providerSelect').value;
  const hint = document.getElementById('providerHint');
  hint.textContent = PROVIDER_HINTS[provider] || '';
  hint.classList.toggle('visible', !!PROVIDER_HINTS[provider]);
}

onProviderChange();

// ── WebSocket ─────────────────────────────────────────────────────────────────

function connectWs() {
  const proto = location.protocol === 'https:' ? 'wss' : 'ws';
  ws = new WebSocket(`${proto}://${location.host}/ws`);

  ws.onopen = () => {
    wsRetryCount = 0;
  };

  ws.onmessage = (event) => {
    try {
      const msg = JSON.parse(event.data);
      handleWsMessage(msg);
    } catch (e) {
      console.error('WS parse error', e);
    }
  };

  ws.onclose = () => {
    if (wsRetryCount < MAX_WS_RETRIES) {
      wsRetryCount++;
      setTimeout(connectWs, Math.min(1000 * wsRetryCount, 8000));
    }
  };

  ws.onerror = () => ws.close();
}

function handleWsMessage(msg) {
  switch (msg.type) {

    case 'status': {
      const d = msg.data;
      if (d.status === 'running') {
        setRunning(true, msg.run_id || currentRunId, d.task, d.steps);
      } else {
        setRunning(false);
      }
      break;
    }

    case 'step': {
      const d = msg.data;
      const actNames = (d.actions || []).map(a => Object.keys(a)[0]).join(', ') || '—';
      addLog('step', `خطوة ${d.step} — الإجراءات: ${actNames}` + (d.url ? ` — ${d.url}` : ''));
      document.getElementById('stepCounter').textContent = `خطوة ${d.step}`;
      break;
    }

    case 'action': {
      addLog('action', JSON.stringify(msg.data));
      break;
    }

    case 'screenshot': {
      const panel = document.getElementById('screenshotPanel');
      const img = document.getElementById('screenshotImg');
      const meta = document.getElementById('screenshotMeta');
      img.src = 'data:image/jpeg;base64,' + msg.data.image;
      meta.textContent = `خطوة ${msg.data.step}`;
      panel.style.display = '';
      break;
    }

    case 'done': {
      const d = msg.data;
      setRunning(false);
      if (d.status === 'done') {
        addLog('done', '✅ اكتملت المهمة');
        if (d.result) {
          const rp = document.getElementById('resultPanel');
          document.getElementById('resultContent').textContent = d.result;
          rp.style.display = '';
        }
        toast('اكتملت المهمة بنجاح ✅', 'success');
      } else if (d.status === 'stopped') {
        addLog('info', '⏹ أُوقف الوكيل');
        toast('تم إيقاف الوكيل', '');
      }
      if (d.errors && d.errors.length) {
        d.errors.forEach(e => addLog('error', e));
      }
      loadHistory();
      break;
    }

    case 'error': {
      const d = msg.data;
      addLog('error', d.error);
      setRunning(false);
      toast('خطأ: ' + d.error, 'error');
      loadHistory();
      break;
    }

    default:
      break;
  }
}

// ── Log helpers ────────────────────────────────────────────────────────────────

function addLog(type, text) {
  const container = document.getElementById('logContainer');
  const placeholder = container.querySelector('.log-placeholder');
  if (placeholder) placeholder.remove();

  const now = new Date();
  const time = now.toLocaleTimeString('ar-SA', { hour12: false });

  const entry = document.createElement('div');
  entry.className = 'log-entry';

  const timeEl = document.createElement('span');
  timeEl.className = 'log-time';
  timeEl.textContent = time;

  const badge = document.createElement('span');
  badge.className = `log-badge badge-${type}`;
  const LABELS = { step: 'خطوة', action: 'إجراء', done: 'انتهى', error: 'خطأ', info: 'معلومة' };
  badge.textContent = LABELS[type] || type;

  const textEl = document.createElement('span');
  textEl.className = 'log-text';
  textEl.textContent = text;

  entry.append(timeEl, badge, textEl);
  container.appendChild(entry);
  container.scrollTop = container.scrollHeight;
}

function clearLog() {
  const c = document.getElementById('logContainer');
  c.innerHTML = '<p class="log-placeholder">سيظهر تدفق الوكيل هنا عند التشغيل…</p>';
}

// ── Run/Stop ───────────────────────────────────────────────────────────────────

async function startRun() {
  const task = document.getElementById('taskInput').value.trim();
  if (!task) { toast('الرجاء إدخال وصف المهمة', 'error'); return; }

  // Build config from form values
  const useVisionRadio = document.querySelector('input[name="useVision"]:checked');
  let useVision = useVisionRadio ? useVisionRadio.value : 'auto';
  if (useVision === 'true') useVision = true;
  else if (useVision === 'false') useVision = false;

  const allowedDomains = document.getElementById('allowedDomainsInput').value
    .split('\n').map(s => s.trim()).filter(Boolean);
  const prohibitedDomains = document.getElementById('prohibitedDomainsInput').value
    .split('\n').map(s => s.trim()).filter(Boolean);

  const payload = {
    task,
    config: {
      provider: document.getElementById('providerSelect').value,
      model: document.getElementById('modelInput').value.trim(),
      api_key: document.getElementById('apiKeyInput').value.trim(),
      temperature: parseFloat(document.getElementById('tempInput').value) || 0,
      max_steps: parseInt(document.getElementById('maxStepsInput').value) || 50,
      max_actions_per_step: parseInt(document.getElementById('maxActionsInput').value) || 5,
      use_vision: useVision,
      use_thinking: document.getElementById('useThinking').checked,
      flash_mode: document.getElementById('flashMode').checked,
      extend_system_message: document.getElementById('extendSysMsg').value.trim(),
      browser: {
        headless: document.getElementById('headlessCheck').checked,
        disable_security: document.getElementById('disableSecCheck').checked,
        window_width: parseInt(document.getElementById('winWidthInput').value) || 1280,
        window_height: parseInt(document.getElementById('winHeightInput').value) || 720,
        allowed_domains: allowedDomains,
        prohibited_domains: prohibitedDomains,
      },
    },
  };

  // Reset UI
  clearLog();
  document.getElementById('resultPanel').style.display = 'none';
  document.getElementById('screenshotPanel').style.display = 'none';
  document.getElementById('stepCounter').textContent = '';

  // Switch to task tab
  document.querySelector('[data-tab="task"]').click();

  try {
    const resp = await fetch('/api/run', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    const data = await resp.json();
    if (!resp.ok) {
      toast(data.error || 'فشل في بدء التشغيل', 'error');
      return;
    }
    currentRunId = data.run_id;
    setRunning(true, currentRunId, task, 0);
    addLog('info', 'بدأ الوكيل…');
    toast('تم إطلاق الوكيل ✅', 'success');
  } catch (e) {
    toast('خطأ في الاتصال: ' + e.message, 'error');
  }
}

async function stopRun() {
  if (!currentRunId) return;
  try {
    await fetch('/api/stop', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ run_id: currentRunId }),
    });
    toast('طلب الإيقاف أُرسل…', '');
  } catch (e) {
    toast('خطأ في الإيقاف: ' + e.message, 'error');
  }
}

// ── UI state helpers ───────────────────────────────────────────────────────────

function setRunning(running, runId, task, steps) {
  const dot  = document.getElementById('statusDot');
  const text = document.getElementById('statusText');
  const runBtn  = document.getElementById('runBtn');
  const stopBtn = document.getElementById('stopBtn');

  if (running) {
    currentRunId = runId;
    dot.className = 'status-dot running';
    text.textContent = task ? `تشغيل: ${task.substring(0, 40)}…` : 'يعمل…';
    runBtn.disabled = true;
    stopBtn.disabled = false;
    if (steps !== undefined) {
      document.getElementById('stepCounter').textContent = `خطوة ${steps}`;
    }
  } else {
    currentRunId = null;
    dot.className = 'status-dot done';
    text.textContent = 'في انتظار المهمة';
    runBtn.disabled = false;
    stopBtn.disabled = true;
    document.getElementById('stepCounter').textContent = '';
  }
}

// ── History ────────────────────────────────────────────────────────────────────

async function loadHistory() {
  try {
    const resp = await fetch('/api/history');
    const data = await resp.json();
    renderHistory(data.runs || []);
  } catch (e) {
    console.error('History load error', e);
  }
}

function renderHistory(runs) {
  const list = document.getElementById('historyList');
  if (!runs.length) {
    list.innerHTML = '<p class="log-placeholder">لا توجد عمليات تشغيل سابقة بعد.</p>';
    return;
  }

  list.innerHTML = '';
  runs.forEach(run => {
    const card = document.createElement('div');
    card.className = 'history-card';

    const statusClass = { done: 'hs-done', running: 'hs-running', error: 'hs-error', stopped: 'hs-stopped' }[run.status] || 'hs-stopped';
    const statusLabel = { done: 'اكتمل', running: 'يعمل', error: 'خطأ', stopped: 'أُوقف' }[run.status] || run.status;

    const started = new Date(run.started_at).toLocaleString('ar-SA');

    card.innerHTML = `
      <div class="history-card-header">
        <div class="history-task" title="${escapeHtml(run.task)}">${escapeHtml(run.task.substring(0, 80))}${run.task.length > 80 ? '…' : ''}</div>
        <span class="history-status ${statusClass}">${statusLabel}</span>
      </div>
      <div class="history-meta">
        <span>🕒 ${started}</span>
        <span>📶 ${run.steps} خطوة</span>
        <span>🤖 ${run.config.provider} / ${run.config.model || 'افتراضي'}</span>
      </div>
      ${run.final_result ? `<div class="history-result">${escapeHtml(run.final_result)}</div>` : ''}
      ${run.errors.length ? `<div class="history-result" style="color:var(--error)">⚠️ ${escapeHtml(run.errors[0])}</div>` : ''}
    `;
    list.appendChild(card);
  });
}

async function clearHistory() {
  if (!confirm('هل تريد مسح كامل سجل التشغيل؟')) return;
  await fetch('/api/history', { method: 'DELETE' });
  loadHistory();
}

// ── Toast ──────────────────────────────────────────────────────────────────────

function toast(msg, type) {
  const c = document.getElementById('toastContainer');
  const t = document.createElement('div');
  t.className = `toast ${type || ''}`;
  t.textContent = msg;
  c.appendChild(t);
  setTimeout(() => t.remove(), 3200);
}

// ── Utils ──────────────────────────────────────────────────────────────────────

function escapeHtml(str) {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

// ── Init ───────────────────────────────────────────────────────────────────────

connectWs();
loadHistory();

// Sync status on load
fetch('/api/status').then(r => r.json()).then(d => {
  if (d.running) setRunning(true, d.run_id, d.task, d.steps);
}).catch(() => {});
