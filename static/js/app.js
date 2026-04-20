/* ============================================================
   SentrySpeed — app.js
   Modular JS: TabManager · FileUploader · StatusPoller ·
               ResultsRenderer · CameraManager · HistoryManager ·
               Downloader · StatsAnimator · NotificationSystem
   ============================================================ */

'use strict';

// ── State ──────────────────────────────────────────────────────
const AppState = {
  currentVideoId: null,
  pollerTimer:    null,
};

// ── API helpers ────────────────────────────────────────────────
const API = {
  async upload(file) {
    const fd = new FormData();
    fd.append('file', file);
    const resp = await fetch('/api/upload', { method: 'POST', body: fd });
    if (!resp.ok) throw new Error((await resp.json()).detail || 'Upload failed');
    return resp.json();
  },
  async status(videoId)   { return (await fetch(`/api/status/${videoId}`)).json(); },
  async results(videoId)  { return (await fetch(`/api/results/${videoId}`)).json(); },
  async vehicles(videoId) { return (await fetch(`/api/vehicles/${videoId}`)).json(); },
  async videos()          { return (await fetch('/api/videos')).json(); },
  async startCamera(source = '0') { 
    const url = `/api/camera/start?camera_source=${encodeURIComponent(source)}`;
    return (await fetch(url, { method: 'POST' })).json(); 
  },
  async stopCamera()      { return (await fetch('/api/camera/stop', { method: 'POST' })).json(); },
  async cameraStats()     { return (await fetch('/api/camera/stats')).json(); },
};

// ── Toast Notifications ───────────────────────────────────────
const NotificationSystem = {
  show(message, type = 'info', duration = 4000) {
    const container = document.getElementById('toastContainer');
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.textContent = message;
    container.appendChild(toast);
    setTimeout(() => {
      toast.style.opacity = '0';
      toast.style.transform = 'translateX(30px)';
      toast.style.transition = 'all 0.3s ease';
      setTimeout(() => toast.remove(), 300);
    }, duration);
  },
  success(msg) { this.show(msg, 'success'); },
  error(msg)   { this.show(msg, 'error'); },
  info(msg)    { this.show(msg, 'info'); },
};

// ── Stats Animator ────────────────────────────────────────────
const StatsAnimator = {
  animateTo(elId, target, suffix = '') {
    const el = document.getElementById(elId);
    if (!el) return;
    const start = parseInt(el.textContent) || 0;
    const diff  = target - start;
    const steps = 30;
    let step = 0;
    const timer = setInterval(() => {
      step++;
      el.textContent = Math.round(start + diff * (step / steps)) + suffix;
      if (step >= steps) {
        el.textContent = target + suffix;
        clearInterval(timer);
      }
    }, 16);
  },
  update(analytics) {
    this.animateTo('totalVehiclesVal', analytics.total_vehicles);
    this.animateTo('avgSpeedVal', Math.round(analytics.avg_speed || 0));
    this.animateTo('overspeedVal', analytics.overspeed_count);
    // Count plates: vehicles with non-null plates
    const plates = analytics.vehicles_with_plates || 0;
    this.animateTo('platesVal', plates);
  },
};

// ── Tab Manager ───────────────────────────────────────────────
const TabManager = {
  show(tabName) {
    const panels = document.querySelectorAll('.tab-panel');
    const buttons = document.querySelectorAll('.tab-btn');
    panels.forEach(p => p.classList.remove('active'));
    buttons.forEach(b => { b.classList.remove('active'); b.setAttribute('aria-selected', 'false'); });

    const panel = document.getElementById(`panel${tabName.charAt(0).toUpperCase() + tabName.slice(1)}`);
    const btn   = document.getElementById(`tab${tabName.charAt(0).toUpperCase() + tabName.slice(1)}`);
    if (panel) panel.classList.add('active');
    if (btn) { btn.classList.add('active'); btn.setAttribute('aria-selected', 'true'); }

    if (tabName === 'history') HistoryManager.refresh();
  },
};

