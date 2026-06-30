'use strict';

const API_BASE_URL = 'http://localhost:8001/api/v1';
const HEALTH_URL   = 'http://localhost:8001/health';

// =============================================================================
// UTILS — define FIRST so everything else can use it
// =============================================================================
const Utils = {
  async request(path, options) {
    options = options || {};
    const url = API_BASE_URL + path;
    const resp = await fetch(url, Object.assign({
      headers: Object.assign({ 'Content-Type': 'application/json' }, options.headers || {})
    }, options));
    if (!resp.ok) {
      let msg = 'HTTP ' + resp.status;
      try { const err = await resp.json(); msg = err.detail || err.error || msg; } catch (_e) {}
      throw new Error(msg);
    }
    const ct = resp.headers.get('content-type') || '';
    if (ct.includes('application/json')) return resp.json();
    return resp;
  },
  post(path, body) { return this.request(path, { method: 'POST', body: JSON.stringify(body) }); },
  get(path)        { return this.request(path, { method: 'GET' }); },

  toast(message, type) {
    type = type || 'success';
    const container = document.getElementById('toast-container');
    if (!container) return;
    const id = 'toast-' + Date.now();
    const iconMap = { success: 'check-circle', danger: 'exclamation-triangle', warning: 'exclamation-circle', info: 'info-circle' };
    const icon = iconMap[type] || 'info-circle';
    container.insertAdjacentHTML('beforeend',
      '<div id="' + id + '" class="toast align-items-center text-bg-' + type + ' border-0" role="alert">' +
      '<div class="d-flex"><div class="toast-body"><i class="fa-solid fa-' + icon + ' me-2"></i>' + message + '</div>' +
      '<button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast"></button></div></div>');
    const el = document.getElementById(id);
    if (el && window.bootstrap) {
      new bootstrap.Toast(el, { delay: 4000 }).show();
      el.addEventListener('hidden.bs.toast', function() { el.remove(); });
    }
  },

  setLoading(visible, message) {
    const el = document.getElementById('loading-overlay');
    const msg = document.getElementById('loading-message');
    if (!el) return;
    el.classList.toggle('d-none', !visible);
    if (msg) msg.textContent = message || 'Processing...';
  },

  formatBytes(bytes) {
    if (!bytes) return '—';
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1048576) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / 1048576).toFixed(2) + ' MB';
  },

  truncate(text, max) {
    max = max || 200;
    return text && text.length > max ? text.slice(0, max) + '…' : text;
  },

  scoreBadgeClass(score) {
    return score >= 0.75 ? 'high' : score >= 0.5 ? 'medium' : 'low';
  },

  riskBadgeClass(cat) {
    var m = { LOW: 'risk-LOW', MEDIUM: 'risk-MEDIUM', HIGH: 'risk-HIGH', VERY_HIGH: 'risk-VERY_HIGH' };
    return m[cat] || 'risk-MEDIUM';
  },

  escHtml(str) {
    const d = document.createElement('div');
    d.appendChild(document.createTextNode(String(str)));
    return d.innerHTML;
  }
};

// =============================================================================
// UI — Navigation and Charts
// =============================================================================
const UI = {
  _charts: {},

  init() {
    document.querySelectorAll('.nav-item').forEach(function(link) {
      link.addEventListener('click', function(e) {
        e.preventDefault();
        const s = link.dataset.section;
        if (s) UI.navigate(s);
      });
    });
    const tog = document.getElementById('sidebar-toggle');
    if (tog) tog.addEventListener('click', function() {
      document.getElementById('sidebar').classList.toggle('open');
    });
    const sel = document.getElementById('global-dataset-select');
    if (sel) sel.addEventListener('change', function(e) {
      DatasetStore.setSelected(e.target.value);
    });
    UI.checkHealth();
    setInterval(function() { UI.checkHealth(); }, 30000);
    DatasetStore.refresh();
    setInterval(function() { DatasetStore.refresh(); }, 15000);
    Home.loadStats();
  },

  navigate(section) {
    document.querySelectorAll('.nav-item').forEach(function(l) {
      l.classList.toggle('active', l.dataset.section === section);
    });
    document.querySelectorAll('.content-section').forEach(function(s) {
      s.classList.remove('active');
    });
    const target = document.getElementById('section-' + section);
    if (target) target.classList.add('active');

    const titles = {
      home: 'Home', upload: 'Upload Data', chat: 'AI Assistant',
      search: 'Semantic Search', fairness: 'Fairness Dashboard',
      ml: 'ML Engine', reports: 'Reports', monitoring: 'Monitoring', settings: 'AI Settings'
    };
    const titleEl = document.getElementById('page-title');
    if (titleEl) titleEl.textContent = titles[section] || section;

    const bar = document.getElementById('global-dataset-bar');
    if (bar) {
      const hideOn = ['home', 'upload', 'chat', 'search', 'settings'];
      bar.classList.toggle('d-none', hideOn.indexOf(section) !== -1);
    }

    if (section === 'monitoring') Monitoring.load();
    if (section === 'upload')     { Upload.listUploads(); DatasetStore.refresh(); }
    if (section === 'home')       Home.loadStats();
    if (section === 'settings')   Settings.init();
  },

  async checkHealth() {
    const badge   = document.getElementById('api-status-badge');
    const homeApi = document.getElementById('home-stat-api');
    try {
      const controller = new AbortController();
      const timer = setTimeout(function() { controller.abort(); }, 5000);
      const resp = await fetch(HEALTH_URL, { signal: controller.signal });
      clearTimeout(timer);
      if (resp.ok) {
        if (badge) { badge.className = 'badge bg-success'; badge.innerHTML = '<i class="fa-solid fa-circle me-1"></i>API Online'; }
        if (homeApi) { homeApi.textContent = 'Online'; homeApi.style.color = '#388E3C'; }
      } else {
        if (badge) { badge.className = 'badge bg-warning text-dark'; badge.innerHTML = '<i class="fa-solid fa-circle me-1"></i>API Issues'; }
        if (homeApi) { homeApi.textContent = 'Issues'; homeApi.style.color = '#F57C00'; }
      }
    } catch (_e) {
      if (badge) { badge.className = 'badge bg-danger'; badge.innerHTML = '<i class="fa-solid fa-circle me-1"></i>API Offline'; }
      if (homeApi) { homeApi.textContent = 'Offline'; homeApi.style.color = '#D32F2F'; }
    }
    const lbl = document.getElementById('last-updated-label');
    if (lbl) lbl.textContent = 'Updated ' + new Date().toLocaleTimeString();
  },

  destroyChart(id) {
    if (UI._charts[id]) { UI._charts[id].destroy(); delete UI._charts[id]; }
  },

  createBarChart(canvasId, labels, data, label, colors) {
    UI.destroyChart(canvasId);
    const canvas = document.getElementById(canvasId);
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    UI._charts[canvasId] = new Chart(ctx, {
      type: 'bar',
      data: { labels: labels, datasets: [{ label: label, data: data, backgroundColor: colors || '#1976D2', borderRadius: 4 }] },
      options: { responsive: true, maintainAspectRatio: true, plugins: { legend: { display: false } }, scales: { y: { beginAtZero: true, max: 1.0 } } }
    });
  },

  createLineChart(canvasId, labels, data, label) {
    UI.destroyChart(canvasId);
    const canvas = document.getElementById(canvasId);
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    UI._charts[canvasId] = new Chart(ctx, {
      type: 'line',
      data: { labels: labels, datasets: [{ label: label, data: data, borderColor: '#1976D2', backgroundColor: 'rgba(25,118,210,0.1)', fill: true, tension: 0.3, pointRadius: 3 }] },
      options: { responsive: true, maintainAspectRatio: true, plugins: { legend: { display: false } } }
    });
  },

  createDoughnutChart(canvasId, labels, data) {
    UI.destroyChart(canvasId);
    const canvas = document.getElementById(canvasId);
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    UI._charts[canvasId] = new Chart(ctx, {
      type: 'doughnut',
      data: { labels: labels, datasets: [{ data: data, backgroundColor: ['#388E3C', '#F57C00', '#D32F2F', '#880E4F'] }] },
      options: { responsive: true, maintainAspectRatio: true }
    });
  }
};

