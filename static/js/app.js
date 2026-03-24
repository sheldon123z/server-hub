/* ServerHub 客户端逻辑 */

// ─── Toast 通知 ───
function showToast(msg, type = 'info') {
  const container = document.getElementById('toast-container');
  if (!container) return;
  const toast = document.createElement('div');
  toast.className = `toast toast-${type}`;
  toast.textContent = msg;
  container.appendChild(toast);
  setTimeout(() => toast.remove(), 3000);
}

// ─── 格式化工具 ───
function formatBytes(bytes) {
  if (bytes === 0) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  const i = Math.floor(Math.log(bytes) / Math.log(1024));
  return (bytes / Math.pow(1024, i)).toFixed(1) + ' ' + units[i];
}

function formatPercent(value) {
  return Math.round(value) + '%';
}

function barColor(percent) {
  if (percent >= 85) return 'var(--red)';
  if (percent >= 60) return 'var(--yellow)';
  return 'var(--green)';
}

// ─── HTMX 事件处理 ───
document.addEventListener('htmx:responseError', function(evt) {
  const status = evt.detail.xhr.status;
  if (status === 401) {
    window.location.href = '/login';
  } else if (status === 403) {
    showToast('权限不足', 'err');
  } else {
    showToast('请求失败: ' + status, 'err');
  }
});

document.addEventListener('htmx:afterSwap', function(evt) {
  // 更新侧边栏活跃项
  const url = window.location.pathname;
  document.querySelectorAll('.nav-item').forEach(item => {
    const href = item.getAttribute('hx-get') || item.getAttribute('href');
    if (href) {
      const isActive = url === href || (href !== '/' && url.startsWith(href));
      item.classList.toggle('active', isActive);
    }
  });
});

// ─── 确认对话框 ───
function confirmAction(msg) {
  return confirm(msg);
}

// ─── API 调用工具 ───
async function apiCall(url, method = 'GET', body = null) {
  const opts = { method, headers: {} };
  if (body) {
    opts.headers['Content-Type'] = 'application/json';
    opts.body = JSON.stringify(body);
  }
  const resp = await fetch(url, opts);
  const data = await resp.json();
  if (!resp.ok) {
    throw new Error(data.detail || '请求失败');
  }
  return data;
}

// ─── 仪表盘图表 ───
let metricsChart = null;

async function initDashboardCharts() {
  const canvas = document.getElementById('metrics-chart');
  if (!canvas) return;

  try {
    const resp = await fetch('/api/monitoring/history?metric=cpu&hours=6');
    const data = await resp.json();

    const ctx = canvas.getContext('2d');
    if (metricsChart) metricsChart.destroy();

    metricsChart = new Chart(ctx, {
      type: 'line',
      data: {
        labels: data.map(d => new Date(d.timestamp).toLocaleTimeString('zh-CN', {hour:'2-digit', minute:'2-digit'})),
        datasets: [{
          label: 'CPU %',
          data: data.map(d => {
            try { return JSON.parse(d.value).cpu_percent || 0; } catch { return 0; }
          }),
          borderColor: '#38bdf8',
          backgroundColor: 'rgba(56,189,248,0.1)',
          borderWidth: 1.5,
          fill: true,
          tension: 0.3,
          pointRadius: 0,
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
        },
        scales: {
          x: {
            grid: { color: 'rgba(51,65,85,0.3)' },
            ticks: { color: '#64748b', font: { size: 10 }, maxTicksLimit: 12 },
          },
          y: {
            min: 0, max: 100,
            grid: { color: 'rgba(51,65,85,0.3)' },
            ticks: { color: '#64748b', font: { size: 10 }, callback: v => v + '%' },
          }
        },
        interaction: { mode: 'index', intersect: false },
      }
    });
  } catch (e) {
    console.warn('Chart init failed:', e);
  }
}

// ─── 仪表盘实时数据 ───
async function refreshDashboard() {
  try {
    const data = await apiCall('/api/dashboard/overview');
    updateDashboardCards(data);
  } catch (e) {
    console.warn('Dashboard refresh failed:', e);
  }
}

function updateDashboardCards(s) {
  const updates = {
    'mem-value': formatPercent(s.mem_percent),
    'mem-sub': `${formatBytes(s.mem_used)} / ${formatBytes(s.mem_total)}`,
    'swap-value': formatPercent(s.swap_percent),
    'swap-sub': `${formatBytes(s.swap_used)} / ${formatBytes(s.swap_total)}`,
    'cpu-value': formatPercent(s.cpu_percent),
    'cpu-sub': `负载 ${s.load.join(' / ')} (${s.cpu_count} 核)`,
    'disk-value': formatPercent(s.disk_percent),
    'disk-sub': `${formatBytes(s.disk_used)} / ${formatBytes(s.disk_total)}`,
    'uptime-value': s.uptime,
  };

  for (const [id, val] of Object.entries(updates)) {
    const el = document.getElementById(id);
    if (el) el.textContent = val;
  }

  // 更新进度条
  ['mem', 'swap', 'cpu', 'disk'].forEach(key => {
    const bar = document.getElementById(`${key}-bar`);
    if (!bar) return;
    const pct = key === 'cpu' ? s.cpu_percent : s[`${key}_percent`];
    bar.style.width = pct + '%';
    bar.style.background = barColor(pct);
  });

  // GPU
  if (s.gpu && s.gpu.mem_total) {
    const gp = Math.round(s.gpu.mem_used / s.gpu.mem_total * 100);
    const el = document.getElementById('gpu-value');
    if (el) el.textContent = s.gpu.util + '%';
    const sub = document.getElementById('gpu-sub');
    if (sub) sub.textContent = `显存 ${s.gpu.mem_used}/${s.gpu.mem_total} MiB | ${s.gpu.temp}°C`;
    const bar = document.getElementById('gpu-bar');
    if (bar) { bar.style.width = gp + '%'; bar.style.background = barColor(gp); }
  }
}

// 页面初始化
document.addEventListener('DOMContentLoaded', function() {
  // 仪表盘自动刷新
  if (document.getElementById('dashboard-page')) {
    refreshDashboard();
    initDashboardCharts();
    setInterval(refreshDashboard, 15000);
  }
});