// ── File Uploader ─────────────────────────────────────────────
const FileUploader = {
  onDragOver(e) {
    e.preventDefault();
    document.getElementById('dropZone').classList.add('dragover');
  },
  onDragLeave()  { document.getElementById('dropZone').classList.remove('dragover'); },
  onDrop(e) {
    e.preventDefault();
    document.getElementById('dropZone').classList.remove('dragover');
    const file = e.dataTransfer.files[0];
    if (file) this._upload(file);
  },
  onFileSelect(e) {
    const file = e.target.files[0];
    if (file) this._upload(file);
  },

  async _upload(file) {
    const uploadBlock = document.getElementById('uploadProgress');
    const statusText  = document.getElementById('uploadStatusText');
    const pct         = document.getElementById('uploadPct');
    const bar         = document.getElementById('uploadBar');

    uploadBlock.classList.remove('hidden');
    statusText.textContent = `Uploading ${file.name}…`;

    // Fake upload progress (real progress via XHR would need more setup)
    let fakeProgress = 0;
    const fakeTimer = setInterval(() => {
      fakeProgress = Math.min(fakeProgress + 8, 90);
      bar.style.width  = fakeProgress + '%';
      pct.textContent  = fakeProgress + '%';
    }, 100);

    try {
      const result = await API.upload(file);
      clearInterval(fakeTimer);
      bar.style.width = '100%';
      pct.textContent = '100%';
      statusText.textContent = '✓ Uploaded — processing started';

      NotificationSystem.success(`"${file.name}" uploaded. Processing started (ID: ${result.video_id})`);
      AppState.currentVideoId = result.video_id;
      document.getElementById('resultVideoId').textContent = `#${result.video_id}`;

      setTimeout(() => {
        uploadBlock.classList.add('hidden');
        StatusPoller.start(result.video_id);
      }, 800);

    } catch (err) {
      clearInterval(fakeTimer);
      bar.style.width = '100%';
      bar.style.background = 'var(--accent-red)';
      statusText.textContent = '✗ Upload failed';
      NotificationSystem.error(`Upload failed: ${err.message}`);
    }
  },
};

// ── Status Poller ─────────────────────────────────────────────
const StatusPoller = {
  start(videoId) {
    if (AppState.pollerTimer) clearInterval(AppState.pollerTimer);
    const procBlock   = document.getElementById('procProgress');
    const procStatus  = document.getElementById('procStatusText');
    const procPct     = document.getElementById('procPct');
    const procBar     = document.getElementById('procBar');

    procBlock.classList.remove('hidden');
    procStatus.textContent = 'Processing…';

    AppState.pollerTimer = setInterval(async () => {
      try {
        const data = await API.status(videoId);
        const progress = Math.min(data.progress || 0, 100);
        procBar.style.width = progress + '%';
        procPct.textContent = progress + '%';
        procStatus.textContent = `${data.status} — ${progress}%`;

        if (data.status === 'completed') {
          clearInterval(AppState.pollerTimer);
          procStatus.textContent = '✓ Completed!';
          NotificationSystem.success(`Video #${videoId} processing complete!`);
          await ResultsRenderer.load(videoId);
          document.getElementById('downloadRow').style.display = 'flex';
        } else if (data.status === 'failed') {
          clearInterval(AppState.pollerTimer);
          procStatus.textContent = '✗ Processing failed';
          NotificationSystem.error(`Video #${videoId} processing failed.`);
        }
      } catch { /* silently retry */ }
    }, 2000);
  },
};

// ── Results Renderer ──────────────────────────────────────────
const ResultsRenderer = {
  async load(videoId) {
    try {
      const [analytics, vehicles] = await Promise.all([
        API.results(videoId),
        API.vehicles(videoId),
      ]);

      this._fillAnalytics(analytics);
      this._fillTable(vehicles);
      StatsAnimator.update(analytics);
    } catch (err) {
      NotificationSystem.error('Failed to load results: ' + err.message);
    }
  },

  _fillAnalytics(a) {
    const set = (id, val) => { const el = document.getElementById(id); if (el) el.textContent = val; };
    set('anaCars',     a.cars || 0);
    set('anaTrucks',   a.trucks || 0);
    set('anaBuses',    a.buses || 0);
    set('anaBikes',    a.bikes || 0);
    set('anaOverPct',  (a.overspeed_percentage || 0).toFixed(1) + '%');
    set('anaMaxSpeed', (a.max_speed || 0).toFixed(1) + ' km/h');
  },

  _fillTable(vehicles) {
    const tbody = document.getElementById('vehicleTableBody');
    if (!vehicles || vehicles.length === 0) {
      tbody.innerHTML = '<tr><td colspan="6" class="empty-row">No vehicles detected.</td></tr>';
      return;
    }

    tbody.innerHTML = vehicles.map(v => {
      const isOver = v.status === 'overspeed';
      const statusBadge = isOver
        ? '<span class="status-badge status-overspeed">⚠ Overspeed</span>'
        : '<span class="status-badge status-normal">✓ Normal</span>';
      return `
        <tr class="${isOver ? 'row-overspeed' : ''}">
          <td>${v.vehicle_unique_id}</td>
          <td>${v.vehicle_type}</td>
          <td>${v.plate_number || '—'}</td>
          <td>${(v.avg_speed || 0).toFixed(1)} km/h</td>
          <td>${(v.max_speed || 0).toFixed(1)} km/h</td>
          <td>${statusBadge}</td>
        </tr>`;
    }).join('');
  },
};