// =============================================================================
// DATASET STORE
// =============================================================================
const DatasetStore = {
  _datasets: [],
  _selected: null,

  async refresh() {
    try {
      const data = await Utils.get('/upload/list');
      DatasetStore._datasets = (data.uploads || []).filter(function(u) { return u.status === 'completed'; });
      DatasetStore._renderAllDropdowns();
    } catch (_e) {}
  },

  getSelected() { return DatasetStore._selected || ''; },

  getSelectedName() {
    const ds = DatasetStore._datasets.find(function(d) { return d.file_id === DatasetStore._selected; });
    return ds ? (ds.filename || ds.file_id.slice(0, 8) + '...') : 'None selected';
  },

  setSelected(fileId) {
    DatasetStore._selected = fileId;
    const sel = document.getElementById('global-dataset-select');
    if (sel) sel.value = fileId || '';
    DatasetStore._syncDisplays();
  },

  _renderAllDropdowns() {
    const sel = document.getElementById('global-dataset-select');
    if (!sel) return;
    const current = sel.value;
    let opts = '<option value="">— Select uploaded dataset —</option>';
    DatasetStore._datasets.forEach(function(d) {
      opts += '<option value="' + Utils.escHtml(d.file_id) + '">' + Utils.escHtml(d.filename || d.file_id.slice(0, 12) + '...') + ' (' + Utils.formatBytes(d.file_size || 0) + ')</option>';
    });
    sel.innerHTML = opts;
    if (current && DatasetStore._datasets.find(function(d) { return d.file_id === current; })) {
      sel.value = current;
      DatasetStore._selected = current;
    } else if (DatasetStore._datasets.length > 0 && !DatasetStore._selected) {
      sel.value = DatasetStore._datasets[0].file_id;
      DatasetStore._selected = DatasetStore._datasets[0].file_id;
    }
    DatasetStore._syncDisplays();
  },

  _syncDisplays() {
    const name = DatasetStore.getSelectedName();
    const id   = DatasetStore._selected;
    const label = id ? name : 'No dataset selected — use the dropdown above';
    const color = id ? '#212529' : '#6c757d';
    ['fairness-dataset-display', 'ml-dataset-display', 'ml-batch-display', 'report-dataset-display'].forEach(function(elId) {
      const el = document.getElementById(elId);
      if (el) { el.textContent = label; el.style.color = color; }
    });
    const homeDs = document.getElementById('home-stat-datasets');
    if (homeDs) homeDs.textContent = DatasetStore._datasets.length;
  }
};

// =============================================================================
// HOME
// =============================================================================
const Home = {
  async loadStats() {
    try {
      const data = await fetch('http://localhost:8001/monitoring/dashboard').then(function(r) { return r.json(); });
      const tq = document.getElementById('home-stat-queries');
      const tf = document.getElementById('home-stat-fairness');
      if (tq) tq.textContent = data.total_queries != null ? data.total_queries : '0';
      if (tf) tf.textContent = data.average_fairness_score != null ? data.average_fairness_score.toFixed(1) : '—';
    } catch (_e) {}
    await DatasetStore.refresh();
  }
};

