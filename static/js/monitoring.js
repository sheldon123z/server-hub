/**
 * ServerHub 监控大屏前端核心
 * 单一 dashboard 页面 + ECharts 可视化 + WebSocket 实时推送
 */

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
    splitLine: { lineStyle: { color: 'rgba(51, 65, 85, 0.35)' } },
    categoryAxis: {
        axisLine: { lineStyle: { color: '#334155' } },
        axisLabel: { color: '#94a3b8' },
    },
    valueAxis: {
        axisLine: { lineStyle: { color: '#334155' } },
        axisLabel: { color: '#94a3b8' },
        splitLine: { lineStyle: { color: 'rgba(51, 65, 85, 0.3)' } },
    },
});

class MetricsWS {
    constructor() {
        this.ws = null;
        this.subscribers = new Map();
        this.connected = false;
        this._reconnectDelay = 1000;
        this._maxReconnectDelay = 30000;
        this._buffer = [];
    }

    connect() {
        const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
        this.ws = new WebSocket(`${protocol}//${location.host}/ws/metrics`);

        this.ws.onopen = () => {
            this.connected = true;
            this._reconnectDelay = 1000;
            this._notify('_status', { connected: true });
        };

        this.ws.onmessage = (event) => {
            try {
                const msg = JSON.parse(event.data);
                if (msg.type === 'metrics' || msg.type === 'metrics_full') {
                    this._buffer.push(msg.data);
                    if (this._buffer.length > 90) {
                        this._buffer.shift();
                    }
                    this._notify('_all', msg.data);
                } else if (msg.type === 'alert') {
                    this._notify('alert', msg.data);
                }
            } catch (e) {
                console.error('WS parse error:', e);
            }
        };

        this.ws.onclose = () => {
            this.connected = false;
            this._notify('_status', { connected: false });
            setTimeout(() => this.connect(), this._reconnectDelay);
            this._reconnectDelay = Math.min(this._reconnectDelay * 2, this._maxReconnectDelay);
        };

        this.ws.onerror = () => {
            if (this.ws) {
                this.ws.close();
            }
        };
    }

    subscribe(key, callback) {
        if (!this.subscribers.has(key)) {
            this.subscribers.set(key, new Set());
        }
        this.subscribers.get(key).add(callback);
    }

    _notify(key, data) {
        const callbacks = this.subscribers.get(key);
        if (!callbacks) {
            return;
        }
        callbacks.forEach((cb) => {
            try {
                cb(data);
            } catch (e) {
                console.error(e);
            }
        });
    }
}

const metricsWS = new MetricsWS();

function formatBytesM(bytes) {
    const value = Number(bytes) || 0;
    if (value <= 0) {
        return '0 B';
    }
    const units = ['B', 'KB', 'MB', 'GB', 'TB', 'PB'];
    const idx = Math.min(Math.floor(Math.log(value) / Math.log(1024)), units.length - 1);
    return (value / Math.pow(1024, idx)).toFixed(idx === 0 ? 0 : 1) + ' ' + units[idx];
}

function formatRate(bytesPerSec) {
    const value = Number(bytesPerSec) || 0;
    if (value < 1024) {
        return value.toFixed(0) + ' B/s';
    }
    if (value < 1024 * 1024) {
        return (value / 1024).toFixed(1) + ' KB/s';
    }
    if (value < 1024 * 1024 * 1024) {
        return (value / 1024 / 1024).toFixed(1) + ' MB/s';
    }
    return (value / 1024 / 1024 / 1024).toFixed(1) + ' GB/s';
}

function formatPercentM(value) {
    return (Number(value) || 0).toFixed(1) + '%';
}

function statusColor(percent) {
    const value = Number(percent) || 0;
    if (value >= 85) {
        return '#f87171';
    }
    if (value >= 60) {
        return '#fbbf24';
    }
    return '#4ade80';
}

function createSparkline(el, color) {
    const chart = echarts.init(el, 'serverhub', { renderer: 'canvas' });
    chart.setOption({
        grid: { left: 0, right: 0, top: 0, bottom: 0 },
        xAxis: { show: false, type: 'category', data: [] },
        yAxis: { show: false, type: 'value', min: 0, max: 100 },
        series: [{
            type: 'line',
            data: [],
            smooth: true,
            symbol: 'none',
            lineStyle: { width: 1.5, color: color },
            areaStyle: {
                color: {
                    type: 'linear',
                    x: 0,
                    y: 0,
                    x2: 0,
                    y2: 1,
                    colorStops: [
                        { offset: 0, color: color + '55' },
                        { offset: 1, color: 'transparent' },
                    ],
                },
            },
        }],
        animation: false,
    });
    return chart;
}

function createTrendChart(el, opts) {
    const chart = echarts.init(el, 'serverhub');
    chart.setOption({
        tooltip: { trigger: 'axis' },
        legend: { show: (opts.series || []).length > 1, top: 5 },
        grid: {
            left: 48,
            right: 20,
            top: (opts.series || []).length > 1 ? 36 : 16,
            bottom: opts.dataZoom ? 52 : 28,
        },
        xAxis: {
            type: 'category',
            data: opts.xData || [],
            boundaryGap: false,
        },
        yAxis: {
            type: 'value',
            min: opts.yMin != null ? opts.yMin : 0,
            max: opts.yMax,
            axisLabel: { formatter: opts.yFormatter || '{value}' },
        },
        dataZoom: opts.dataZoom ? [{ type: 'inside' }, { type: 'slider', height: 18, bottom: 6 }] : [],
        series: (opts.series || []).map((item) => Object.assign({
            type: 'line',
            smooth: true,
            symbol: 'none',
            lineStyle: { width: 2 },
        }, item)),
    });
    return chart;
}