// ── History Manager ───────────────────────────────────────────
const HistoryManager = {
  async refresh() {
    const list = document.getElementById('historyList');
    list.innerHTML = '<p class="muted">Loading…</p>';
    try {
      const videos = await API.videos();
      if (!videos || videos.length === 0) {
        list.innerHTML = '<p class="muted">No videos processed yet.</p>';
        return;
      }
      list.innerHTML = videos.map(v => `
        <div class="history-item" onclick="HistoryManager.select(${v.video_id})" role="button" tabindex="0">
          <div>
            <div class="h-filename">${v.filename}</div>
            <div class="h-meta">${v.upload_time?.split('T')[0] ?? ''} · ${v.total_vehicles ?? 0} vehicles</div>
          </div>
          <span class="status-badge ${v.status === 'completed' ? 'status-normal' : 'status-overspeed'}">${v.status}</span>
        </div>`).join('');
    } catch {
      list.innerHTML = '<p class="muted">Failed to load history.</p>';
    }
  },

  async select(videoId) {
    AppState.currentVideoId = videoId;
    document.getElementById('resultVideoId').textContent = `#${videoId}`;
    TabManager.show('upload');  // Stay on same side while showing results
    await ResultsRenderer.load(videoId);
    document.getElementById('downloadRow').style.display = 'flex';
    NotificationSystem.info(`Loaded results for video #${videoId}`);
  },
};

// ── Camera Manager ────────────────────────────────────────────
const CameraManager = {
  streamInterval: null,
  statsInterval: null,
  isStreaming: false,

  async start() {
    try {
      const cameraSource = document.getElementById('cameraSource').value || '0';
      await API.startCamera(cameraSource);
      const img = document.getElementById('cameraStream');
      img.classList.remove('hidden');
      document.getElementById('cameraPlaceholder').classList.add('hidden');
      document.getElementById('btnStartCam').disabled = true;
      document.getElementById('btnStopCam').disabled  = false;
      
      this.isStreaming = true;
      this.startPolling();
      this.startStatsPolling();
      NotificationSystem.success('Camera stream started: ' + cameraSource);
    } catch (err) {
      NotificationSystem.error('Failed to start camera: ' + err.message);
    }
  },

  startPolling() {
    if (this.streamInterval) clearInterval(this.streamInterval);
    this.streamInterval = setInterval(async () => {
      if (!this.isStreaming) return;
      try {
        const response = await fetch('/api/camera/frame?t=' + Date.now());
        if (response.ok) {
          const blob = await response.blob();
          const url = URL.createObjectURL(blob);
          const img = document.getElementById('cameraStream');
          img.src = url;
        }
      } catch (err) {
        console.error('Stream polling error:', err);
      }
    }, 50); // Poll every 50ms for ~20fps updates
  },

  startStatsPolling() {
    if (this.statsInterval) clearInterval(this.statsInterval);
    this.statsInterval = setInterval(async () => {
      if (!this.isStreaming) return;
      try {
        const response = await API.cameraStats();
        if (response.data) {
          const analytics = response.data;
          StatsAnimator.update(analytics);
        }
      } catch (err) {
        console.error('Stats polling error:', err);
      }
    }, 500); // Poll every 500ms for stats
  },

  async stop() {
    try {
      this.isStreaming = false;
      if (this.streamInterval) {
        clearInterval(this.streamInterval);
        this.streamInterval = null;
      }
      if (this.statsInterval) {
        clearInterval(this.statsInterval);
        this.statsInterval = null;
      }
      await API.stopCamera();
      const img = document.getElementById('cameraStream');
      img.src = '';
      img.classList.add('hidden');
      document.getElementById('cameraPlaceholder').classList.remove('hidden');
      document.getElementById('btnStartCam').disabled = false;
      document.getElementById('btnStopCam').disabled  = true;
      NotificationSystem.info('Camera stream stopped.');
    } catch (err) {
      NotificationSystem.error('Failed to stop camera: ' + err.message);
    }
  },
};

// ── Downloader ────────────────────────────────────────────────
const Downloader = {
  excel() {
    const id = AppState.currentVideoId;
    if (!id) { NotificationSystem.error('No video selected.'); return; }
    window.open(`/api/download/excel/${id}`, '_blank');
  },
  video() {
    const id = AppState.currentVideoId;
    if (!id) { NotificationSystem.error('No video selected.'); return; }
    window.open(`/api/download/video/${id}`, '_blank');
  },
};

// ── Init ──────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  // Verify API is live
  fetch('/api/health').then(r => r.json()).then(d => {
    if (d.status === 'ok') {
      document.getElementById('systemStatus').textContent = '● ONLINE';
    }
  }).catch(() => {
    document.getElementById('systemStatus').textContent = '● OFFLINE';
    document.getElementById('systemStatus').style.color = 'var(--accent-red)';
  });
});