// =============================================================================
// UPLOAD
// =============================================================================
const Upload = {
  handleDrop(event, type) {
    event.preventDefault();
    const f = event.dataTransfer.files[0];
    if (f) Upload._upload(f, type);
  },

  handleFileSelect(input, type) {
    const f = input.files[0];
    if (f) Upload._upload(f, type);
    input.value = '';
  },

  async _upload(file, type) {
    const suffix   = type === 'dataset' ? 'dataset' : 'doc';
    const endpoint = type === 'dataset' ? '/upload/dataset' : '/upload/document';
    const progressWrap = document.getElementById('upload-progress-' + suffix);
    const bar          = document.getElementById('upload-bar-' + suffix);
    const statusText   = document.getElementById('upload-status-text-' + suffix);
    if (progressWrap) progressWrap.classList.remove('d-none');
    if (bar) bar.style.width = '20%';
    if (statusText) statusText.textContent = 'Uploading ' + file.name + '...';
    const formData = new FormData();
    formData.append('file', file);
    try {
      const resp = await fetch(API_BASE_URL + endpoint, { method: 'POST', body: formData });
      if (!resp.ok) throw new Error('Upload failed: ' + resp.status);
      const data = await resp.json();
      if (bar) bar.style.width = '60%';
      if (statusText) statusText.textContent = 'Processing...';
      Utils.toast(file.name + ' uploaded successfully!', 'success');
      Upload._pollStatus(data.file_id, bar, statusText, type);
      Upload.listUploads();
    } catch (err) {
      if (bar) { bar.classList.add('bg-danger'); bar.style.width = '100%'; }
      if (statusText) statusText.textContent = 'Error: ' + err.message;
      Utils.toast(err.message, 'danger');
    }
  },

  _pollStatus(fileId, bar, statusText, type) {
    let attempts = 0;
    const timer = setInterval(async function() {
      attempts++;
      try {
        const data   = await Utils.get('/upload/status/' + fileId);
        const status = (data.details && data.details.status) ? data.details.status : data.status;
        if (status === 'completed') {
          clearInterval(timer);
          if (bar) { bar.style.width = '100%'; bar.classList.remove('progress-bar-animated', 'bg-danger'); }
          if (statusText) statusText.textContent = 'Completed ✓';
          if (type === 'dataset') Upload._showResults(data.details);
          Upload.listUploads();
          DatasetStore.refresh();
        } else if (status === 'failed') {
          clearInterval(timer);
          if (bar) bar.classList.add('bg-danger');
          if (statusText) statusText.textContent = 'Failed: ' + ((data.details && data.details.error) || 'Unknown error');
        } else {
          if (bar) bar.style.width = Math.min(60 + attempts * 5, 90) + '%';
        }
        if (attempts >= 60) clearInterval(timer);
      } catch (_e) {
        if (attempts >= 60) clearInterval(timer);
      }
    }, 2000);
  },

  _showResults(details) {
    if (!details) return;
    const container = document.getElementById('upload-results');
    const body = document.getElementById('upload-results-body');
    if (!container || !body) return;
    let html = '<div class="row g-3">';
    if (details.rows) html += '<div class="col-md-3"><div class="metric-card"><div class="metric-label">Rows Loaded</div><div class="metric-value">' + details.rows.toLocaleString() + '</div></div></div>';
    if (details.schema_discovery) {
      const sd = details.schema_discovery;
      html += '<div class="col-md-3"><div class="metric-card"><div class="metric-label">Fields Mapped</div><div class="metric-value">' + sd.mapped_columns + '/' + sd.total_columns + '</div></div></div>';
    }
    if (details.processing_report) {
      const pr = details.processing_report;
      const c = pr.quality_score >= 80 ? '#388E3C' : pr.quality_score >= 60 ? '#F57C00' : '#D32F2F';
      html += '<div class="col-md-3"><div class="metric-card"><div class="metric-label">Quality Score</div><div class="metric-value" style="color:' + c + '">' + pr.quality_score.toFixed(1) + '</div></div></div>';
      html += '<div class="col-md-3"><div class="metric-card"><div class="metric-label">Duplicates Removed</div><div class="metric-value">' + pr.duplicates_removed + '</div></div></div>';
    }
    html += '</div>';
    if (details.schema_discovery && details.schema_discovery.field_mappings) {
      const fm = details.schema_discovery.field_mappings;
      html += '<div class="mt-3"><strong class="small">Mapped Fields:</strong><div class="d-flex flex-wrap gap-1 mt-1">';
      Object.keys(fm).forEach(function(k) {
        html += '<span class="badge bg-primary-subtle text-primary-emphasis">' + Utils.escHtml(k) + ' ← ' + Utils.escHtml(fm[k]) + '</span>';
      });
      html += '</div></div>';
    }
    body.innerHTML = html;
    container.classList.remove('d-none');
  },

  async listUploads() {
    try {
      const data      = await Utils.get('/upload/list');
      const container = document.getElementById('uploads-table-container');
      if (!container) return;
      if (!data.uploads || !data.uploads.length) {
        container.innerHTML = '<p class="text-muted small p-3 mb-0">No files uploaded yet.</p>';
        return;
      }
      let rows = '';
      data.uploads.forEach(function(u) {
        const statusClass = u.status === 'completed' ? 'bg-success' : u.status === 'failed' ? 'bg-danger' : 'bg-warning text-dark';
        const useBtn = u.status === 'completed'
          ? '<button class="btn btn-xs btn-sm btn-primary py-0 px-2" onclick="DatasetStore.setSelected(\'' + Utils.escHtml(u.file_id) + '\');UI.navigate(\'fairness\')"><i class="fa-solid fa-arrow-right me-1"></i>Use</button>'
          : '';
        rows += '<tr><td><code class="small">' + Utils.escHtml(u.file_id.slice(0, 8)) + '...</code></td><td>' + Utils.escHtml(u.filename || '—') + '</td><td><span class="badge ' + statusClass + '">' + u.status + '</span></td><td>' + Utils.formatBytes(u.file_size) + '</td><td>' + useBtn + '</td></tr>';
      });
      container.innerHTML = '<table class="table-platform w-100"><thead><tr><th>File ID</th><th>Filename</th><th>Status</th><th>Size</th><th>Action</th></tr></thead><tbody>' + rows + '</tbody></table>';
    } catch (_e) {}
  }
};

