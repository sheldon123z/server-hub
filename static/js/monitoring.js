/**
 * ServerHub 监控大屏前端核心
 * WebSocket 客户端 + ECharts 图表工厂 + 数据分发
 */

// ─── ECharts 暗色主题注册 ───
echarts.registerTheme('serverhub', {
    backgroundColor: 'transparent',
    color: ['#38bdf8', '#4ade80', '#fbbf24', '#f87171', '#a78bfa', '#fb923c', '#2dd4bf', '#e879f9'],
    textStyle: { color: '#94a3b8' },
    title: { textStyle: { color: '#e2e8f0' }, subtextStyle: { color: '#94a3b8' } },
    legend: { textStyle: { color: '#94a3b8' } },
    tooltip: {
        backgroundColor: 'rgba(15, 23, 42, 0.95)',
        borderColor: '#334155',
        textStyle: { color: '#e2e8f0' },
    },
    axisLine: { lineStyle: { color: '#334155' } },
    splitLine: { lineStyle: { color: 'rgba(51, 65, 85, 0.5)' } },
    categoryAxis: { axisLine: { lineStyle: { color: '#334155' } }, axisLabel: { color: '#94a3b8' } },
    valueAxis: { axisLine: { lineStyle: { color: '#334155' } }, axisLabel: { color: '#94a3b8' }, splitLine: { lineStyle: { color: 'rgba(51, 65, 85, 0.3)' } } },
});

// ─── WebSocket 客户端 ───
class MetricsWS {
    constructor() {
        this.ws = null;
        this.subscribers = new Map();
        this.latestData = {};
        this.connected = false;
        this._reconnectDelay = 1000;
        this._maxReconnectDelay = 30000;
        this._buffer = []; // 最近60个快照用于sparkline
    }

    connect() {
        const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
        const url = `${protocol}//${location.host}/ws/metrics`;
        this.ws = new WebSocket(url);

        this.ws.onopen = () => {
            this.connected = true;
            this._reconnectDelay = 1000;
            this._notify('_status', { connected: true });
        };

        this.ws.onmessage = (event) => {
            try {
                const msg = JSON.parse(event.data);
                if (msg.type === 'metrics' || msg.type === 'metrics_full') {
                    this.latestData = msg.data;
                    this._buffer.push(msg.data);
                    if (this._buffer.length > 60) this._buffer.shift();
                    // 分发到各订阅者
                    for (const [key, callbacks] of this.subscribers) {
                        if (key === '_all' || msg.data[key] !== undefined) {
                            const value = key === '_all' ? msg.data : msg.data[key];
                            callbacks.forEach(cb => { try { cb(value, msg.data); } catch(e) { console.error(e); } });
                        }
                    }
                } else if (msg.type === 'alert') {
                    this._notify('alert', msg.data);
                }
            } catch (e) { console.error('WS parse error:', e); }
        };

        this.ws.onclose = () => {
            this.connected = false;
            this._notify('_status', { connected: false });
            setTimeout(() => this.connect(), this._reconnectDelay);
            this._reconnectDelay = Math.min(this._reconnectDelay * 2, this._maxReconnectDelay);
        };

        this.ws.onerror = () => { this.ws.close(); };
    }

    subscribe(key, callback) {
        if (!this.subscribers.has(key)) this.subscribers.set(key, new Set());
        this.subscribers.get(key).add(callback);
    }

    unsubscribe(key, callback) {
        const s = this.subscribers.get(key);
        if (s) { s.delete(callback); if (s.size === 0) this.subscribers.delete(key); }
    }

    _notify(key, data) {
        const callbacks = this.subscribers.get(key);
        if (callbacks) callbacks.forEach(cb => { try { cb(data); } catch(e) {} });
    }
}

const metricsWS = new MetricsWS();

// ─── 格式化工具 ───
function formatBytesM(bytes) {
    if (bytes === 0) return '0 B';
    const k = 1024, sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
}

