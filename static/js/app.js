/* ============================================================
   SentrySpeed — app.js  (Professional Dashboard)
   ============================================================ */
'use strict';

// ── App State ─────────────────────────────────────────────────
const AppState = {
  currentVideoId: null,
  pollerTimer:    null,
  allVehicles:    [],
  filterMode:     'all',
  sortKey:        null,
  sortAsc:        true,
  prevKPIs:       {},
};

// ── API ───────────────────────────────────────────────────────
const API = {
  async upload(file) {
    const fd = new FormData();
    fd.append('file', file);
    const r = await fetch('/api/upload', { method: 'POST', body: fd });
    if (!r.ok) throw new Error((await r.json()).detail || 'Upload failed');
    return r.json();
  },
  async status(id)   { return (await fetch(`/api/status/${id}`)).json(); },
  async results(id)  { return (await fetch(`/api/results/${id}`)).json(); },
  async vehicles(id) { return (await fetch(`/api/vehicles/${id}`)).json(); },
  async videos()     { return (await fetch('/api/videos')).json(); },
  async startCamera(src) {
    return (await fetch(`/api/camera/start?camera_source=${encodeURIComponent(src)}`, { method:'POST' })).json();
  },
  async stopCamera() { return (await fetch('/api/camera/stop', { method:'POST' })).json(); },
  async cameraStats(){ return (await fetch('/api/camera/stats')).json(); },
};

// ── Toast ─────────────────────────────────────────────────────
const Toast = {
  show(msg, type='info', ms=4000) {
    const c = document.getElementById('toastContainer');
    const t = document.createElement('div');
    t.className = `toast toast-${type}`;
    t.textContent = msg;
    c.appendChild(t);
    setTimeout(() => {
      t.style.cssText = 'opacity:0;transform:translateX(30px);transition:all .3s ease';
      setTimeout(() => t.remove(), 300);
    }, ms);
  },
  ok(m)   { this.show(m,'success'); },
  err(m)  { this.show(m,'error'); },
  info(m) { this.show(m,'info'); },
};

// ── Animated Counter ──────────────────────────────────────────
function animateTo(id, target, suffix='') {
  const el = document.getElementById(id);
  if (!el) return;
  const start = parseFloat(el.textContent) || 0;
  const diff  = target - start;
  const steps = 30;
  let s = 0;
  const t = setInterval(() => {
    s++;
    el.textContent = Math.round(start + diff * (s/steps)) + suffix;
    if (s >= steps) { el.textContent = target + suffix; clearInterval(t); }
  }, 16);
}

function updateKPIs(data) {
  const prev = AppState.prevKPIs || {};

  const vals = {
    totalVehiclesVal: data.total_vehicles || 0,
    avgSpeedVal:      Math.round(data.avg_speed || 0),
    overspeedVal:     data.overspeed_count || 0,
    platesVal:        data.vehicles_with_plates ?? data.plates_detected ?? 0,
  };

  animateTo('totalVehiclesVal', vals.totalVehiclesVal);
  animateTo('avgSpeedVal',      vals.avgSpeedVal);
  animateTo('overspeedVal',     vals.overspeedVal);
  animateTo('platesVal',        vals.platesVal);

  // Trend indicators
  const trends = [
    ['trendVehicles', vals.totalVehiclesVal, prev.totalVehiclesVal, false],
    ['trendSpeed',    vals.avgSpeedVal,      prev.avgSpeedVal,      false],
    ['trendPlates',   vals.platesVal,        prev.platesVal,        false],
    ['trendOverspeed',vals.overspeedVal,     prev.overspeedVal,     true],
  ];
  trends.forEach(([id, cur, old, isDanger]) => {
    const el = document.getElementById(id);
    if (!el || old === undefined) return;
    const diff = cur - old;
    if (diff === 0) { el.classList.remove('visible'); return; }
    el.textContent = (diff > 0 ? '↑ +' : '↓ ') + Math.abs(diff);
    el.style.color = isDanger ? (diff > 0 ? 'var(--red)' : 'var(--green)') : (diff > 0 ? 'var(--green)' : 'var(--text2)');
    el.classList.add('visible');
  });

  // Overspeed card pulse
  const card = document.getElementById('kpiOverspeedCard');
  if (card) {
    if (vals.overspeedVal > 0) card.classList.add('has-overspeed');
    else card.classList.remove('has-overspeed');
  }

  AppState.prevKPIs = vals;
}