// =============================================================================
// CHAT
// =============================================================================
const Chat = {
  _isTyping: false,

  getSessionId() {
    const el = document.getElementById('session-id-input');
    return (el && el.value.trim()) ? el.value.trim() : 'default';
  },

  async send() {
    const input = document.getElementById('chat-input');
    if (!input) return;
    const text  = input.value.trim();
    if (!text || Chat._isTyping) return;
    input.value = '';
    Chat._addBubble('user', text);
    Chat._showTyping();
    Chat._isTyping = true;
    const btn = document.getElementById('chat-send-btn');
    if (btn) btn.disabled = true;
    // Get provider/model overrides
    const providerEl = document.getElementById('chat-provider-select');
    const modelEl    = document.getElementById('chat-model-select');
    const provider   = providerEl && providerEl.value ? providerEl.value : undefined;
    const model      = modelEl    && modelEl.value    ? modelEl.value    : undefined;
    try {
      const body = { messages: [{ role: 'user', content: text }], session_id: Chat.getSessionId(), top_k: 10 };
      if (provider) body.provider = provider;
      if (model)    body.model    = model;
      const resp = await Utils.post('/chat', body);
      Chat._removeTyping();
      // Show which provider was used
      const usedProvider = (resp.metadata && resp.metadata.provider) ? resp.metadata.provider.toUpperCase() : '';
      const usedModel    = (resp.metadata && resp.metadata.model)    ? resp.metadata.model : '';
      Chat._addBubble('assistant', resp.answer, usedProvider, usedModel);
      Chat._showSources(resp.sources || []);
    } catch (err) {
      Chat._removeTyping();
      Chat._addBubble('assistant', '⚠️ Error: ' + err.message);
    } finally {
      Chat._isTyping = false;
      if (btn) btn.disabled = false;
    }
  },

  _addBubble(role, content, providerLabel, modelLabel) {
    const c = document.getElementById('chat-messages');
    if (!c) return;
    const d = document.createElement('div');
    d.className = 'chat-bubble ' + role;
    const icon = role === 'user' ? 'user' : 'robot';
    const formatted = Utils.escHtml(content).replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>').replace(/\n/g, '<br/>');
    // Add provider badge for assistant messages
    const badge = (role === 'assistant' && providerLabel)
      ? '<div class="chat-provider-badge">' + providerLabel + (modelLabel ? ' / ' + modelLabel : '') + '</div>'
      : '';
    d.innerHTML = '<div class="bubble-avatar"><i class="fa-solid fa-' + icon + '"></i></div><div class="bubble-content">' + formatted + badge + '</div>';
    c.appendChild(d);
    c.scrollTop = c.scrollHeight;
  },

  _showTyping() {
    const c = document.getElementById('chat-messages');
    if (!c) return;
    const d = document.createElement('div');
    d.className = 'chat-bubble assistant';
    d.id = 'typing-bubble';
    d.innerHTML = '<div class="bubble-avatar"><i class="fa-solid fa-robot"></i></div><div class="bubble-content"><div class="typing-indicator"><span></span><span></span><span></span></div></div>';
    c.appendChild(d);
    c.scrollTop = c.scrollHeight;
  },

  _removeTyping() { const el = document.getElementById('typing-bubble'); if (el) el.remove(); },

  _showSources(sources) {
    const p = document.getElementById('chat-sources');
    if (!p) return;
    if (!sources.length) { p.innerHTML = '<p class="text-muted small">No sources retrieved.</p>'; return; }
    let html = '';
    sources.forEach(function(s, i) {
      html += '<div class="source-chip"><div class="d-flex justify-content-between mb-1"><small class="fw-bold">#' + (i + 1) + ' ' + Utils.escHtml(s.source || 'unknown') + '</small><span class="source-score">' + (s.score * 100).toFixed(0) + '%</span></div><small class="text-muted">' + Utils.truncate(s.text, 150) + '</small></div>';
    });
    p.innerHTML = html;
  },

  async clearSession() {
    try {
      await Utils.request('/chat/session/' + Chat.getSessionId(), { method: 'DELETE' });
      const msgs = document.getElementById('chat-messages');
      if (msgs) msgs.innerHTML = '<div class="chat-bubble assistant"><div class="bubble-avatar"><i class="fa-solid fa-robot"></i></div><div class="bubble-content"><p class="mb-0">Session cleared. How can I help you?</p></div></div>';
      const src = document.getElementById('chat-sources');
      if (src) src.innerHTML = '<p class="text-muted small">Sources will appear here after each query.</p>';
      Utils.toast('Session cleared.', 'info');
    } catch (err) { Utils.toast(err.message, 'danger'); }
  }
};

// =============================================================================
// SEARCH
// =============================================================================
const Search = {
  async run() {
    const queryEl = document.getElementById('search-query');
    const typeEl  = document.getElementById('search-type');
    const topKEl  = document.getElementById('search-top-k');
    const query = queryEl ? queryEl.value.trim() : '';
    const type  = typeEl  ? typeEl.value : 'semantic';
    const topK  = topKEl  ? (parseInt(topKEl.value) || 10) : 10;
    if (!query) { Utils.toast('Please enter a search query.', 'warning'); return; }
    const container = document.getElementById('search-results-container');
    if (!container) return;
    container.innerHTML = '<div class="text-center py-4"><div class="spinner-border text-primary"></div></div>';
    try {
      const results = await Utils.post('/search/' + type, { query: query, top_k: topK });
      if (!results.length) { container.innerHTML = '<div class="text-muted text-center py-4">No results found.</div>'; return; }
      let html = '<div class="mb-2 small text-muted"><strong>' + results.length + '</strong> results</div>';
      results.forEach(function(r, i) {
        html += '<div class="search-result-card"><div class="d-flex justify-content-between mb-2"><div class="fw-semibold small">#' + (i + 1) + ' ' + Utils.escHtml(r.source || r.id) + '</div><span class="score-badge ' + Utils.scoreBadgeClass(r.score) + '">' + (r.score * 100).toFixed(1) + '% match</span></div><p class="small mb-1">' + Utils.escHtml(Utils.truncate(r.text, 300)) + '</p></div>';
      });
      container.innerHTML = html;
    } catch (err) {
      container.innerHTML = '<div class="alert alert-danger">' + Utils.escHtml(err.message) + '</div>';
    }
  }
};