function createGaugeChart(el, opts) {
    const chart = echarts.init(el, 'serverhub');
    chart.setOption({
        series: [{
            type: 'gauge',
            radius: '92%',
            startAngle: 220,
            endAngle: -40,
            min: 0,
            max: 100,
            pointer: { show: false },
            progress: { show: true, width: 12, roundCap: true },
            axisLine: { lineStyle: { width: 12, color: [[0.6, '#4ade80'], [0.85, '#fbbf24'], [1, '#f87171']] } },
            axisTick: { show: false },
            splitLine: { show: false },
            axisLabel: { show: false },
            title: { show: true, offsetCenter: [0, '70%'], fontSize: 12, color: '#94a3b8' },
            detail: {
                valueAnimation: true,
                fontSize: 24,
                fontWeight: 'bold',
                offsetCenter: [0, '15%'],
                color: '#e2e8f0',
                formatter: '{value}%',
            },
            data: [{ value: opts.value || 0, name: opts.name || '' }],
        }],
    });
    return chart;
}

function createHeatmapChart(el, opts) {
    const chart = echarts.init(el, 'serverhub');
    chart.setOption({
        tooltip: {
            formatter: function (p) {
                return 'Core ' + (p.data[0] + p.data[1] * opts.cols) + ': ' + p.data[2] + '%';
            },
        },
        grid: { left: 30, right: 10, top: 10, bottom: 35 },
        xAxis: {
            type: 'category',
            data: Array.from({ length: opts.cols }, (_, i) => i),
            splitArea: { show: true },
        },
        yAxis: {
            type: 'category',
            data: Array.from({ length: opts.rows }, (_, i) => i),
            splitArea: { show: true },
        },
        visualMap: {
            min: 0,
            max: 100,
            orient: 'horizontal',
            left: 'center',
            bottom: 0,
            inRange: { color: ['#1e293b', '#4ade80', '#fbbf24', '#f87171'] },
            textStyle: { color: '#94a3b8' },
        },
        series: [{ type: 'heatmap', data: opts.data || [], label: { show: false } }],
    });
    return chart;
}

function createPieChart(el, opts) {
    const chart = echarts.init(el, 'serverhub');
    chart.setOption({
        tooltip: { trigger: 'item', formatter: '{b}: {c} ({d}%)' },
        legend: {
            orient: opts.legendOrient || 'vertical',
            right: opts.legendRight || 10,
            top: opts.legendTop || 'center',
            textStyle: { color: '#94a3b8' },
        },
        series: [{
            type: 'pie',
            radius: opts.radius || ['42%', '72%'],
            center: opts.center || ['35%', '50%'],
            label: { show: false },
            emphasis: { label: { show: true, fontSize: 14 } },
            data: opts.data || [],
        }],
    });
    return chart;
}

function createBarChart(el, opts) {
    const chart = echarts.init(el, 'serverhub');
    const horizontal = Boolean(opts.horizontal);
    chart.setOption({
        tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
        legend: { show: (opts.series || []).length > 1, top: 5 },
        grid: horizontal
            ? { left: 90, right: 24, top: (opts.series || []).length > 1 ? 34 : 14, bottom: 20 }
            : { left: 48, right: 20, top: (opts.series || []).length > 1 ? 34 : 14, bottom: 45 },
        xAxis: horizontal
            ? { type: 'value', axisLabel: { formatter: opts.xFormatter || '{value}' } }
            : { type: 'category', data: opts.labels || [], axisLabel: { interval: 0, rotate: opts.rotate || 0 } },
        yAxis: horizontal
            ? { type: 'category', data: opts.labels || [], inverse: true }
            : { type: 'value', axisLabel: { formatter: opts.yFormatter || '{value}' } },
        series: (opts.series || []).map((series) => Object.assign({
            type: 'bar',
            barMaxWidth: 22,
            stack: opts.stacked ? 'total' : undefined,
        }, series)),
    });
    return chart;
}