function formatRate(bytesPerSec) {
    if (bytesPerSec < 1024) return bytesPerSec.toFixed(0) + ' B/s';
    if (bytesPerSec < 1024*1024) return (bytesPerSec/1024).toFixed(1) + ' KB/s';
    return (bytesPerSec/1024/1024).toFixed(1) + ' MB/s';
}

function formatPercentM(v) { return (v || 0).toFixed(1) + '%'; }

function statusColor(percent) {
    if (percent >= 85) return '#f87171';  // red
    if (percent >= 60) return '#fbbf24';  // yellow
    return '#4ade80';                     // green
}

function timeAgo(ts) {
    const diff = Date.now()/1000 - ts;
    if (diff < 60) return Math.floor(diff) + 's ago';
    if (diff < 3600) return Math.floor(diff/60) + 'm ago';
    if (diff < 86400) return Math.floor(diff/3600) + 'h ago';
    return Math.floor(diff/86400) + 'd ago';
}

// ─── ECharts 图表工厂 ───

// 迷你 sparkline (用于卡片底部)
function createSparkline(el, color) {
    color = color || '#38bdf8';
    const chart = echarts.init(el, 'serverhub', { renderer: 'canvas' });
    chart.setOption({
        grid: { left: 0, right: 0, top: 0, bottom: 0 },
        xAxis: { show: false, type: 'category', data: [] },
        yAxis: { show: false, type: 'value', min: 0, max: 100 },
        series: [{
            type: 'line', data: [], smooth: true, symbol: 'none',
            lineStyle: { width: 1.5, color: color },
            areaStyle: { color: { type: 'linear', x: 0, y: 0, x2: 0, y2: 1, colorStops: [
                { offset: 0, color: color + '4D' },
                { offset: 1, color: 'transparent' }
            ]}},
        }],
        animation: false,
    });
    return chart;
}

// 趋势折线图（多线，带dataZoom）
function createTrendChart(el, opts) {
    opts = opts || {};
    var chart = echarts.init(el, 'serverhub');
    var series = (opts.series || []).map(function(s) {
        return Object.assign({
            type: 'line', smooth: true, symbol: 'none', lineStyle: { width: 2 },
            areaStyle: opts.area ? { opacity: 0.1 } : undefined,
        }, s);
    });
    chart.setOption({
        tooltip: { trigger: 'axis' },
        legend: { show: series.length > 1, top: 5 },
        grid: { left: 50, right: 20, top: series.length > 1 ? 35 : 15, bottom: opts.dataZoom ? 50 : 25 },
        xAxis: { type: 'category', data: opts.xData || [], boundaryGap: false },
        yAxis: { type: 'value', min: opts.yMin != null ? opts.yMin : 0, max: opts.yMax, axisLabel: { formatter: opts.yFormatter || '{value}' } },
        series: series,
        dataZoom: opts.dataZoom ? [{ type: 'inside' }, { type: 'slider', height: 20, bottom: 5 }] : [],
    });
    return chart;
}

// 仪表盘 (gauge)
function createGaugeChart(el, opts) {
    opts = opts || {};
    var chart = echarts.init(el, 'serverhub');
    chart.setOption({
        series: [{
            type: 'gauge',
            radius: '90%',
            startAngle: 220, endAngle: -40,
            min: 0, max: 100,
            pointer: { show: false },
            progress: { show: true, width: 12, roundCap: true },
            axisLine: { lineStyle: { width: 12, color: [[0.6, '#4ade80'], [0.85, '#fbbf24'], [1, '#f87171']] } },
            axisTick: { show: false },
            splitLine: { show: false },
            axisLabel: { show: false },
            title: { show: true, offsetCenter: [0, '70%'], fontSize: 12, color: '#94a3b8' },
            detail: { valueAnimation: true, fontSize: 24, fontWeight: 'bold', offsetCenter: [0, '15%'], color: '#e2e8f0', formatter: '{value}%' },
            data: [{ value: opts.value || 0, name: opts.name || '' }],
        }],
    });
    return chart;
}