// =============================================================================
// FAIRNESS
// =============================================================================
const Fairness = {
  async registerCsv() {
    const idEl  = document.getElementById('csv-reg-id');
    const csvEl = document.getElementById('csv-reg-content');
    const id    = idEl  ? idEl.value.trim()  : null;
    const csv   = csvEl ? csvEl.value.trim() : '';
    if (!csv) { Utils.toast('Please enter CSV content.', 'warning'); return; }
    Utils.setLoading(true, 'Registering dataset...');
    try {
      const data = await Utils.post('/fairness/register-dataset', { dataset_id: id || null, csv_data: csv });
      Utils.toast('Dataset registered: ' + data.details.dataset_id, 'success');
      await DatasetStore.refresh();
      DatasetStore.setSelected(data.details.dataset_id);
      const modal = document.getElementById('modal-register-csv');
      if (modal && window.bootstrap) bootstrap.Modal.getInstance(modal) && bootstrap.Modal.getInstance(modal).hide();
    } catch (err) { Utils.toast(err.message, 'danger'); }
    finally { Utils.setLoading(false); }
  },

  async runAudit() {
    const datasetId = DatasetStore.getSelected();
    if (!datasetId) { Utils.toast('Please select a dataset from the dropdown above.', 'warning'); return; }
    try {
      const detected = await Utils.get('/fairness/detect-columns/' + datasetId);
      Fairness._showDetectedColumns(detected);
    } catch (_e) {}
    const outcomeEl    = document.getElementById('fairness-outcome-col');
    const protectedEl  = document.getElementById('fairness-protected-cols');
    const outcomeOverride   = outcomeEl   ? outcomeEl.value.trim()   : null;
    const protectedOverride = protectedEl ? protectedEl.value.trim() : null;
    const auditBody = { dataset_id: datasetId };
    if (outcomeOverride) auditBody.outcome_column = outcomeOverride;
    if (protectedOverride) {
      try {
        const colMap = {};
        protectedOverride.split(',').map(function(s) { return s.trim(); }).filter(Boolean).forEach(function(pair) {
          const parts = pair.split('=').map(function(s) { return s.trim(); });
          if (parts[0] && parts[1]) colMap[parts[0]] = parts[1];
        });
        if (Object.keys(colMap).length > 0) auditBody.protected_columns = colMap;
      } catch (_e) {}
    }
    Utils.setLoading(true, 'Running fairness audit...');
    try {
      const report = await Utils.post('/fairness/audit', auditBody);
      Fairness._renderReport(report);
      Utils.toast('Fairness audit complete.', 'success');
    } catch (err) { Utils.toast(err.message, 'danger'); }
    finally { Utils.setLoading(false); }
  },

  async runAiExplain() {
    const datasetId = DatasetStore.getSelected();
    if (!datasetId) { Utils.toast('Please select a dataset from the dropdown above.', 'warning'); return; }
    const panel   = document.getElementById('fairness-ai-panel');
    const content = document.getElementById('fairness-ai-content');
    const badge   = document.getElementById('fairness-ai-provider-badge');
    if (panel)   panel.classList.remove('d-none');
    if (content) content.innerHTML = '<div class="text-center py-3"><div class="spinner-border text-warning spinner-border-sm me-2"></div>Generating AI analysis...</div>';
    const auditBody = { dataset_id: datasetId };
    const outcomeEl   = document.getElementById('fairness-outcome-col');
    const protectedEl = document.getElementById('fairness-protected-cols');
    if (outcomeEl && outcomeEl.value.trim()) auditBody.outcome_column = outcomeEl.value.trim();
    if (protectedEl && protectedEl.value.trim()) {
      try {
        const colMap = {};
        protectedEl.value.trim().split(',').map(function(s) { return s.trim(); }).filter(Boolean).forEach(function(pair) {
          const parts = pair.split('=').map(function(s) { return s.trim(); });
          if (parts[0] && parts[1]) colMap[parts[0]] = parts[1];
        });
        if (Object.keys(colMap).length > 0) auditBody.protected_columns = colMap;
      } catch (_e) {}
    }
    try {
      const data = await Utils.post('/fairness/ai-explain', auditBody);
      if (badge) badge.textContent = ((data.provider || 'AI').toUpperCase()) + ' / ' + (data.model || '');
      if (content) {
        const text = data.ai_explanation || 'No AI explanation returned.';
        content.innerHTML = Utils.escHtml(text).replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>').replace(/\n\n/g, '</p><p>').replace(/\n/g, '<br/>');
      }
      if (data.report) Fairness._renderReport(data.report);
      Utils.toast('AI fairness analysis complete!', 'success');
    } catch (err) {
      if (content) content.innerHTML = '<div class="alert alert-warning small mb-0"><i class="fa-solid fa-triangle-exclamation me-1"></i>' + Utils.escHtml(err.message) + '<br/><a href="#" onclick="UI.navigate(\'settings\')">Configure AI provider in Settings →</a></div>';
      Utils.toast(err.message, 'warning');
    }
  },

  _showDetectedColumns(detected) {
    const container = document.getElementById('fairness-detected-cols');
    const info      = document.getElementById('fairness-detected-info');
    if (!container || !info) return;
    const dtype   = detected.dataset_type ? detected.dataset_type.replace(/_/g, ' ') : 'generic';
    const outcome = detected.detected_outcome_column || '(none)';
    const pcols   = detected.detected_protected_columns || {};
    const pStr    = Object.keys(pcols).map(function(k) { return k + '=' + pcols[k]; }).join(', ') || '(none)';
    const rows    = detected.total_rows ? detected.total_rows.toLocaleString() + ' rows' : '';
    info.innerHTML = 'Type: <strong>' + Utils.escHtml(dtype) + '</strong> | ' + (rows ? rows + ' | ' : '') + 'Outcome: <strong>' + Utils.escHtml(outcome) + '</strong> | Protected: <strong>' + Utils.escHtml(pStr) + '</strong>';
    container.classList.remove('d-none');
  },

  _renderReport(report) {
    const score   = report.score;
    const scoreEl = document.getElementById('metric-fairness-score');
    if (scoreEl) {
      scoreEl.textContent = score.toFixed(1);
      scoreEl.style.color = score >= 80 ? '#388E3C' : score >= 60 ? '#F57C00' : '#D32F2F';
    }
    const interp = document.getElementById('metric-fairness-interpretation');
    if (interp) interp.textContent = score >= 80 ? '✓ Acceptable' : score >= 60 ? '⚠ Needs Attention' : '✗ High Risk';
    const di = report.disparate_impact_ratios || {};
    const raceDI   = document.getElementById('metric-race-di');
    const genderDI = document.getElementById('metric-gender-di');
    const biasCount = document.getElementById('metric-bias-count');
    if (raceDI)   raceDI.textContent   = di.race   != null ? (di.race   * 100).toFixed(1) + '%' : '—';
    if (genderDI) genderDI.textContent = di.gender != null ? (di.gender * 100).toFixed(1) + '%' : '—';
    if (biasCount) biasCount.textContent = (report.bias_indicators || []).length;
    const ar = report.approval_rates_by_group || {};
    if (ar.race) {
      const e = Object.entries(ar.race);
      UI.createBarChart('chart-race-approval', e.map(function(x) { return x[0]; }), e.map(function(x) { return x[1]; }), 'Approval Rate', e.map(function(x) { return x[1] >= 0.8 ? '#388E3C' : '#D32F2F'; }));
    }
    if (ar.gender) {
      const e = Object.entries(ar.gender);
      UI.createBarChart('chart-gender-approval', e.map(function(x) { return x[0]; }), e.map(function(x) { return x[1]; }), 'Approval Rate', e.map(function(x) { return x[1] >= 0.8 ? '#388E3C' : '#D32F2F'; }));
    }
    const findingsEl = document.getElementById('fairness-findings');
    if (findingsEl) {
      findingsEl.innerHTML = (report.findings || []).map(function(f) {
        const isType = f.toLowerCase().indexOf('dataset type detected') === 0;
        return '<div class="d-flex gap-2 mb-2 small"><i class="fa-solid ' + (isType ? 'fa-tag text-info' : 'fa-circle-dot text-warning') + ' mt-1 flex-shrink-0"></i><span>' + Utils.escHtml(f) + '</span></div>';
      }).join('') || '<p class="text-muted small">No findings.</p>';
    }
    const recsEl = document.getElementById('fairness-recommendations');
    if (recsEl) {
      recsEl.innerHTML = (report.recommendations || []).map(function(r) {
        return '<div class="d-flex gap-2 mb-2 small"><i class="fa-solid fa-check text-success mt-1 flex-shrink-0"></i><span>' + Utils.escHtml(r) + '</span></div>';
      }).join('') || '<p class="text-muted small">No recommendations.</p>';
    }
  }
};