function dashboardState() {
    return {
        drillTarget: null,
        locateTarget: null,
        wsConnected: false,
        historyPeriod: '24',

        cpu: { overall_percent: 0, per_cpu_percent: [], load_avg: { '1min': 0, '5min': 0, '15min': 0 }, count: 0 },
        memory: { ram: { total: 0, used: 0, available: 0, percent: 0 }, swap: { total: 0, used: 0, available: 0, percent: 0 } },
        gpu: { available: false, name: '', util: 0, mem_used: 0, mem_total: 0, temp: 0, processes: [] },
        network: { totals: { bytes_recv_rate: 0, bytes_sent_rate: 0, packets_recv_rate: 0, packets_sent_rate: 0, err_in: 0, err_out: 0, drop_in: 0, drop_out: 0 }, tcp_states: {}, tcp_total: 0 },
        diskIo: { devices: {} },
        docker: { containers: [], groups: {}, total_containers: 0, total_running: 0 },
        systemInfo: { hostname: '', os: '', kernel: '', cpu_model: '' },
        disk: [],
        inode: [],
        topProcesses: { by_cpu: [], by_mem: [], by_gpu: [] },
        alerts: { critical: 0, warning: 0, info: 0, activeRules: 0, total24h: 0, recent: [] },
        uptime: '',

        trendData: {
            timestamps: [],
            cpu: [],
            memory: [],
            gpu: [],
            swap: [],
            netIn: [],
            netOut: [],
            packetIn: [],
            packetOut: [],
            disk: [],
            gpuMem: [],
        },

        _charts: {},

        async init() {
            metricsWS.connect();
            metricsWS.subscribe('_status', (status) => { this.wsConnected = status.connected; });
            metricsWS.subscribe('_all', (data) => this._onMetricsUpdate(data));
            metricsWS.subscribe('alert', (data) => this._onAlert(data));

            await Promise.all([
                this._loadSnapshot(),
                this._loadHistory(),
                this._loadAlertSummary(),
                this._loadRecentAlerts(),
            ]);

            this.$nextTick(() => this._initOverviewCharts());
            window.addEventListener('resize', () => {
                Object.values(this._charts).forEach((chart) => {
                    if (chart && chart.resize) {
                        chart.resize();
                    }
                });
            });
        },

        formatAlertTime(alert) {
            const raw = alert?.created_at || alert?.timestamp;
            return raw ? new Date(raw).toLocaleString('zh-CN') : '-';
        },

        formatNumber(value) {
            return (Number(value) || 0).toFixed(1);
        },

        loadValue(key) {
            return this.cpu?.load_avg?.[key] || 0;
        },

        memoryPercent() {
            return this.memory?.ram?.percent || 0;
        },

        memoryUsed() {
            return this.memory?.ram?.used || 0;
        },

        memoryTotal() {
            return this.memory?.ram?.total || 0;
        },

        memoryAvailable() {
            return this.memory?.ram?.available || 0;
        },

        swapPercent() {
            return this.memory?.swap?.percent || 0;
        },

        swapUsed() {
            return this.memory?.swap?.used || 0;
        },

        swapTotal() {
            return this.memory?.swap?.total || 0;
        },

        netIn() {
            return this.network?.totals?.bytes_recv_rate || 0;
        },

        netOut() {
            return this.network?.totals?.bytes_sent_rate || 0;
        },

        packetsIn() {
            return this.network?.totals?.packets_recv_rate || 0;
        },

        packetsOut() {
            return this.network?.totals?.packets_sent_rate || 0;
        },

        primaryDisk() {
            return this.disk.find((item) => item.mountpoint === '/') || this.disk[0] || null;
        },

        primaryDiskPercent() {
            return this.primaryDisk()?.percent || 0;
        },

        primaryDiskLabel() {
            const disk = this.primaryDisk();
            if (!disk) {
                return '-';
            }
            return formatBytesM(disk.used) + ' / ' + formatBytesM(disk.total);
        },

        gpuTempColor() {
            if ((this.gpu?.temp || 0) >= 80) {
                return '#f87171';
            }
            if ((this.gpu?.temp || 0) >= 65) {
                return '#fbbf24';
            }
            return '#4ade80';
        },

        gpuMemPercent() {
            if (!this.gpu?.mem_total) {
                return 0;
            }
            return (this.gpu.mem_used / this.gpu.mem_total) * 100;
        },

        dockerAbnormalCount() {
            return this.docker.containers.filter((container) => container.state !== 'running').length;
        },

        topDisks(limit) {
            return [...this.disk].sort((a, b) => (b.percent || 0) - (a.percent || 0)).slice(0, limit);
        },

        dockerGroupsArray() {
            return Object.entries(this.docker.groups || {}).map(([name, info]) => ({
                name: name === '_standalone' ? 'standalone' : name,
                count: info.count || 0,
                running: info.running || 0,
                total_cpu: info.total_cpu || 0,
                total_mem_mb: info.total_mem_mb || 0,
            })).sort((a, b) => (b.total_cpu || 0) - (a.total_cpu || 0));
        },

        dockerStatusData() {
            const counts = { running: 0, restarting: 0, stopped: 0 };
            this.docker.containers.forEach((container) => {
                if (container.state === 'running') {
                    counts.running += 1;
                } else if (container.state === 'restarting') {
                    counts.restarting += 1;
                } else {
                    counts.stopped += 1;
                }
            });
            return [
                { name: '运行中', value: counts.running },
                { name: '重启中', value: counts.restarting },
                { name: '已停止', value: counts.stopped },
            ];
        },

        alertDistribution() {
            return [
                { name: '严重', value: this.alerts.critical || 0 },
                { name: '警告', value: this.alerts.warning || 0 },
                { name: '信息', value: this.alerts.info || 0 },
            ];
        },

        topProcessCpuData(limit) {
            return this.topProcesses.by_cpu.slice(0, limit);
        },

        topProcessMemData(limit) {
            return this.topProcesses.by_mem.slice(0, limit);
        },

        diskDevicesArray() {
            return Object.entries(this.diskIo.devices || {}).map(([name, info]) => ({
                name,
                ...info,
            })).sort((a, b) => (b.util_percent || 0) - (a.util_percent || 0));
        },

        busiestDeviceUtil() {
            return this.diskDevicesArray()[0]?.util_percent || 0;
        },

        busiestDeviceName() {
            const device = this.diskDevicesArray()[0];
            return device ? device.name + ' 忙碌' : '等待采集';
        },

        resourceMixData() {
            return [
                { name: 'CPU', value: this.cpu.overall_percent || 0 },
                { name: '内存', value: this.memoryPercent() },
                { name: '磁盘', value: this.primaryDiskPercent() },
                { name: 'GPU', value: this.gpu.util || 0 },
            ];
        },

        async setHistoryPeriod(period) {
            this.historyPeriod = period;
            await this._loadHistory();
            this._updateVisibleCharts();
        },

        _pushTrendPoint(label, data) {
            this.trendData.timestamps.push(label);
            this.trendData.cpu.push(data.cpu?.overall_percent || 0);
            this.trendData.memory.push(data.memory?.ram?.percent || 0);
            this.trendData.gpu.push(data.gpu?.util || 0);
            this.trendData.swap.push(data.memory?.swap?.percent || 0);
            this.trendData.netIn.push(data.network?.totals?.bytes_recv_rate || 0);
            this.trendData.netOut.push(data.network?.totals?.bytes_sent_rate || 0);
            this.trendData.packetIn.push(data.network?.totals?.packets_recv_rate || 0);
            this.trendData.packetOut.push(data.network?.totals?.packets_sent_rate || 0);
            this.trendData.disk.push((data.disk && data.disk.length ? (data.disk.find((item) => item.mountpoint === '/') || data.disk[0])?.percent : 0) || 0);
            this.trendData.gpuMem.push(data.gpu?.mem_total ? (data.gpu.mem_used / data.gpu.mem_total * 100) : 0);
        },

        _trimTrendData(maxPoints) {
            Object.keys(this.trendData).forEach((key) => {
                if (this.trendData[key].length > maxPoints) {
                    this.trendData[key] = this.trendData[key].slice(-maxPoints);
                }
            });
        },

        _applySnapshot(data, appendTrend) {
            if (data.cpu) {
                this.cpu = data.cpu;
            }
            if (data.memory) {
                this.memory = data.memory;
            }
            if (data.gpu) {
                this.gpu = data.gpu;
            }
            if (data.network) {
                this.network = data.network;
            }
            if (data.disk_io) {
                this.diskIo = data.disk_io;
            }
            if (data.docker) {
                this.docker = data.docker;
            }
            if (data.system_info) {
                this.systemInfo = data.system_info;
            }
            if (data.disk) {
                this.disk = data.disk;
            }
            if (data.inode) {
                this.inode = data.inode;
            }
            if (data.top_processes) {
                this.topProcesses = data.top_processes;
            }
            if (data.uptime) {
                this.uptime = data.uptime;
            }

            if (appendTrend) {
                const label = new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });
                this._pushTrendPoint(label, data);
                this._trimTrendData(320);
            }

            this._updateVisibleCharts();
        },

        _onMetricsUpdate(data) {
            this._applySnapshot(data, true);
        },

        _onAlert(data) {
            this.alerts.recent.unshift(data);
            if (this.alerts.recent.length > 50) {
                this.alerts.recent.pop();
            }
            this._loadAlertSummary();
        },

        async _loadSnapshot() {
            try {
                const response = await fetch('/api/monitoring/realtime');
                if (!response.ok) {
                    return;
                }
                const data = await response.json();
                metricsWS._buffer = [data];
                this._applySnapshot(data, false);
            } catch (e) {
                console.error('Failed to load monitoring snapshot:', e);
            }
        },

        async _loadHistory() {
            try {
                const response = await fetch(`/api/monitoring/history?metric=all&hours=${this.historyPeriod}`);
                if (!response.ok) {
                    return;
                }
                const rows = await response.json();
                Object.keys(this.trendData).forEach((key) => { this.trendData[key] = []; });
                rows.forEach((row) => {
                    const payload = typeof row.value === 'string' ? JSON.parse(row.value) : row.value;
                    const label = new Date(row.timestamp).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });
                    this._pushTrendPoint(label, payload);
                });
            } catch (e) {
                console.error('Failed to load history:', e);
            }
        },

        async _loadAlertSummary() {
            try {
                const response = await fetch('/api/monitoring/alerts/summary');
                if (!response.ok) {
                    return;
                }
                const data = await response.json();
                this.alerts.critical = data.critical || 0;
                this.alerts.warning = data.warning || 0;
                this.alerts.info = data.info || 0;
                this.alerts.activeRules = data.active_rules || 0;
                this.alerts.total24h = data.total_24h || 0;
            } catch (e) {
                console.error('Failed to load alert summary:', e);
            }
        },

        async _loadRecentAlerts() {
            try {
                const response = await fetch('/api/monitoring/alerts/recent?limit=30');
                if (!response.ok) {
                    return;
                }
                this.alerts.recent = await response.json();
            } catch (e) {
                console.error('Failed to load alerts:', e);
            }
        },

        async _loadProcesses() {
            try {
                const response = await fetch('/api/monitoring/top-processes?limit=20');
                if (!response.ok) {
                    return;
                }
                this.topProcesses = await response.json();
                this._updateVisibleCharts();
            } catch (e) {
                console.error('Failed to load processes:', e);
            }
        },

        _sparkSeries(bufferMapper) {
            const values = metricsWS._buffer.map(bufferMapper).slice(-40);
            return {
                labels: values.map((_, index) => index),
                values,
            };
        },

        _updateSparklines() {
            const configs = {
                sparkCpu: this._sparkSeries((item) => item.cpu?.overall_percent || 0),
                sparkMem: this._sparkSeries((item) => item.memory?.ram?.percent || 0),
                sparkSwap: this._sparkSeries((item) => item.memory?.swap?.percent || 0),
                sparkDisk: this._sparkSeries((item) => {
                    const root = item.disk?.find((disk) => disk.mountpoint === '/') || item.disk?.[0];
                    return root?.percent || 0;
                }),
                sparkNet: this._sparkSeries((item) => Math.min(100, ((item.network?.totals?.bytes_recv_rate || 0) + (item.network?.totals?.bytes_sent_rate || 0)) / 1024 / 1024 * 8)),
                sparkIo: this._sparkSeries((item) => {
                    const devices = Object.values(item.disk_io?.devices || {});
                    return devices.length ? Math.max(...devices.map((device) => device.util_percent || 0)) : 0;
                }),
                sparkDocker: this._sparkSeries((item) => {
                    const total = item.docker?.total_containers || 0;
                    const running = item.docker?.total_running || 0;
                    return total ? (running / total) * 100 : 0;
                }),
                sparkGpu: this._sparkSeries((item) => item.gpu?.util || 0),
                sparkLoad: this._sparkSeries((item) => Math.min(100, (item.cpu?.load_avg?.['1min'] || 0) * 10)),
            };

            Object.entries(configs).forEach(([key, series]) => {
                if (this._charts[key]) {
                    this._charts[key].setOption({
                        xAxis: { data: series.labels },
                        series: [{ data: series.values }],
                    });
                }
            });
        },

        _updateOverviewCharts() {
            if (this._charts.overviewTrend) {
                this._charts.overviewTrend.setOption({
                    xAxis: { data: this.trendData.timestamps },
                    series: [
                        { data: this.trendData.cpu },
                        { data: this.trendData.memory },
                        { data: this.trendData.gpu },
                        { data: this.trendData.swap },
                    ],
                });
            }

            if (this._charts.overviewAlerts) {
                this._charts.overviewAlerts.setOption({
                    series: [{ data: this.alertDistribution() }],
                });
            }

            if (this._charts.overviewDockerStatus) {
                this._charts.overviewDockerStatus.setOption({
                    series: [{ data: this.dockerStatusData() }],
                });
            }

            if (this._charts.overviewNetworkTrend) {
                this._charts.overviewNetworkTrend.setOption({
                    xAxis: { data: this.trendData.timestamps },
                    series: [
                        { data: this.trendData.netIn },
                        { data: this.trendData.netOut },
                    ],
                });
            }

            if (this._charts.overviewDiskUsage) {
                const disks = this.topDisks(8);
                this._charts.overviewDiskUsage.setOption({
                    yAxis: { data: disks.map((disk) => disk.mountpoint) },
                    series: [{ data: disks.map((disk) => disk.percent || 0) }],
                });
            }

            if (this._charts.overviewTopProc) {
                const procs = this.topProcessCpuData(8);
                this._charts.overviewTopProc.setOption({
                    yAxis: { data: procs.map((proc) => proc.name || proc.cmd || proc.pid) },
                    series: [{ data: procs.map((proc) => proc.cpu_percent || 0) }],
                });
            }

            if (this._charts.overviewDockerGroups) {
                const groups = this.dockerGroupsArray().slice(0, 8);
                this._charts.overviewDockerGroups.setOption({
                    yAxis: { data: groups.map((group) => group.name) },
                    series: [
                        { data: groups.map((group) => group.total_cpu || 0) },
                        { data: groups.map((group) => group.total_mem_mb || 0) },
                    ],
                });
            }

            if (this._charts.overviewResourceMix) {
                this._charts.overviewResourceMix.setOption({
                    series: [{ data: this.resourceMixData() }],
                });
            }

            this._updateSparklines();
        },

        _updateCpuCharts() {
            if (this._charts.cpuGauge) {
                this._charts.cpuGauge.setOption({
                    series: [{ data: [{ value: Math.round(this.cpu.overall_percent || 0), name: 'CPU' }] }],
                });
            }
            if (this._charts.cpuHeatmap) {
                const cols = 16;
                const heatData = (this.cpu.per_cpu_percent || []).map((value, index) => [index % cols, Math.floor(index / cols), Math.round(value)]);
                this._charts.cpuHeatmap.setOption({ series: [{ data: heatData }] });
            }
            if (this._charts.cpuTrend) {
                this._charts.cpuTrend.setOption({
                    xAxis: { data: this.trendData.timestamps },
                    series: [{ data: this.trendData.cpu }],
                });
            }
            if (this._charts.cpuTop) {
                const procs = this.topProcessCpuData(8);
                this._charts.cpuTop.setOption({
                    yAxis: { data: procs.map((proc) => proc.name || proc.cmd || proc.pid) },
                    series: [{ data: procs.map((proc) => proc.cpu_percent || 0) }],
                });
            }
        },

        _updateMemoryCharts() {
            if (this._charts.memGauge) {
                this._charts.memGauge.setOption({
                    series: [{ data: [{ value: Math.round(this.memoryPercent()), name: 'RAM' }] }],
                });
            }
            if (this._charts.memRing) {
                this._charts.memRing.setOption({
                    series: [{
                        data: [
                            { name: '已用', value: this.memoryUsed() },
                            { name: '可用', value: this.memoryAvailable() },
                        ],
                    }],
                });
            }
            if (this._charts.swapGauge) {
                this._charts.swapGauge.setOption({
                    series: [{ data: [{ value: Math.round(this.swapPercent()), name: 'Swap' }] }],
                });
            }
            if (this._charts.memTrend) {
                this._charts.memTrend.setOption({
                    xAxis: { data: this.trendData.timestamps },
                    series: [
                        { data: this.trendData.memory },
                        { data: this.trendData.swap },
                    ],
                });
            }
            if (this._charts.memTop) {
                const procs = this.topProcessMemData(8);
                this._charts.memTop.setOption({
                    yAxis: { data: procs.map((proc) => proc.name || proc.cmd || proc.pid) },
                    series: [{ data: procs.map((proc) => proc.mem_percent || 0) }],
                });
            }
        },

        _updateDiskCharts() {
            const disks = this.topDisks(10);
            const inodes = [...this.inode].sort((a, b) => (b.percent || 0) - (a.percent || 0)).slice(0, 10);
            const devices = this.diskDevicesArray().slice(0, 8);

            if (this._charts.diskUsage) {
                this._charts.diskUsage.setOption({
                    yAxis: { data: disks.map((disk) => disk.mountpoint) },
                    series: [{ data: disks.map((disk) => disk.percent || 0) }],
                });
            }
            if (this._charts.diskInode) {
                this._charts.diskInode.setOption({
                    yAxis: { data: inodes.map((item) => item.mountpoint) },
                    series: [{ data: inodes.map((item) => item.percent || 0) }],
                });
            }
            if (this._charts.diskIo) {
                this._charts.diskIo.setOption({
                    yAxis: { data: devices.map((device) => device.name) },
                    series: [
                        { data: devices.map((device) => (device.read_bytes_rate || 0) / 1024 / 1024) },
                        { data: devices.map((device) => (device.write_bytes_rate || 0) / 1024 / 1024) },
                    ],
                });
            }
            if (this._charts.diskDevice) {
                this._charts.diskDevice.setOption({
                    yAxis: { data: devices.map((device) => device.name) },
                    series: [{ data: devices.map((device) => device.util_percent || 0) }],
                });
            }
        },

        _updateNetworkCharts() {
            if (this._charts.networkThroughput) {
                this._charts.networkThroughput.setOption({
                    xAxis: { data: this.trendData.timestamps },
                    series: [
                        { data: this.trendData.netIn.map((value) => value / 1024 / 1024) },
                        { data: this.trendData.netOut.map((value) => value / 1024 / 1024) },
                    ],
                });
            }
            if (this._charts.networkPackets) {
                this._charts.networkPackets.setOption({
                    xAxis: { data: this.trendData.timestamps },
                    series: [
                        { data: this.trendData.packetIn },
                        { data: this.trendData.packetOut },
                    ],
                });
            }
            if (this._charts.networkTcp) {
                this._charts.networkTcp.setOption({
                    series: [{ data: Object.entries(this.network.tcp_states || {}).map(([name, value]) => ({ name, value })) }],
                });
            }
            if (this._charts.networkEvents) {
                this._charts.networkEvents.setOption({
                    xAxis: { data: ['Err In', 'Err Out', 'Drop In', 'Drop Out'] },
                    series: [{
                        data: [
                            this.network?.totals?.err_in || 0,
                            this.network?.totals?.err_out || 0,
                            this.network?.totals?.drop_in || 0,
                            this.network?.totals?.drop_out || 0,
                        ],
                    }],
                });
            }
        },

        _updateGpuCharts() {
            if (this._charts.gpuGauge) {
                this._charts.gpuGauge.setOption({
                    series: [{ data: [{ value: Math.round(this.gpu.util || 0), name: 'GPU' }] }],
                });
            }
            if (this._charts.gpuMem) {
                this._charts.gpuMem.setOption({
                    series: [{
                        data: [
                            { name: '已用显存', value: this.gpu.mem_used || 0 },
                            { name: '剩余显存', value: Math.max((this.gpu.mem_total || 0) - (this.gpu.mem_used || 0), 0) },
                        ],
                    }],
                });
            }
            if (this._charts.gpuTemp) {
                this._charts.gpuTemp.setOption({
                    xAxis: { data: ['温度', '显存使用率'] },
                    series: [{ data: [this.gpu.temp || 0, this.gpuMemPercent()] }],
                });
            }
            if (this._charts.gpuTop) {
                const procs = this.gpu.processes.slice(0, 10);
                this._charts.gpuTop.setOption({
                    xAxis: { data: procs.map((proc) => proc.name || proc.pid) },
                    series: [{ data: procs.map((proc) => proc.gpu_mem_mb || proc.used_memory || 0) }],
                });
            }
        },

        _updateDockerCharts() {
            const groups = this.dockerGroupsArray().slice(0, 8);
            const cpuContainers = [...this.docker.containers].sort((a, b) => (b.cpu_percent || 0) - (a.cpu_percent || 0)).slice(0, 8);
            const restartContainers = [...this.docker.containers].sort((a, b) => (b.restart_count || 0) - (a.restart_count || 0)).slice(0, 8);

            if (this._charts.dockerStatus) {
                this._charts.dockerStatus.setOption({
                    series: [{ data: this.dockerStatusData() }],
                });
            }
            if (this._charts.dockerGroups) {
                this._charts.dockerGroups.setOption({
                    yAxis: { data: groups.map((group) => group.name) },
                    series: [
                        { data: groups.map((group) => group.total_cpu || 0) },
                        { data: groups.map((group) => group.total_mem_mb || 0) },
                    ],
                });
            }
            if (this._charts.dockerCpu) {
                this._charts.dockerCpu.setOption({
                    yAxis: { data: cpuContainers.map((container) => container.name) },
                    series: [{ data: cpuContainers.map((container) => container.cpu_percent || 0) }],
                });
            }
            if (this._charts.dockerRestart) {
                this._charts.dockerRestart.setOption({
                    yAxis: { data: restartContainers.map((container) => container.name) },
                    series: [{ data: restartContainers.map((container) => container.restart_count || 0) }],
                });
            }
        },

        _updateSystemCharts() {
            if (this._charts.systemResource) {
                this._charts.systemResource.setOption({
                    xAxis: { data: ['CPU', '内存', '磁盘', 'GPU'] },
                    series: [{ data: this.resourceMixData().map((item) => item.value) }],
                });
            }
            if (this._charts.systemAlerts) {
                this._charts.systemAlerts.setOption({
                    series: [{ data: this.alertDistribution() }],
                });
            }
            if (this._charts.systemStorage) {
                const disks = this.topDisks(10);
                this._charts.systemStorage.setOption({
                    yAxis: { data: disks.map((disk) => disk.mountpoint) },
                    series: [{ data: disks.map((disk) => disk.percent || 0) }],
                });
            }
        },

        _updateVisibleCharts() {
            this._updateOverviewCharts();

            if (this.drillTarget === 'cpu') {
                this._updateCpuCharts();
            } else if (this.drillTarget === 'memory') {
                this._updateMemoryCharts();
            } else if (this.drillTarget === 'disk') {
                this._updateDiskCharts();
            } else if (this.drillTarget === 'network') {
                this._updateNetworkCharts();
            } else if (this.drillTarget === 'gpu') {
                this._updateGpuCharts();
            } else if (this.drillTarget === 'docker') {
                this._updateDockerCharts();
            } else if (this.drillTarget === 'system') {
                this._updateSystemCharts();
            }
        },

        _initOverviewCharts() {
            const sparkConfigs = {
                sparkCpu: '#38bdf8',
                sparkMem: '#4ade80',
                sparkSwap: '#fbbf24',
                sparkDisk: '#fb923c',
                sparkNet: '#38bdf8',
                sparkIo: '#e879f9',
                sparkDocker: '#2dd4bf',
                sparkGpu: '#a78bfa',
                sparkLoad: '#4ade80',
            };

            Object.entries(sparkConfigs).forEach(([id, color]) => {
                const el = document.getElementById(id);
                if (el) {
                    if (this._charts[id]) {
                        this._charts[id].dispose();
                    }
                    this._charts[id] = createSparkline(el, color);
                }
            });

            const overviewTrend = document.getElementById('overview-trend');
            if (overviewTrend) {
                this._charts.overviewTrend = createTrendChart(overviewTrend, {
                    xData: this.trendData.timestamps,
                    yMax: 100,
                    yFormatter: '{value}%',
                    dataZoom: true,
                    series: [
                        { name: 'CPU', data: this.trendData.cpu, color: '#38bdf8' },
                        { name: 'RAM', data: this.trendData.memory, color: '#4ade80' },
                        { name: 'GPU', data: this.trendData.gpu, color: '#a78bfa' },
                        { name: 'Swap', data: this.trendData.swap, color: '#fbbf24' },
                    ],
                });
            }

            const alertsDonut = document.getElementById('overview-alerts-donut');
            if (alertsDonut) {
                this._charts.overviewAlerts = createPieChart(alertsDonut, { data: this.alertDistribution() });
            }

            const dockerDonut = document.getElementById('overview-docker-donut');
            if (dockerDonut) {
                this._charts.overviewDockerStatus = createPieChart(dockerDonut, { data: this.dockerStatusData() });
            }

            const networkTrend = document.getElementById('overview-network-trend');
            if (networkTrend) {
                this._charts.overviewNetworkTrend = createTrendChart(networkTrend, {
                    xData: this.trendData.timestamps,
                    yFormatter: '{value} MB/s',
                    series: [
                        { name: '下行', data: this.trendData.netIn.map((value) => value / 1024 / 1024), color: '#38bdf8' },
                        { name: '上行', data: this.trendData.netOut.map((value) => value / 1024 / 1024), color: '#4ade80' },
                    ],
                });
            }

            const diskUsage = document.getElementById('overview-disk-usage');
            if (diskUsage) {
                this._charts.overviewDiskUsage = createBarChart(diskUsage, {
                    horizontal: true,
                    labels: this.topDisks(8).map((disk) => disk.mountpoint),
                    series: [{ name: '使用率', data: this.topDisks(8).map((disk) => disk.percent || 0), color: '#fb923c' }],
                    xFormatter: '{value}%',
                });
            }

            const topProc = document.getElementById('overview-top-proc');
            if (topProc) {
                this._charts.overviewTopProc = createBarChart(topProc, {
                    horizontal: true,
                    labels: this.topProcessCpuData(8).map((proc) => proc.name || proc.cmd || proc.pid),
                    series: [{ name: 'CPU', data: this.topProcessCpuData(8).map((proc) => proc.cpu_percent || 0), color: '#38bdf8' }],
                    xFormatter: '{value}%',
                });
            }

            const dockerGroups = document.getElementById('overview-docker-groups');
            if (dockerGroups) {
                this._charts.overviewDockerGroups = createBarChart(dockerGroups, {
                    horizontal: true,
                    labels: this.dockerGroupsArray().slice(0, 8).map((group) => group.name),
                    series: [
                        { name: 'CPU%', data: this.dockerGroupsArray().slice(0, 8).map((group) => group.total_cpu || 0), color: '#38bdf8' },
                        { name: 'Memory MB', data: this.dockerGroupsArray().slice(0, 8).map((group) => group.total_mem_mb || 0), color: '#4ade80' },
                    ],
                });
            }

            const resourceMix = document.getElementById('overview-resource-mix');
            if (resourceMix) {
                this._charts.overviewResourceMix = createBarChart(resourceMix, {
                    labels: this.resourceMixData().map((item) => item.name),
                    series: [{ name: '占比', data: this.resourceMixData().map((item) => item.value), color: '#a78bfa' }],
                    yFormatter: '{value}%',
                });
            }

            this._updateOverviewCharts();
        },

        _initDetailCharts(target) {
            this.$nextTick(() => {
                if (target === 'cpu') {
                    const cols = 16;
                    const rows = Math.max(1, Math.ceil((this.cpu.count || 1) / cols));
                    this._charts.cpuGauge = createGaugeChart(document.getElementById('cpu-detail-gauge'), { value: Math.round(this.cpu.overall_percent || 0), name: 'CPU' });
                    this._charts.cpuTrend = createTrendChart(document.getElementById('cpu-detail-load'), {
                        xData: this.trendData.timestamps,
                        yMax: 100,
                        yFormatter: '{value}%',
                        series: [{ name: 'CPU', data: this.trendData.cpu, color: '#38bdf8' }],
                    });
                    this._charts.cpuHeatmap = createHeatmapChart(document.getElementById('cpu-detail-heatmap'), { cols: cols, rows: rows, data: [] });
                    this._charts.cpuTop = createBarChart(document.getElementById('cpu-detail-top'), {
                        horizontal: true,
                        labels: [],
                        series: [{ name: 'CPU', data: [], color: '#38bdf8' }],
                        xFormatter: '{value}%',
                    });
                    this._updateCpuCharts();
                } else if (target === 'memory') {
                    this._charts.memGauge = createGaugeChart(document.getElementById('mem-detail-gauge'), { value: Math.round(this.memoryPercent()), name: 'RAM' });
                    this._charts.memRing = createPieChart(document.getElementById('mem-detail-ring'), { data: [] });
                    this._charts.swapGauge = createGaugeChart(document.getElementById('mem-detail-swap'), { value: Math.round(this.swapPercent()), name: 'Swap' });
                    this._charts.memTrend = createTrendChart(document.getElementById('mem-detail-trend'), {
                        xData: this.trendData.timestamps,
                        yMax: 100,
                        yFormatter: '{value}%',
                        series: [
                            { name: 'RAM', data: this.trendData.memory, color: '#4ade80' },
                            { name: 'Swap', data: this.trendData.swap, color: '#fbbf24' },
                        ],
                    });
                    this._charts.memTop = createBarChart(document.getElementById('mem-detail-top'), {
                        horizontal: true,
                        labels: [],
                        series: [{ name: '内存', data: [], color: '#4ade80' }],
                        xFormatter: '{value}%',
                    });
                    this._updateMemoryCharts();
                } else if (target === 'disk') {
                    this._charts.diskUsage = createBarChart(document.getElementById('disk-detail-usage'), {
                        horizontal: true,
                        labels: [],
                        series: [{ name: '使用率', data: [], color: '#fb923c' }],
                        xFormatter: '{value}%',
                    });
                    this._charts.diskInode = createBarChart(document.getElementById('disk-detail-inode'), {
                        horizontal: true,
                        labels: [],
                        series: [{ name: 'inode', data: [], color: '#a78bfa' }],
                        xFormatter: '{value}%',
                    });
                    this._charts.diskIo = createBarChart(document.getElementById('disk-detail-io'), {
                        horizontal: true,
                        labels: [],
                        series: [
                            { name: 'Read MB/s', data: [], color: '#38bdf8' },
                            { name: 'Write MB/s', data: [], color: '#4ade80' },
                        ],
                    });
                    this._charts.diskDevice = createBarChart(document.getElementById('disk-detail-device'), {
                        horizontal: true,
                        labels: [],
                        series: [{ name: 'Busy', data: [], color: '#f87171' }],
                        xFormatter: '{value}%',
                    });
                    this._updateDiskCharts();
                } else if (target === 'network') {
                    this._charts.networkThroughput = createTrendChart(document.getElementById('network-detail-throughput'), {
                        xData: this.trendData.timestamps,
                        yFormatter: '{value} MB/s',
                        series: [
                            { name: '下行', data: this.trendData.netIn.map((value) => value / 1024 / 1024), color: '#38bdf8' },
                            { name: '上行', data: this.trendData.netOut.map((value) => value / 1024 / 1024), color: '#4ade80' },
                        ],
                    });
                    this._charts.networkTcp = createPieChart(document.getElementById('tcp-detail-pie'), { data: [] });
                    this._charts.networkPackets = createTrendChart(document.getElementById('network-detail-packets'), {
                        xData: this.trendData.timestamps,
                        series: [
                            { name: '入包', data: this.trendData.packetIn, color: '#2dd4bf' },
                            { name: '出包', data: this.trendData.packetOut, color: '#fb923c' },
                        ],
                    });
                    this._charts.networkEvents = createBarChart(document.getElementById('network-detail-events'), {
                        labels: ['Err In', 'Err Out', 'Drop In', 'Drop Out'],
                        series: [{ name: '次数', data: [], color: '#f87171' }],
                    });
                    this._updateNetworkCharts();
                } else if (target === 'gpu') {
                    this._charts.gpuGauge = createGaugeChart(document.getElementById('gpu-detail-gauge'), { value: Math.round(this.gpu.util || 0), name: 'GPU' });
                    this._charts.gpuMem = createPieChart(document.getElementById('gpu-detail-mem'), { data: [] });
                    this._charts.gpuTemp = createBarChart(document.getElementById('gpu-detail-temp'), {
                        labels: ['温度', '显存占比'],
                        series: [{ name: '值', data: [], color: '#a78bfa' }],
                    });
                    this._charts.gpuTop = createBarChart(document.getElementById('gpu-detail-top'), {
                        labels: [],
                        series: [{ name: '显存 MB', data: [], color: '#38bdf8' }],
                        rotate: 20,
                    });
                    this._updateGpuCharts();
                } else if (target === 'docker') {
                    this._charts.dockerStatus = createPieChart(document.getElementById('docker-detail-status'), { data: [] });
                    this._charts.dockerGroups = createBarChart(document.getElementById('docker-detail-groups'), {
                        horizontal: true,
                        labels: [],
                        series: [
                            { name: 'CPU%', data: [], color: '#38bdf8' },
                            { name: 'Memory MB', data: [], color: '#4ade80' },
                        ],
                    });
                    this._charts.dockerCpu = createBarChart(document.getElementById('docker-detail-cpu'), {
                        horizontal: true,
                        labels: [],
                        series: [{ name: 'CPU%', data: [], color: '#38bdf8' }],
                        xFormatter: '{value}%',
                    });
                    this._charts.dockerRestart = createBarChart(document.getElementById('docker-detail-restarts'), {
                        horizontal: true,
                        labels: [],
                        series: [{ name: '重启次数', data: [], color: '#f87171' }],
                    });
                    this._updateDockerCharts();
                } else if (target === 'system') {
                    this._charts.systemResource = createBarChart(document.getElementById('system-detail-resource'), {
                        labels: ['CPU', '内存', '磁盘', 'GPU'],
                        series: [{ name: '占比', data: [], color: '#38bdf8' }],
                        yFormatter: '{value}%',
                    });
                    this._charts.systemAlerts = createPieChart(document.getElementById('system-detail-alerts'), { data: [] });
                    this._charts.systemStorage = createBarChart(document.getElementById('system-detail-storage'), {
                        horizontal: true,
                        labels: [],
                        series: [{ name: '使用率', data: [], color: '#fb923c' }],
                        xFormatter: '{value}%',
                    });
                    this._updateSystemCharts();
                }
            });
        },

        drillTo(target) {
            this.drillTarget = target;
            this.$nextTick(() => this._initDetailCharts(target));
        },

        backToOverview() {
            const overviewKeys = [
                'overviewTrend', 'overviewAlerts', 'overviewDockerStatus', 'overviewNetworkTrend',
                'overviewDiskUsage', 'overviewTopProc', 'overviewDockerGroups', 'overviewResourceMix',
                'sparkCpu', 'sparkMem', 'sparkSwap', 'sparkDisk', 'sparkNet', 'sparkIo',
                'sparkDocker', 'sparkGpu', 'sparkLoad',
            ];
            Object.keys(this._charts).forEach((key) => {
                if (!overviewKeys.includes(key) && this._charts[key]) {
                    this._charts[key].dispose();
                    delete this._charts[key];
                }
            });
            this.drillTarget = null;
            this.$nextTick(() => this._initOverviewCharts());
        },

        openLocate(type, params) {
            this.locateTarget = Object.assign({ type: type }, params || {});
            if (type === 'processes') {
                this._loadProcesses();
            }
            if (type === 'alerts') {
                this._loadRecentAlerts();
            }
        },

        closeLocate() {
            this.locateTarget = null;
        },

        async killProcess(pid, username) {
            if (!username) {
                alert('缺少进程所属用户，无法执行终止操作');
                return;
            }
            if (!confirm('确定要终止进程 ' + pid + ' 吗？')) {
                return;
            }
            try {
                const response = await fetch(`/api/users/${encodeURIComponent(username)}/kill/${pid}`, {
                    method: 'POST',
                });
                if (!response.ok) {
                    throw new Error('request failed');
                }
                await Promise.all([this._loadProcesses(), this._loadSnapshot()]);
            } catch (e) {
                alert('操作失败');
            }
        },
    };
}
