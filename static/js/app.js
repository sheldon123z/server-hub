/* ServerHub 客户端逻辑 */

// ─── Toast 通知 ───
function showToast(msg, type) {
  type = type || 'info';
  var container = document.getElementById('toast-container');
  if (!container) return;
  var toast = document.createElement('div');
  toast.className = 'toast toast-' + type;
  toast.textContent = msg;
  container.appendChild(toast);
  setTimeout(function() { toast.remove(); }, 3000);
}

// ─── 格式化工具 ───
function formatBytes(bytes) {
  if (bytes === 0) return '0 B';
  var units = ['B', 'KB', 'MB', 'GB', 'TB'];
  var i = Math.floor(Math.log(bytes) / Math.log(1024));
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
  var status = evt.detail.xhr.status;
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
  var url = window.location.pathname;
  document.querySelectorAll('.nav-item').forEach(function(item) {
    var href = item.getAttribute('hx-get') || item.getAttribute('href');
    if (href) {
      var isActive = url === href || (href !== '/' && url.startsWith(href));
      item.classList.toggle('active', isActive);
    }
  });
});

// ─── 确认对话框 ───
function confirmAction(msg) {
  return confirm(msg);
}

// ─── API 调用工具 ───
async function apiCall(url, method, body) {
  method = method || 'GET';
  body = body || null;
  var opts = { method: method, headers: {} };
  if (body) {
    opts.headers['Content-Type'] = 'application/json';
    opts.body = JSON.stringify(body);
  }
  var resp = await fetch(url, opts);
  var data = await resp.json();
  if (!resp.ok) {
    throw new Error(data.detail || '请求失败');
  }
  return data;
}