// ── Tab Manager ───────────────────────────────────────────────
const TabManager = {
  show(name) {
    document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
    document.querySelectorAll('.tab-btn').forEach(b => { b.classList.remove('active'); b.setAttribute('aria-selected','false'); });
    const panel = document.getElementById(`panel${name[0].toUpperCase()+name.slice(1)}`);
    const btn   = document.getElementById(`tab${name[0].toUpperCase()+name.slice(1)}`);
    if (panel) panel.classList.add('active');
    if (btn)   { btn.classList.add('active'); btn.setAttribute('aria-selected','true'); }
    if (name === 'history') HistoryManager.refresh();
  },
};

// ── File Uploader ─────────────────────────────────────────────
const FileUploader = {
  onDragOver(e)  { e.preventDefault(); document.getElementById('dropZone').classList.add('dragover'); },
  onDragLeave()  { document.getElementById('dropZone').classList.remove('dragover'); },
  onDrop(e) {
    e.preventDefault();
    document.getElementById('dropZone').classList.remove('dragover');
    const f = e.dataTransfer.files[0];
    if (f) this._upload(f);
  },
  onFileSelect(e) { const f = e.target.files[0]; if (f) this._upload(f); },

  async _upload(file) {
    const block = document.getElementById('uploadProgress');
    const txt   = document.getElementById('uploadStatusText');
    const pct   = document.getElementById('uploadPct');
    const bar   = document.getElementById('uploadBar');

    block.classList.remove('hidden');
    txt.textContent = `Uploading ${file.name}…`;

    let fp = 0;
    const ft = setInterval(() => {
      fp = Math.min(fp + 8, 90);
      bar.style.width = fp + '%';
      pct.textContent = fp + '%';
    }, 100);

    try {
      const res = await API.upload(file);
      clearInterval(ft);
      bar.style.width = '100%'; pct.textContent = '100%';
      txt.textContent = '✓ Uploaded — processing started';
      Toast.ok(`"${file.name}" uploaded (ID: ${res.video_id})`);
      AppState.currentVideoId = res.video_id;
      const badge = document.getElementById('resultVideoId');
      if (badge) badge.textContent = `#${res.video_id}`;
      setTimeout(() => { block.classList.add('hidden'); StatusPoller.start(res.video_id); }, 800);
    } catch (err) {
      clearInterval(ft);
      bar.style.width = '100%'; bar.style.background = 'var(--red)';
      txt.textContent = '✗ Upload failed';
      Toast.err(`Upload failed: ${err.message}`);
    }
  },
};

// ── Status Poller ─────────────────────────────────────────────
const StatusPoller = {
  start(id) {
    if (AppState.pollerTimer) clearInterval(AppState.pollerTimer);
    const block = document.getElementById('procProgress');
    const txt   = document.getElementById('procStatusText');
    const pct   = document.getElementById('procPct');
    const bar   = document.getElementById('procBar');

    block.classList.remove('hidden');
    txt.textContent = 'Processing…';

    AppState.pollerTimer = setInterval(async () => {
      try {
        const d = await API.status(id);
        const p = Math.min(d.progress || 0, 100);
        bar.style.width = p + '%';
        pct.textContent = p + '%';
        txt.textContent = `${d.status} — ${p}%`;

        // Live KPI update while processing (partial results)
        if (d.status === 'processing' && d.total_vehicles > 0) {
          updateKPIs({ total_vehicles: d.total_vehicles, avg_speed: 0, overspeed_count: 0, plates_detected: 0 });
        }

        if (d.status === 'completed') {
          clearInterval(AppState.pollerTimer);
          txt.textContent = '✓ Completed!';
          Toast.ok(`Video #${id} processing complete!`);
          await ResultsRenderer.load(id);
          const dr = document.getElementById('downloadRow');
          if (dr) dr.style.display = 'flex';
        } else if (d.status === 'failed') {
          clearInterval(AppState.pollerTimer);
          txt.textContent = '✗ Processing failed';
          Toast.err(`Video #${id} processing failed.`);
        }
      } catch { /* retry */ }
    }, 2000);
  },
};