// 热力图 (CPU核心)
function createHeatmapChart(el, opts) {
    opts = opts || {};
    var cols = opts.cols || 16;
    var rows = opts.rows || 10;
    var chart = echarts.init(el, 'serverhub');
    chart.setOption({
        tooltip: { formatter: function(p) { return 'Core ' + (p.data[0] + p.data[1] * cols) + ': ' + p.data[2] + '%'; } },
        grid: { left: 30, right: 10, top: 10, bottom: 30 },
        xAxis: { type: 'category', data: Array.from({length: cols}, function(_, i) { return i; }), splitArea: { show: true } },
        yAxis: { type: 'category', data: Array.from({length: rows}, function(_, i) { return i; }), splitArea: { show: true } },
        visualMap: { min: 0, max: 100, orient: 'horizontal', left: 'center', bottom: 0, inRange: { color: ['#1e293b', '#4ade80', '#fbbf24', '#f87171'] }, textStyle: { color: '#94a3b8' } },
        series: [{ type: 'heatmap', data: opts.data || [], label: { show: false } }],
    });
    return chart;
}

// 饼图 (TCP连接状态)
function createPieChart(el, opts) {
    opts = opts || {};
    var chart = echarts.init(el, 'serverhub');
    chart.setOption({
        tooltip: { trigger: 'item', formatter: '{b}: {c} ({d}%)' },
        legend: { orient: 'vertical', right: 10, top: 'center', textStyle: { color: '#94a3b8' } },
        series: [{
            type: 'pie', radius: ['40%', '70%'], center: ['35%', '50%'],
            label: { show: false },
            emphasis: { label: { show: true, fontSize: 14 } },
            data: opts.data || [],
        }],
    });
    return chart;
}

// 水平柱状图 (用户配额对比)
function createHBarChart(el, opts) {
    opts = opts || {};
    var chart = echarts.init(el, 'serverhub');
    chart.setOption({
        tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
        grid: { left: 80, right: 30, top: 10, bottom: 20 },
        xAxis: { type: 'value', max: opts.max, axisLabel: { formatter: opts.xFormatter || '{value}' } },
        yAxis: { type: 'category', data: opts.yData || [], inverse: true },
        series: (opts.series || []).map(function(s) { return Object.assign({ type: 'bar', barWidth: 16 }, s); }),
    });
    return chart;
}

