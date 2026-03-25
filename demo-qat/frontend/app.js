/**
 * app.js — Intel Xeon 6 QAT Demo Frontend Logic
 *
 * Handles:
 *  - Status polling on load
 *  - WebSocket benchmark streaming
 *  - Live Chart.js updates
 *  - Results display and speedup calculation
 *  - Confetti animation for impressive speedups
 */

'use strict';

// ─── State ────────────────────────────────────────────────────────────────────
let liveChart = null;
let ws = null;
let isRunning = false;
let swSummary = null;
let accelSummary = null;
let benchDuration = 30;
let activePlotMode = null;  // 'software' | 'accelerated'

const XEON_CORES = 64;  // Assume 64-core Xeon 6 for "cores freed" calculation
const NAVIGATOR_CORES = navigator.hardwareConcurrency || XEON_CORES;

// ─── DOM refs ─────────────────────────────────────────────────────────────────
const $ = id => document.getElementById(id);

// ─── Init ─────────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  fetchStatus();
  initChart();
  bindDurationSlider();
});

// ─── Status fetch ─────────────────────────────────────────────────────────────
async function fetchStatus() {
  try {
    const res = await fetch('/api/status');
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();

    const badge = $('qatBadge');
    if (data.qat_hardware) {
      badge.textContent = '✓ QAT Hardware';
      badge.className = 'badge badge-green';
    } else if (data.qat_simulated) {
      badge.textContent = '⚡ QAT Simulated';
      badge.className = 'badge badge-yellow';
    } else if (data.isal_available) {
      badge.textContent = 'ISA-L only';
      badge.className = 'badge badge-grey';
    } else {
      badge.textContent = 'Software only';
      badge.className = 'badge badge-grey';
    }

    $('isalVersion').textContent = data.isal_available
      ? `v${data.isal_version}`
      : 'not available';

    $('engineInfo').textContent = data.qat_simulated
      ? 'ISA-L + QAT simulation'
      : (data.isal_available ? 'Intel ISA-L' : 'Python gzip');

    $('accelEngine').textContent = data.qat_simulated
      ? 'ISA-L + QAT sim'
      : (data.isal_available ? 'ISA-L' : 'zlib');

  } catch (err) {
    console.error('Status fetch failed:', err);
    const badge = $('qatBadge');
    badge.textContent = '⚠ Backend offline';
    badge.className = 'badge badge-red';
  }
}

// ─── Duration slider ──────────────────────────────────────────────────────────
function bindDurationSlider() {
  const slider = $('durationSlider');
  const val = $('durationVal');
  slider.addEventListener('input', () => {
    benchDuration = parseInt(slider.value, 10);
    val.textContent = benchDuration;
  });
}

// ─── Chart init ───────────────────────────────────────────────────────────────
function initChart() {
  const ctx = $('liveChart').getContext('2d');
  liveChart = new Chart(ctx, {
    type: 'line',
    data: {
      labels: [],
      datasets: [
        {
          label: '⚙ Software (MB/s)',
          data: [],
          borderColor: '#718096',
          backgroundColor: 'rgba(113,128,150,0.08)',
          borderWidth: 2,
          pointRadius: 2,
          tension: 0.4,
          fill: true,
        },
        {
          label: '⚡ QAT Accelerated (MB/s)',
          data: [],
          borderColor: '#00C7FD',
          backgroundColor: 'rgba(0,199,253,0.08)',
          borderWidth: 2.5,
          pointRadius: 2,
          tension: 0.4,
          fill: true,
        },
      ],
    },
    options: {
      responsive: true,
      animation: { duration: 200 },
      interaction: { mode: 'index', intersect: false },
      scales: {
        x: {
          ticks: { color: '#718096', maxTicksLimit: 15 },
          grid: { color: '#1e2736' },
          title: { display: true, text: 'Elapsed (s)', color: '#718096' },
        },
        y: {
          ticks: { color: '#a0aec0' },
          grid: { color: '#1e2736' },
          title: { display: true, text: 'Throughput MB/s', color: '#a0aec0' },
          beginAtZero: true,
        },
      },
      plugins: {
        legend: {
          labels: { color: '#e2e8f0', font: { family: 'monospace' } },
        },
        tooltip: {
          backgroundColor: '#1a2233',
          titleColor: '#00C7FD',
          bodyColor: '#e2e8f0',
        },
      },
    },
  });
}

// ─── Reset chart and panels ───────────────────────────────────────────────────
function resetUI() {
  // Clear chart
  liveChart.data.labels = [];
  liveChart.data.datasets[0].data = [];
  liveChart.data.datasets[1].data = [];
  liveChart.update('none');

  // Reset panels
  for (const id of ['swThroughput','swCpu','swRatio','swLatency','accelThroughput','accelCpu','accelRatio','accelLatency']) {
    $(id).textContent = '—';
  }
  $('swElapsed').textContent = 'Running…';
  $('accelElapsed').textContent = 'Waiting…';
  $('swProgress').style.width = '0%';
  $('accelProgress').style.width = '0%';

  // Hide results
  $('resultsSection').classList.add('hidden');
  $('confettiContainer').innerHTML = '';

  swSummary = null;
  accelSummary = null;
}