// ── Table Filter / Sort / Search ──────────────────────────────
const TableFilter = {
  set(mode) {
    AppState.filterMode = mode;
    document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
    const map = { all:'filterAll', overspeed:'filterOverspeed', normal:'filterNormal' };
    const btn = document.getElementById(map[mode]);
    if (btn) btn.classList.add('active');
    this.apply();
  },

  sort(key) {
    if (AppState.sortKey === key) AppState.sortAsc = !AppState.sortAsc;
    else { AppState.sortKey = key; AppState.sortAsc = true; }
    this.apply();
  },

  apply() {
    let list = [...AppState.allVehicles];

    // Filter by status
    if (AppState.filterMode === 'overspeed') list = list.filter(v => v.status === 'overspeed');
    if (AppState.filterMode === 'normal')    list = list.filter(v => v.status !== 'overspeed');

    // Search by plate or vehicle ID
    const q = (document.getElementById('plateSearch')?.value || '').trim().toUpperCase();
    if (q) list = list.filter(v =>
      (v.plate_number || '').toUpperCase().includes(q) ||
      String(v.vehicle_unique_id).includes(q)
    );

    // Sort
    if (AppState.sortKey) {
      const keyMap = { id:'vehicle_unique_id', type:'vehicle_type', avg:'avg_speed', max:'max_speed' };
      const k = keyMap[AppState.sortKey];
      list.sort((a,b) => {
        const av = a[k], bv = b[k];
        if (typeof av === 'number') return AppState.sortAsc ? av-bv : bv-av;
        return AppState.sortAsc ? String(av).localeCompare(String(bv)) : String(bv).localeCompare(String(av));
      });
    }

    this._render(list);
  },

  _render(vehicles) {
    const tbody = document.getElementById('vehicleTableBody');
    if (!vehicles || vehicles.length === 0) {
      tbody.innerHTML = '<tr><td colspan="6" class="empty-row">No vehicles match the current filter.</td></tr>';
      return;
    }
    tbody.innerHTML = vehicles.map(v => {
      const over = v.status === 'overspeed';
      const badge = over
        ? '<span class="badge-overspeed">⚠ Overspeed</span>'
        : '<span class="badge-normal">✓ Normal</span>';
      return `<tr class="${over ? 'row-over' : ''}">
        <td>${v.vehicle_unique_id}</td>
        <td>${v.vehicle_type}</td>
        <td>${v.plate_number || '—'}</td>
        <td>${(v.avg_speed||0).toFixed(1)} km/h</td>
        <td>${(v.max_speed||0).toFixed(1)} km/h</td>
        <td>${badge}</td>
      </tr>`;
    }).join('');
  },
};

// ── Video Preview ─────────────────────────────────────────────
const VideoPreview = {
  show(videoId) {
    const section = document.getElementById('videoPreview');
    const player  = document.getElementById('processedVideo');
    if (!section || !player) return;
    player.src = `/api/download/video/${videoId}`;
    section.classList.remove('hidden');
  },
  hide() {
    const section = document.getElementById('videoPreview');
    const player  = document.getElementById('processedVideo');
    if (section) section.classList.add('hidden');
    if (player)  { player.pause(); player.src = ''; }
  },
  toggle() {
    const player = document.getElementById('processedVideo');
    if (!player) return;
    if (player.style.maxHeight === 'none') {
      player.style.maxHeight = '280px';
    } else {
      player.style.maxHeight = 'none';
    }
  },
};