// ─── Alpine.js 仪表盘状态管理 ───
function dashboardState() {
    return {
        // 下钻状态
        drillTarget: null,      // null=总览, 'cpu'|'memory'|'disk'|'gpu'|'network'|'docker'|'users'
        locateTarget: null,     // null=无, {type:'processes',sort:'cpu'}|{type:'logs',container:'xxx'}|{type:'alerts'}

        // WebSocket
        wsConnected: false,

        // 指标数据
        cpu: { overall_percent: 0, per_cpu_percent: [], load_avg: { '1min': 0, '5min': 0, '15min': 0 }, count: 0 },
        memory: { ram: { total: 0, used: 0, available: 0, percent: 0 }, swap: { total: 0, used: 0, percent: 0 } },
        gpu: { available: false, util: 0, mem_used: 0, mem_total: 0, temp: 0, processes: [] },
        network: { totals: { bytes_recv_rate: 0, bytes_sent_rate: 0, drop_in: 0, drop_out: 0 }, tcp_states: {}, tcp_total: 0 },
        diskIo: { devices: {} },
        docker: { containers: [], groups: {}, total_containers: 0, total_running: 0 },
        disk: [],
        inode: [],
        topProcesses: { by_cpu: [], by_mem: [], by_gpu: [] },
        alerts: { critical: 0, warning: 0, info: 0, recent: [] },
        uptime: '',

        // 趋势数据缓存
        trendData: { timestamps: [], cpu: [], memory: [], gpu: [] },

        // ECharts 实例缓存
        _charts: {},

        // ─── 初始化 ───
        async init() {
            // 连接 WebSocket
            metricsWS.connect();
            metricsWS.subscribe('_status', (s) => { this.wsConnected = s.connected; });
            metricsWS.subscribe('_all', (data) => this._onMetricsUpdate(data));
            metricsWS.subscribe('alert', (data) => this._onAlert(data));

            // 加载历史趋势数据
            await this._loadHistory();
            // 加载告警摘要
            await this._loadAlertSummary();

            // 初始化总览图表（延迟等待 DOM 渲染）
            this.$nextTick(() => this._initOverviewCharts());

            // 窗口 resize 自适应
            window.addEventListener('resize', () => {
                Object.values(this._charts).forEach(c => c && c.resize && c.resize());
            });
        },

        // ─── 数据更新回调 ───
        _onMetricsUpdate(data) {
            if (data.cpu) this.cpu = data.cpu;
            if (data.memory) this.memory = data.memory;
            if (data.gpu) this.gpu = data.gpu;
            if (data.network) this.network = data.network;
            if (data.disk_io) this.diskIo = data.disk_io;
            if (data.docker) this.docker = data.docker;
            if (data.disk) this.disk = data.disk;
            if (data.inode) this.inode = data.inode;
            if (data.top_processes) this.topProcesses = data.top_processes;
            if (data.uptime) this.uptime = data.uptime;

            // 追加趋势数据
            const now = new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });
            this.trendData.timestamps.push(now);
            this.trendData.cpu.push(data.cpu ? data.cpu.overall_percent : 0);
            this.trendData.memory.push(data.memory && data.memory.ram ? data.memory.ram.percent : 0);
            this.trendData.gpu.push(data.gpu ? data.gpu.util : 0);
            // 保留最近300个点 (5s x 300 = 25min)
            var maxPoints = 300;
            if (this.trendData.timestamps.length > maxPoints) {
                this.trendData.timestamps = this.trendData.timestamps.slice(-maxPoints);
                this.trendData.cpu = this.trendData.cpu.slice(-maxPoints);
                this.trendData.memory = this.trendData.memory.slice(-maxPoints);
                this.trendData.gpu = this.trendData.gpu.slice(-maxPoints);
            }

            // 更新可见图表
            this._updateVisibleCharts();
        },

        _onAlert(data) {
            this.alerts.recent.unshift(data);
            if (this.alerts.recent.length > 50) this.alerts.recent.pop();
            this._loadAlertSummary();
        },

        // ─── 加载历史 ───
        async _loadHistory() {
            try {
                var resp = await fetch('/api/monitoring/history?metric=all&hours=24');
                if (!resp.ok) return;
                var rows = await resp.json();
                rows.forEach(row => {
                    var data = typeof row.value === 'string' ? JSON.parse(row.value) : row.value;
                    var ts = new Date(row.timestamp).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });
                    this.trendData.timestamps.push(ts);
                    this.trendData.cpu.push(data.cpu ? (data.cpu.overall_percent || 0) : 0);
                    this.trendData.memory.push(data.memory && data.memory.ram ? (data.memory.ram.percent || 0) : 0);
                    this.trendData.gpu.push(data.gpu ? (data.gpu.util || 0) : 0);
                });
            } catch(e) { console.error('Failed to load history:', e); }
        },

        async _loadAlertSummary() {
            try {
                var resp = await fetch('/api/monitoring/alerts/summary');
                if (!resp.ok) return;
                var data = await resp.json();
                this.alerts.critical = data.critical || 0;
                this.alerts.warning = data.warning || 0;
                this.alerts.info = data.info || 0;
            } catch(e) {}
        },

        // ─── 图表更新 ───
        _updateVisibleCharts() {
            // 总览层趋势图
            if (!this.drillTarget && this._charts.trend) {
                this._charts.trend.setOption({
                    xAxis: { data: this.trendData.timestamps },
                    series: [
                        { data: this.trendData.cpu },
                        { data: this.trendData.memory },
                        { data: this.trendData.gpu },
                    ],
                });
            }
            // 总览层 sparklines
            this._updateSparklines();

            // CPU 详情层热力图
            if (this.drillTarget === 'cpu' && this._charts.cpuHeatmap && this.cpu.per_cpu_percent) {
                var cols = 16;
                var heatData = this.cpu.per_cpu_percent.map(function(v, i) {
                    return [i % cols, Math.floor(i / cols), Math.round(v)];
                });
                this._charts.cpuHeatmap.setOption({ series: [{ data: heatData }] });
            }

            // CPU 详情层 gauge
            if (this.drillTarget === 'cpu' && this._charts.cpuGauge) {
                this._charts.cpuGauge.setOption({ series: [{ data: [{ value: Math.round(this.cpu.overall_percent), name: 'CPU' }] }] });
            }

            // Memory gauge
            if (this.drillTarget === 'memory' && this._charts.memGauge) {
                var memPct = this.memory.ram ? Math.round(this.memory.ram.percent) : 0;
                this._charts.memGauge.setOption({ series: [{ data: [{ value: memPct, name: 'RAM' }] }] });
            }

            // Network pie
            if (this.drillTarget === 'network' && this._charts.tcpPie && this.network.tcp_states) {
                var tcpData = Object.entries(this.network.tcp_states).map(function(e) { return { name: e[0], value: e[1] }; });
                this._charts.tcpPie.setOption({ series: [{ data: tcpData }] });
            }
        },

        _updateSparklines() {
            var recentCpu = metricsWS._buffer.map(function(d) { return d.cpu ? d.cpu.overall_percent : 0; }).slice(-30);
            var recentMem = metricsWS._buffer.map(function(d) { return d.memory && d.memory.ram ? d.memory.ram.percent : 0; }).slice(-30);
            var recentGpu = metricsWS._buffer.map(function(d) { return d.gpu ? d.gpu.util : 0; }).slice(-30);
            var recentNet = metricsWS._buffer.map(function(d) {
                if (!d.network || !d.network.totals) return 0;
                return Math.min(100, (d.network.totals.bytes_recv_rate + d.network.totals.bytes_sent_rate) / 1024 / 1024 * 10);
            }).slice(-30);
            var idx = function(arr) { return arr.map(function(_, i) { return i; }); };
            if (this._charts.sparkCpu) this._charts.sparkCpu.setOption({ xAxis: { data: idx(recentCpu) }, series: [{ data: recentCpu }] });
            if (this._charts.sparkMem) this._charts.sparkMem.setOption({ xAxis: { data: idx(recentMem) }, series: [{ data: recentMem }] });
            if (this._charts.sparkGpu) this._charts.sparkGpu.setOption({ xAxis: { data: idx(recentGpu) }, series: [{ data: recentGpu }] });
            if (this._charts.sparkNet) this._charts.sparkNet.setOption({ xAxis: { data: idx(recentNet) }, series: [{ data: recentNet }] });
        },

        // ─── 导航方法 ───
        drillTo(target) {
            this.drillTarget = target;
            this.$nextTick(() => this._initDetailCharts(target));
        },
        backToOverview() {
            // 销毁详情层图表
            var keepKeys = ['trend', 'sparkCpu', 'sparkMem', 'sparkGpu', 'sparkNet'];
            var self = this;
            Object.keys(this._charts).forEach(function(k) {
                if (keepKeys.indexOf(k) === -1 && self._charts[k]) {
                    self._charts[k].dispose();
                    delete self._charts[k];
                }
            });
            this.drillTarget = null;
            this.$nextTick(() => this._initOverviewCharts());
        },
        openLocate(type, params) {
            params = params || {};
            this.locateTarget = Object.assign({ type: type }, params);
            if (type === 'processes') this._loadProcesses(params.sort || 'cpu');
            if (type === 'alerts') this._loadRecentAlerts();
        },
        closeLocate() { this.locateTarget = null; },

        // ─── 初始化图表 ───
        _initOverviewCharts() {
            // 总览趋势图
            var trendEl = document.getElementById('overview-trend');
            if (trendEl) {
                if (this._charts.trend) this._charts.trend.dispose();
                this._charts.trend = createTrendChart(trendEl, {
                    xData: this.trendData.timestamps,
                    yMax: 100, yFormatter: '{value}%', area: true, dataZoom: true,
                    series: [
                        { name: 'CPU', data: this.trendData.cpu, color: '#38bdf8' },
                        { name: 'Memory', data: this.trendData.memory, color: '#4ade80' },
                        { name: 'GPU', data: this.trendData.gpu, color: '#a78bfa' },
                    ],
                });
            }
            // Sparklines
            var sparkConfigs = { sparkCpu: '#38bdf8', sparkMem: '#4ade80', sparkGpu: '#a78bfa', sparkNet: '#fbbf24' };
            var self = this;
            Object.keys(sparkConfigs).forEach(function(id) {
                var el = document.getElementById(id);
                if (el) {
                    if (self._charts[id]) self._charts[id].dispose();
                    self._charts[id] = createSparkline(el, sparkConfigs[id]);
                }
            });
        },

        _initDetailCharts(target) {
            var self = this;
            if (target === 'cpu') {
                this.$nextTick(function() {
                    var gaugeEl = document.getElementById('cpu-detail-gauge');
                    if (gaugeEl) self._charts.cpuGauge = createGaugeChart(gaugeEl, { value: Math.round(self.cpu.overall_percent), name: 'CPU' });
                    var heatEl = document.getElementById('cpu-detail-heatmap');
                    if (heatEl) {
                        var cols = 16;
                        var rows = Math.ceil((self.cpu.count || 160) / cols);
                        var heatData = (self.cpu.per_cpu_percent || []).map(function(v, i) { return [i % cols, Math.floor(i / cols), Math.round(v)]; });
                        self._charts.cpuHeatmap = createHeatmapChart(heatEl, { cols: cols, rows: rows, data: heatData });
                    }
                });
            } else if (target === 'memory') {
                this.$nextTick(function() {
                    var gaugeEl = document.getElementById('mem-detail-gauge');
                    if (gaugeEl) {
                        var pct = self.memory.ram ? Math.round(self.memory.ram.percent) : 0;
                        self._charts.memGauge = createGaugeChart(gaugeEl, { value: pct, name: 'RAM' });
                    }
                });
            } else if (target === 'network') {
                this.$nextTick(function() {
                    var pieEl = document.getElementById('tcp-detail-pie');
                    if (pieEl && self.network.tcp_states) {
                        var tcpData = Object.entries(self.network.tcp_states).map(function(e) { return { name: e[0], value: e[1] }; });
                        self._charts.tcpPie = createPieChart(pieEl, { data: tcpData });
                    }
                });
            }
        },

        // ─── API 调用 ───
        async _loadProcesses(sort) {
            try {
                var resp = await fetch('/api/monitoring/top-processes');
                if (!resp.ok) return;
                var data = await resp.json();
                this.topProcesses = data;
            } catch(e) {}
        },
        async _loadRecentAlerts() {
            try {
                var resp = await fetch('/api/monitoring/alerts/recent?limit=30');
                if (!resp.ok) return;
                this.alerts.recent = await resp.json();
            } catch(e) {}
        },
        async killProcess(pid) {
            if (!confirm('确定要终止进程 ' + pid + ' 吗？')) return;
            try {
                await fetch('/api/users/kill-process/' + pid, { method: 'POST' });
                this._loadProcesses('cpu');
            } catch(e) { alert('操作失败'); }
        },
    };
}