// ─── Main benchmark trigger ───────────────────────────────────────────────────
function runBenchmark() {
  if (isRunning) {
    console.warn('Benchmark already running.');
    return;
  }

  const duration = parseInt($('durationSlider').value, 10);
  const chunkSizeMb = parseInt($('chunkSelect').value, 10);
  benchDuration = duration;

  resetUI();
  setRunning(true);

  const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
  const wsUrl = `${protocol}//${location.host}/ws/benchmark`;

  try {
    ws = new WebSocket(wsUrl);
  } catch (err) {
    setRunning(false);
    setStatus(`❌ WebSocket error: ${err.message}`);
    return;
  }

  ws.onopen = () => {
    setStatus('🔗 Connected — starting benchmark…');
    ws.send(JSON.stringify({
      mode: 'both',
      duration,
      chunk_size_mb: chunkSizeMb,
    }));
  };

  ws.onmessage = (event) => {
    let msg;
    try {
      msg = JSON.parse(event.data);
    } catch (e) {
      console.error('Bad JSON from server:', event.data);
      return;
    }
    handleMessage(msg, duration);
  };

  ws.onerror = (err) => {
    console.error('WebSocket error', err);
    setStatus('❌ WebSocket connection error. Is the backend running?');
    setRunning(false);
  };

  ws.onclose = (event) => {
    if (isRunning) {
      setStatus(`⚠ Connection closed unexpectedly (code ${event.code}).`);
      setRunning(false);
    }
  };
}

// ─── Message handler ──────────────────────────────────────────────────────────
function handleMessage(msg, duration) {
  const { type } = msg;

  if (type === 'phase_start') {
    const phase = msg.phase;
    activePlotMode = phase;
    setStatus(`⏱ ${msg.message}`);
    if (phase === 'software') {
      $('swElapsed').textContent = 'Running…';
    } else {
      $('accelElapsed').textContent = 'Running…';
    }
    return;
  }

  if (type === 'mode_switch') {
    activePlotMode = 'accelerated';
    setStatus(`⚡ ${msg.message}`);
    $('swElapsed').textContent = 'Complete ✓';
    $('accelElapsed').textContent = 'Running…';
    if (msg.sw_summary) swSummary = msg.sw_summary;
    return;
  }

  if (type === 'complete') {
    handleComplete(msg.summary);
    return;
  }

  if (type === 'error') {
    setStatus(`❌ Error: ${msg.message}`);
    setRunning(false);
    return;
  }

  // Per-second metric update
  if (msg.mode) {
    updatePanel(msg, duration);
    pushToChart(msg);
  }
}

// ─── Panel update ─────────────────────────────────────────────────────────────
function updatePanel(m, duration) {
  const isSw = m.mode === 'software';
  const prefix = isSw ? 'sw' : 'accel';

  animateValue(`${prefix}Throughput`, m.throughput_mbps.toFixed(1));
  animateValue(`${prefix}Cpu`, `${m.cpu_percent.toFixed(1)}%`);
  animateValue(`${prefix}Ratio`, `${m.compression_ratio.toFixed(2)}×`);
  animateValue(`${prefix}Latency`, `${m.latency_ms.toFixed(1)} ms`);

  // Progress bar
  const pct = Math.min(100, (m.elapsed / duration) * 100);
  $(`${prefix}Progress`).style.width = `${pct}%`;
  $(`${prefix}Elapsed`).textContent = `${m.elapsed.toFixed(0)}s / ${duration}s`;
}

// ─── Smooth value animation ───────────────────────────────────────────────────
function animateValue(id, newVal) {
  const el = $(id);
  if (!el) return;
  el.classList.add('value-updating');
  el.textContent = newVal;
  setTimeout(() => el.classList.remove('value-updating'), 300);
}

// ─── Chart update ────────────────────────────────────────────────────────────
function pushToChart(m) {
  const datasetIdx = m.mode === 'software' ? 0 : 1;
  const label = `${m.elapsed.toFixed(0)}s`;

  // Only add label from software (primary timeline), accelerated reuses same time axis
  if (m.mode === 'software') {
    liveChart.data.labels.push(label);
  } else {
    // Ensure label array is long enough for accelerated data
    while (liveChart.data.labels.length <= liveChart.data.datasets[1].data.length) {
      liveChart.data.labels.push(label);
    }
  }

  liveChart.data.datasets[datasetIdx].data.push(m.throughput_mbps);

  // Keep chart from growing unbounded
  const MAX_POINTS = 120;
  if (liveChart.data.labels.length > MAX_POINTS) {
    liveChart.data.labels.shift();
    liveChart.data.datasets.forEach(ds => ds.data.shift());
  }

  liveChart.update('none');
}