// ── Results Renderer ──────────────────────────────────────────
const ResultsRenderer = {
  async load(id) {
    try {
      const [analytics, vehicles] = await Promise.all([API.results(id), API.vehicles(id)]);
      this._fillCards(analytics);
      AppState.allVehicles = vehicles || [];
      TableFilter.apply();
      updateKPIs(analytics);
      // Show video preview
      VideoPreview.show(id);
    } catch (err) {
      Toast.err('Failed to load results: ' + err.message);
    }
  },

  _fillCards(a) {
    const s = (id, v) => { const el = document.getElementById(id); if (el) el.textContent = v; };
    s('anaCars',     a.cars || 0);
    s('anaTrucks',   a.trucks || 0);
    s('anaBuses',    a.buses || 0);
    s('anaBikes',    a.bikes || 0);
    s('anaOverPct',  (a.overspeed_percentage || 0).toFixed(1) + '%');
    s('anaMaxSpeed', (a.max_speed || 0).toFixed(1) + ' km/h');
  },
};

// ── History Manager ───────────────────────────────────────────
const HistoryManager = {
  async refresh() {
    const list = document.getElementById('historyList');
    list.innerHTML = '<p class="empty-hint">Loading…</p>';
    try {
      const videos = await API.videos();
      if (!videos || !videos.length) {
        list.innerHTML = '<p class="empty-hint">No videos processed yet.</p>';
        return;
      }
      list.innerHTML = videos.map(v => `
        <div class="history-item" onclick="HistoryManager.select(${v.video_id})" role="button" tabindex="0">
          <div>
            <div class="h-filename">${v.filename}</div>
            <div class="h-meta">${v.upload_time?.split('T')[0] ?? ''} · ${v.total_vehicles ?? 0} vehicles</div>
          </div>
          <span class="${v.status==='completed'?'badge-normal':'badge-overspeed'}">${v.status}</span>
        </div>`).join('');
    } catch {
      list.innerHTML = '<p class="empty-hint">Failed to load history.</p>';
    }
  },

  async select(id) {
    AppState.currentVideoId = id;
    const badge = document.getElementById('resultVideoId');
    if (badge) badge.textContent = `#${id}`;
    TabManager.show('upload');
    await ResultsRenderer.load(id);
    const dr = document.getElementById('downloadRow');
    if (dr) dr.style.display = 'flex';
    Toast.info(`Loaded results for video #${id}`);
  },
};

// ── Camera Manager ────────────────────────────────────────────
const CameraManager = {
  _streamTimer: null,
  _statsTimer:  null,
  _maxSpeed:    0,
  isStreaming:  false,

  async start() {
    try {
      const src = document.getElementById('cameraSource').value || '0';
      await API.startCamera(src);
      document.getElementById('cameraStream').classList.remove('hidden');
      document.getElementById('cameraPlaceholder').classList.add('hidden');
      document.getElementById('btnStartCam').disabled = true;
      document.getElementById('btnStopCam').disabled  = false;
      this.isStreaming = true;
      this._startFramePolling();
      this._startStatsPolling();
      Toast.ok('Camera started: ' + src);
    } catch (err) { Toast.err('Camera failed: ' + err.message); }
  },

  _startFramePolling() {
    if (this._streamTimer) clearInterval(this._streamTimer);
    this._streamTimer = setInterval(async () => {
      if (!this.isStreaming) return;
      try {
        const r = await fetch('/api/camera/frame?t=' + Date.now());
        if (r.ok) {
          const blob = await r.blob();
          document.getElementById('cameraStream').src = URL.createObjectURL(blob);
        }
      } catch {}
    }, 50);
  },

  _startStatsPolling() {
    if (this._statsTimer) clearInterval(this._statsTimer);
    this._statsTimer = setInterval(async () => {
      if (!this.isStreaming) return;
      try {
        const r = await API.cameraStats();
        if (!r.data) return;
        const s = r.data;
        updateKPIs({ total_vehicles: s.total_vehicles||0, avg_speed: s.avg_speed||0, overspeed_count: s.overspeed_count||0, plates_detected: s.plates_detected||0 });
        const set = (id,v) => { const el=document.getElementById(id); if(el) el.textContent=v; };
        set('anaCars',    s.cars||0);
        set('anaTrucks',  s.trucks||0);
        set('anaBuses',   s.buses||0);
        set('anaBikes',   s.bikes||0);
        set('anaOverPct', s.total_vehicles>0 ? ((s.overspeed_count/s.total_vehicles)*100).toFixed(1)+'%' : '0.0%');
        if ((s.avg_speed||0) > this._maxSpeed) this._maxSpeed = s.avg_speed;
        set('anaMaxSpeed', this._maxSpeed.toFixed(1)+' km/h');
      } catch {}
    }, 500);
  },

  async stop() {
    this.isStreaming = false;
    this._maxSpeed = 0;
    [this._streamTimer, this._statsTimer].forEach(t => { if(t) clearInterval(t); });
    this._streamTimer = this._statsTimer = null;
    await API.stopCamera();
    const img = document.getElementById('cameraStream');
    img.src = ''; img.classList.add('hidden');
    document.getElementById('cameraPlaceholder').classList.remove('hidden');
    document.getElementById('btnStartCam').disabled = false;
    document.getElementById('btnStopCam').disabled  = true;
    Toast.info('Camera stopped.');
  },
};