// =============================================================================
// ML ENGINE
// =============================================================================
const ML = {
  async train() {
    const datasetId = DatasetStore.getSelected();
    const targetEl  = document.getElementById('ml-target-col');
    const targetCol = targetEl ? targetEl.value.trim() : '';
    if (!datasetId) { Utils.toast('Please select a dataset from the dropdown above.', 'warning'); return; }
    Utils.setLoading(true, 'Training model...');
    try {
      const data = await Utils.post('/ml/train', { dataset_id: datasetId, target_column: targetCol || undefined });
      const el = document.getElementById('ml-train-result');
      if (el) el.innerHTML = '<div class="alert alert-success small py-2 mb-0"><strong>Model trained!</strong><br/>Accuracy: <strong>' + (data.accuracy * 100).toFixed(1) + '%</strong> | Rows: ' + data.training_rows.toLocaleString() + ' | Features: ' + data.features_used.length + '</div>';
      Utils.toast('Model training complete!', 'success');
    } catch (err) {
      const el = document.getElementById('ml-train-result');
      if (el) el.innerHTML = '<div class="alert alert-danger small py-2 mb-0">' + Utils.escHtml(err.message) + '</div>';
    } finally { Utils.setLoading(false); }
  },

  async predict() {
    const rawEl = document.getElementById('ml-predict-record');
    const appEl = document.getElementById('ml-predict-id');
    const rawJson = rawEl ? rawEl.value.trim() : '';
    const appId   = appEl ? appEl.value.trim() : '';
    if (!rawJson) { Utils.toast('Enter a record JSON.', 'warning'); return; }
    let record;
    try { record = JSON.parse(rawJson); } catch (_e) { Utils.toast('Invalid JSON.', 'danger'); return; }
    Utils.setLoading(true, 'Predicting...');
    try {
      const data = await Utils.post('/ml/predict', { record: record, applicant_id: appId || undefined });
      const rc   = Utils.riskBadgeClass(data.risk_category);
      const el   = document.getElementById('ml-predict-result');
      if (el) el.innerHTML = '<div class="card border mt-2"><div class="card-body py-2 px-3"><div class="d-flex justify-content-between mb-1"><strong class="small">Approval Probability</strong><strong style="font-size:1.4rem">' + (data.approval_probability * 100).toFixed(1) + '%</strong></div><div class="d-flex justify-content-between"><span class="small text-muted">Risk Category</span><span class="risk-badge ' + rc + '">' + data.risk_category + '</span></div><div class="d-flex justify-content-between mt-1"><span class="small text-muted">Risk Score</span><span class="fw-semibold">' + data.risk_score.toFixed(1) + '/100</span></div></div></div>';
    } catch (err) { Utils.toast(err.message, 'danger'); }
    finally { Utils.setLoading(false); }
  },

  async predictBatch() {
    const datasetId = DatasetStore.getSelected();
    if (!datasetId) { Utils.toast('Please select a dataset from the dropdown above.', 'warning'); return; }
    Utils.setLoading(true, 'Running batch predictions...');
    try {
      const data = await Utils.post('/ml/predict-batch', { dataset_id: datasetId });
      ML._renderBatchResults(data);
      Utils.toast(data.length + ' predictions generated.', 'success');
    } catch (err) { Utils.toast(err.message, 'danger'); }
    finally { Utils.setLoading(false); }
  },

  _renderBatchResults(predictions) {
    const container = document.getElementById('ml-batch-results');
    if (!container) return;
    if (!predictions.length) { container.innerHTML = '<p class="text-muted small">No predictions.</p>'; return; }
    const dist = { LOW: 0, MEDIUM: 0, HIGH: 0, VERY_HIGH: 0 };
    predictions.forEach(function(p) { dist[p.risk_category] = (dist[p.risk_category] || 0) + 1; });
    UI.createDoughnutChart('chart-risk-dist', Object.keys(dist), Object.values(dist));
    let rows = '';
    predictions.slice(0, 20).forEach(function(p) {
      rows += '<tr><td>' + Utils.escHtml(p.applicant_id) + '</td><td>' + (p.approval_probability * 100).toFixed(1) + '%</td><td>' + p.risk_score.toFixed(1) + '</td><td><span class="risk-badge ' + Utils.riskBadgeClass(p.risk_category) + '">' + p.risk_category + '</span></td></tr>';
    });
    container.innerHTML = '<p class="small text-muted mb-2">Showing 20 of ' + predictions.length + ' predictions.</p><table class="table-platform w-100"><thead><tr><th>Applicant ID</th><th>Approval Prob.</th><th>Risk Score</th><th>Category</th></tr></thead><tbody>' + rows + '</tbody></table>';
  },

  async getSegments() {
    const datasetId = DatasetStore.getSelected();
    if (!datasetId) { Utils.toast('Please select a dataset from the dropdown above.', 'warning'); return; }
    Utils.setLoading(true, 'Computing segments...');
    try {
      const data = await Utils.post('/ml/segments', { dataset_id: datasetId });
      Utils.toast(data.num_clusters + ' segments found.', 'success');
      const container = document.getElementById('ml-batch-results');
      if (container) {
        let rows = '';
        Object.keys(data.cluster_profiles || {}).forEach(function(k) {
          const v = data.cluster_profiles[k];
          rows += '<tr><td>' + k + '</td><td>' + v.size + '</td><td>' + v.pct + '%</td></tr>';
        });
        container.innerHTML = '<p class="small text-muted mb-2">' + data.num_clusters + ' applicant segments</p><table class="table-platform w-100"><thead><tr><th>Segment</th><th>Size</th><th>%</th></tr></thead><tbody>' + rows + '</tbody></table>';
      }
    } catch (err) { Utils.toast(err.message, 'danger'); }
    finally { Utils.setLoading(false); }
  },

  async getAnomalies() {
    const datasetId = DatasetStore.getSelected();
    if (!datasetId) { Utils.toast('Please select a dataset from the dropdown above.', 'warning'); return; }
    Utils.setLoading(true, 'Detecting anomalies...');
    try {
      const data = await Utils.post('/ml/anomalies', { dataset_id: datasetId });
      Utils.toast(data.anomaly_count + ' anomalies detected.', 'warning');
      const container = document.getElementById('ml-batch-results');
      if (container) container.innerHTML = '<div class="alert alert-warning small"><strong>' + data.anomaly_count + ' anomalous records</strong> out of ' + data.total_records + ' total (' + ((data.anomaly_count / data.total_records) * 100).toFixed(1) + '%)</div>';
    } catch (err) { Utils.toast(err.message, 'danger'); }
    finally { Utils.setLoading(false); }
  }
};