// ─── Complete handler ─────────────────────────────────────────────────────────
function handleComplete(summary) {
  setRunning(false);
  setStatus('✅ Benchmark complete!');

  if (ws) ws.close();

  $('swElapsed').textContent = 'Complete ✓';
  $('accelElapsed').textContent = 'Complete ✓';
  $('swProgress').style.width = '100%';
  $('accelProgress').style.width = '100%';

  swSummary = summary.software || swSummary;
  accelSummary = summary.accelerated || accelSummary;
  const speedup = summary.speedup || 1;

  buildResultsTable(swSummary, accelSummary, speedup);
  $('resultsSection').classList.remove('hidden');
  $('resultsSection').scrollIntoView({ behavior: 'smooth', block: 'start' });

  if (speedup > 10) launchConfetti();
}

// ─── Results table ────────────────────────────────────────────────────────────
function buildResultsTable(sw, accel, speedup) {
  if (!sw || !accel) return;

  $('speedupNum').textContent = `${speedup.toFixed(1)}×`;

  const swCpuPct = sw.avg_cpu_percent || 0;
  const accelCpuPct = accel.avg_cpu_percent || 0;
  const cpuDelta = swCpuPct - accelCpuPct;
  const coresFree = ((cpuDelta / 100) * XEON_CORES).toFixed(1);
  const latencyImprove = sw.p99_latency_ms > 0
    ? `${(sw.p99_latency_ms / (accel.p99_latency_ms || 1)).toFixed(1)}×`
    : '—';

  $('coresFreeVal').textContent = coresFree;
  $('cpuSavedPct').textContent = `${cpuDelta.toFixed(1)}%`;
  $('latencyImprov').textContent = latencyImprove;

  const rows = [
    ['Throughput', fmb(sw.avg_throughput_mbps), fmb(accel.avg_throughput_mbps), `${speedup.toFixed(1)}×`, 'green'],
    ['CPU Usage', fpc(swCpuPct), fpc(accelCpuPct), `−${cpuDelta.toFixed(1)}%`, 'green'],
    ['P99 Latency', fms(sw.p99_latency_ms), fms(accel.p99_latency_ms), latencyImprove, 'green'],
    ['P50 Latency', fms(sw.p50_latency_ms), fms(accel.p50_latency_ms), '—', ''],
    ['Compression Ratio', `${sw.compression_ratio}×`, `${accel.compression_ratio}×`, '—', ''],
    ['Total Data Processed', fmb(sw.total_data_mb), fmb(accel.total_data_mb), '—', ''],
  ];

  const tbody = $('resultsTableBody');
  tbody.innerHTML = rows.map(([metric, swVal, accelVal, delta, cls]) => `
    <tr>
      <td>${metric}</td>
      <td class="td-sw">${swVal}</td>
      <td class="td-accel">${accelVal}</td>
      <td class="td-delta ${cls}">${delta}</td>
    </tr>
  `).join('');
}

// ─── Formatters ───────────────────────────────────────────────────────────────
const fmb = v => v != null ? `${Number(v).toFixed(1)} MB/s` : '—';
const fpc = v => v != null ? `${Number(v).toFixed(1)}%` : '—';
const fms = v => v != null ? `${Number(v).toFixed(2)} ms` : '—';

// ─── UI helpers ───────────────────────────────────────────────────────────────
function setRunning(running) {
  isRunning = running;
  const btn = $('runBtn');
  if (running) {
    btn.classList.add('active');
    btn.disabled = true;
    btn.innerHTML = '<span class="run-icon spin">◌</span> RUNNING…';
  } else {
    btn.classList.remove('active');
    btn.disabled = false;
    btn.innerHTML = '<span class="run-icon">▶</span> RUN BENCHMARK';
  }
}

function setStatus(text) {
  $('runStatus').textContent = text;
}

// ─── Confetti ─────────────────────────────────────────────────────────────────
function launchConfetti() {
  const container = $('confettiContainer');
  container.innerHTML = '';
  const colors = ['#0068B5', '#00C7FD', '#68D391', '#F6E05E', '#FC8181', '#B794F4'];
  const count = 120;

  for (let i = 0; i < count; i++) {
    const el = document.createElement('div');
    el.className = 'confetti-piece';
    el.style.left = `${Math.random() * 100}vw`;
    el.style.animationDelay = `${Math.random() * 2}s`;
    el.style.animationDuration = `${2 + Math.random() * 2}s`;
    el.style.backgroundColor = colors[Math.floor(Math.random() * colors.length)];
    el.style.transform = `rotate(${Math.random() * 360}deg)`;
    container.appendChild(el);
  }

  // Auto-clear after 5s
  setTimeout(() => { container.innerHTML = ''; }, 5000);
}