// ── Downloader ────────────────────────────────────────────────
const Downloader = {
  excel() {
    const id = AppState.currentVideoId;
    if (!id) { Toast.err('No video selected.'); return; }
    window.open(`/api/download/excel/${id}`, '_blank');
  },
  video() {
    const id = AppState.currentVideoId;
    if (!id) { Toast.err('No video selected.'); return; }
    window.open(`/api/download/video/${id}`, '_blank');
  },
};

// ── Model Metrics ─────────────────────────────────────────────
const MetricsUI = {
  showChart(name) {
    document.querySelectorAll('.chart-img').forEach(i => i.classList.remove('active'));
    document.querySelectorAll('.ctab').forEach(b => b.classList.remove('active'));
    const map    = { results:'chartResults', loss:'chartLoss', map:'chartMap', pr:'chartPr' };
    const tabMap = { results:'ctabResults',  loss:'ctabLoss',  map:'ctabMap',  pr:'ctabPr'  };
    document.getElementById(map[name])?.classList.add('active');
    document.getElementById(tabMap[name])?.classList.add('active');
  },

  async load() {
    try {
      const d = await (await fetch('/api/model-metrics')).json();
      if (!d.available) return;
      const badge = document.getElementById('metricsBestEpoch');
      if (badge) badge.textContent = `Best: Epoch ${d.best_epoch} / ${d.total_epochs}`;
      const b = d.best;
      [
        ['mPrecision','mPrecisionBar', b.precision],
        ['mRecall',   'mRecallBar',    b.recall],
        ['mMap50',    'mMap50Bar',     b.mAP50],
        ['mMap5095',  'mMap5095Bar',   b.mAP50_95],
      ].forEach(([vid, bid, val]) => {
        const el  = document.getElementById(vid);
        const bar = document.getElementById(bid);
        if (el)  el.textContent = (val*100).toFixed(1) + '%';
        if (bar) setTimeout(() => bar.style.width = (val*100).toFixed(1)+'%', 300);
      });
    } catch (e) { console.warn('Metrics load failed:', e.message); }
  },
};

// ── Init ──────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  // Health check
  fetch('/api/health').then(r=>r.json()).then(d => {
    const el = document.getElementById('systemStatus');
    if (!el) return;
    if (d.status === 'ok') {
      el.querySelector('.status-text').textContent = 'ONLINE';
    } else {
      el.querySelector('.status-dot').style.background = 'var(--red)';
      el.querySelector('.status-text').textContent = 'OFFLINE';
      el.style.color = 'var(--red)';
    }
  }).catch(() => {
    const el = document.getElementById('systemStatus');
    if (el) {
      el.querySelector('.status-dot').style.background = 'var(--red)';
      el.querySelector('.status-text').textContent = 'OFFLINE';
      el.style.color = 'var(--red)';
    }
  });

  // Load model metrics
  MetricsUI.load();
});