// =============================================================================
// REPORTS
// =============================================================================
const Reports = {
  async download(type) {
    const datasetId = DatasetStore.getSelected();
    const fmtEl     = document.getElementById('report-format');
    const format    = fmtEl ? fmtEl.value : 'pdf';
    if (!datasetId) { Utils.toast('Please select a dataset from the dropdown above.', 'warning'); return; }
    Utils.setLoading(true, 'Generating ' + type + ' report...');
    try {
      const resp = await fetch(API_BASE_URL + '/reports/' + type + '?format=' + format, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ dataset_id: datasetId })
      });
      if (!resp.ok) throw new Error('Report generation failed: ' + resp.status);
      const blob = await resp.blob();
      const url  = URL.createObjectURL(blob);
      const a    = document.createElement('a');
      a.href = url; a.download = type + '_report.' + format;
      document.body.appendChild(a); a.click(); document.body.removeChild(a);
      URL.revokeObjectURL(url);
      Utils.toast(type + ' report downloaded!', 'success');
    } catch (err) { Utils.toast(err.message, 'danger'); }
    finally { Utils.setLoading(false); }
  }
};

// =============================================================================
// MONITORING
// =============================================================================
const Monitoring = {
  async load() {
    try {
      const data = await fetch('http://localhost:8001/monitoring/dashboard').then(function(r) { return r.json(); });
      const tq = document.getElementById('mon-total-queries');
      const rt = document.getElementById('mon-avg-rt');
      const fs = document.getElementById('mon-avg-fairness');
      const al = document.getElementById('mon-open-alerts');
      if (tq) tq.textContent = data.total_queries != null ? data.total_queries : 0;
      if (rt) rt.textContent = data.average_response_time_seconds != null ? data.average_response_time_seconds.toFixed(2) + 's' : '—';
      if (fs) fs.textContent = data.average_fairness_score != null ? data.average_fairness_score.toFixed(1) : '—';
      if (al) al.textContent = (data.recent_alerts || []).filter(function(a) { return !a.resolved; }).length;
      const qvol = data.query_volume_by_hour || {};
      UI.createLineChart('chart-query-volume', Object.keys(qvol), Object.values(qvol), 'Queries');
      const ftrend = data.fairness_score_trend || [];
      UI.createLineChart('chart-fairness-trend', ftrend.map(function(_, i) { return i + 1; }), ftrend.map(function(f) { return f.score || 0; }), 'Fairness Score');
      const alerts = data.recent_alerts || [];
      const ac = document.getElementById('alerts-table-container');
      if (ac) {
        if (!alerts.length) { ac.innerHTML = '<p class="text-muted small p-3 mb-0">No alerts.</p>'; return; }
        let rows = '';
        alerts.forEach(function(a) {
          const sc = a.severity === 'critical' ? 'bg-danger' : a.severity === 'warning' ? 'bg-warning text-dark' : 'bg-info';
          rows += '<tr><td>' + Utils.escHtml(a.alert_type) + '</td><td><span class="badge ' + sc + '">' + a.severity + '</span></td><td>' + Utils.escHtml(a.message) + '</td><td>' + new Date(a.timestamp).toLocaleTimeString() + '</td></tr>';
        });
        ac.innerHTML = '<table class="table-platform w-100"><thead><tr><th>Type</th><th>Severity</th><th>Message</th><th>Time</th></tr></thead><tbody>' + rows + '</tbody></table>';
      }
    } catch (_e) {}
  }
};

// =============================================================================
// SETTINGS
// =============================================================================
const Settings = {
  async init() {
    try {
      const status = await Utils.get('/ai/status');
      Settings._updateUI(status);
    } catch (_e) {}
  },

  _updateUI(status) {
    const gBadge   = document.getElementById('gemini-status-badge');
    const oBadge   = document.getElementById('openai-status-badge');
    const banner   = document.getElementById('ai-status-banner');
    const provInfo = document.getElementById('active-provider-info');
    if (gBadge) { gBadge.textContent = status.gemini_configured ? '✓ Configured (' + status.gemini_key_source + ')' : 'Not Configured'; gBadge.className = 'badge ' + (status.gemini_configured ? 'bg-success' : 'bg-secondary'); }
    if (oBadge) { oBadge.textContent = status.openai_configured  ? '✓ Configured (' + status.openai_key_source  + ')' : 'Not Configured'; oBadge.className = 'badge ' + (status.openai_configured  ? 'bg-success' : 'bg-secondary'); }
    const any = status.gemini_configured || status.openai_configured;
    if (banner) {
      if (any) { banner.className = 'alert alert-success d-flex align-items-center gap-2 mb-4'; banner.innerHTML = '<i class="fa-solid fa-circle-check"></i><span>AI provider active: <strong>' + status.active_provider.toUpperCase() + '</strong> — model: <strong>' + status.active_model + '</strong></span>'; }
      else      { banner.className = 'alert alert-warning d-flex align-items-center gap-2 mb-4'; banner.innerHTML = '<i class="fa-solid fa-triangle-exclamation"></i><span>No AI provider configured. Add an API key below to enable AI-powered features.</span>'; }
    }
    if (provInfo && any) {
      provInfo.innerHTML = '<div class="row g-3"><div class="col-md-4"><div class="metric-card text-center"><div class="metric-label">Active Provider</div><div class="metric-value" style="font-size:1.2rem">' + status.active_provider.toUpperCase() + '</div></div></div><div class="col-md-4"><div class="metric-card text-center"><div class="metric-label">Active Model</div><div class="metric-value" style="font-size:1rem">' + (status.active_model || '—') + '</div></div></div><div class="col-md-4"><div class="metric-card text-center"><div class="metric-label">Keys Stored</div><div class="metric-value" style="font-size:1.2rem">' + ((status.gemini_configured ? 1 : 0) + (status.openai_configured ? 1 : 0)) + '</div></div></div></div>';
    }
  },

  async saveKey(provider) {
    const keyEl   = document.getElementById(provider + '-api-key');
    const modelEl = document.getElementById(provider + '-model');
    const key     = keyEl   ? keyEl.value.trim()   : '';
    const model   = modelEl ? modelEl.value         : '';
    if (!key) { Utils.toast('Please enter an API key.', 'warning'); return; }
    Utils.setLoading(true, 'Saving ' + provider + ' API key...');
    try {
      const data = await Utils.post('/ai/config', { provider: provider, api_key: key, model: model, set_active: true });
      Utils.toast(provider.toUpperCase() + ' key saved. Active: ' + data.provider + ' / ' + data.model, 'success');
      if (keyEl) keyEl.value = '';
      await Settings.init();
    } catch (err) { Utils.toast(err.message, 'danger'); }
    finally { Utils.setLoading(false); }
  },

  async testKey(provider) {
    const resultEl = document.getElementById(provider + '-test-result');
    if (resultEl) resultEl.innerHTML = '<div class="spinner-border spinner-border-sm text-primary"></div> Testing...';
    try {
      const data = await Utils.post('/ai/test', { provider: provider });
      if (resultEl) resultEl.innerHTML = '<div class="alert alert-success py-1 small mt-1">✓ Connected! Response: <em>' + Utils.escHtml(data.response.slice(0, 80)) + '</em></div>';
      Utils.toast(provider.toUpperCase() + ' connection successful!', 'success');
    } catch (err) {
      if (resultEl) resultEl.innerHTML = '<div class="alert alert-danger py-1 small mt-1">✗ ' + Utils.escHtml(err.message) + '</div>';
      Utils.toast(err.message, 'danger');
    }
  },

  async clearKey(provider) {
    try {
      await Utils.request('/ai/config/' + provider, { method: 'DELETE' });
      Utils.toast(provider.toUpperCase() + ' key removed.', 'info');
      await Settings.init();
    } catch (err) { Utils.toast(err.message, 'danger'); }
  },

  toggleVisibility(inputId) {
    const el = document.getElementById(inputId);
    if (el) el.type = el.type === 'password' ? 'text' : 'password';
  }
};

// =============================================================================
// BOOT
// =============================================================================
document.addEventListener('DOMContentLoaded', function() {
  UI.init();
  Settings.init();
  UI.navigate('home');
});
