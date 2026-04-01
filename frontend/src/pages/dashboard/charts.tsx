/**
 * Dashboard chart components - all ECharts-based visualizations
 * used in the overview grid and drill-down detail panels.
 */

import { useMemo } from 'react'
import ReactECharts from 'echarts-for-react'
import * as echarts from 'echarts/core'
import { cn } from '@/lib/utils'
import { ensureArray } from '@/lib/utils'
import ErrorBoundary from '@/components/ErrorBoundary'
import { THEME_NAME, ECHARTS_COLORS, PERIOD_OPTIONS } from './constants'
import type { AlertSummary, HistoryPeriod, HistoryPoint } from './types'
import type { MetricsData } from '@/hooks/useWebSocket'
import { statusHex } from './utils'

// ---------------------------------------------------------------------------
// Sparkline mini chart
// ---------------------------------------------------------------------------
export function Sparkline({ data, color }: { data: number[]; color: string }) {
  const option = useMemo(() => ({
    grid: { top: 2, right: 0, bottom: 2, left: 0 },
    xAxis: { type: 'category' as const, show: false, data: data.map((_, i) => i) },
    yAxis: { type: 'value' as const, show: false, min: 0, max: 100 },
    series: [{
      type: 'line' as const,
      data,
      smooth: true,
      symbol: 'none',
      lineStyle: { width: 1.5, color },
      areaStyle: {
        color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
          { offset: 0, color: color + '40' },
          { offset: 1, color: color + '05' },
        ]),
      },
    }],
    tooltip: { show: false },
  }), [data, color])

  return (
    <ReactECharts
      option={option}
      theme={THEME_NAME}
      style={{ height: 60, width: '100%' }}
      opts={{ renderer: 'canvas' }}
      notMerge
      lazyUpdate
    />
  )
}

// ---------------------------------------------------------------------------
// Detail chart (larger, with axes)
// ---------------------------------------------------------------------------
export function DetailChart({
  data,
  labels,
  color,
  title,
  unit = '%',
  max,
}: {
  data: number[]
  labels: string[]
  color: string
  title: string
  unit?: string
  max?: number
}) {
  const option = useMemo(() => ({
    grid: { top: 36, right: 20, bottom: 28, left: 50 },
    title: { text: title, textStyle: { color: '#e2e8f0', fontSize: 14, fontWeight: 500 }, left: 8, top: 8 },
    xAxis: {
      type: 'category' as const,
      data: labels,
      axisLabel: { fontSize: 10 },
      boundaryGap: false,
    },
    yAxis: {
      type: 'value' as const,
      axisLabel: { formatter: `{value}${unit}`, fontSize: 10 },
      min: 0,
      ...(max != null ? { max } : {}),
    },
    tooltip: {
      trigger: 'axis' as const,
      formatter: (params: Array<{ value: number; axisValue: string }>) => {
        const p = params[0]
        return `${p.axisValue}<br/>${(p.value ?? 0).toFixed(1)}${unit}`
      },
    },
    series: [{
      type: 'line' as const,
      data,
      smooth: true,
      symbol: 'none',
      lineStyle: { width: 2, color },
      areaStyle: {
        color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
          { offset: 0, color: color + '30' },
          { offset: 1, color: color + '05' },
        ]),
      },
    }],
  }), [data, labels, color, title, unit, max])

  return (
    <ReactECharts
      option={option}
      theme={THEME_NAME}
      style={{ height: 280, width: '100%' }}
      opts={{ renderer: 'canvas' }}
      notMerge
      lazyUpdate
    />
  )
}

// ---------------------------------------------------------------------------
// Multi-line detail chart (e.g., per-CPU)
// ---------------------------------------------------------------------------
export function MultiLineChart({
  series,
  labels,
  title,
  unit = '%',
}: {
  series: { name: string; data: number[]; color: string }[]
  labels: string[]
  title: string
  unit?: string
}) {
  const option = useMemo(() => ({
    grid: { top: 48, right: 20, bottom: 28, left: 50 },
    title: { text: title, textStyle: { color: '#e2e8f0', fontSize: 14, fontWeight: 500 }, left: 8, top: 8 },
    legend: { top: 8, right: 12, textStyle: { fontSize: 10 } },
    xAxis: { type: 'category' as const, data: labels, axisLabel: { fontSize: 10 }, boundaryGap: false },
    yAxis: { type: 'value' as const, axisLabel: { formatter: `{value}${unit}`, fontSize: 10 }, min: 0, max: 100 },
    tooltip: { trigger: 'axis' as const },
    series: series.map((s) => ({
      name: s.name,
      type: 'line' as const,
      data: s.data,
      smooth: true,
      symbol: 'none',
      lineStyle: { width: 1.5, color: s.color },
    })),
  }), [series, labels, title, unit])

  return (
    <ReactECharts
      option={option}
      theme={THEME_NAME}
      style={{ height: 320, width: '100%' }}
      opts={{ renderer: 'canvas' }}
      notMerge
      lazyUpdate
    />
  )
}

// ---------------------------------------------------------------------------
// Overview: System Resource Trend (8 cols)
// ---------------------------------------------------------------------------
export function SystemTrendChart({
  historyData,
  period,
  setPeriod,
}: {
  historyData: HistoryPoint[]
  period: HistoryPeriod
  setPeriod: (p: HistoryPeriod) => void
}) {
  const option = useMemo(() => {
    const timestamps = historyData.map((h) => {
      const d = new Date(h.timestamp)
      return `${d.getHours().toString().padStart(2, '0')}:${d.getMinutes().toString().padStart(2, '0')}`
    })
    const cpuData = historyData.map((h) => h.value.cpu?.overall_percent ?? 0)
    const memData = historyData.map((h) => h.value.memory?.percent ?? 0)
    const gpuData = historyData.map((h) => h.value.gpu?.utilization ?? 0)
    const swapData = historyData.map((h) => h.value.swap?.percent ?? 0)

    return {
      grid: { top: 48, right: 20, bottom: 28, left: 50 },
      title: { text: '系统资源趋势', textStyle: { color: '#e2e8f0', fontSize: 14, fontWeight: 500 }, left: 8, top: 8 },
      legend: { top: 8, right: 12, textStyle: { fontSize: 10 } },
      tooltip: { trigger: 'axis' as const },
      xAxis: { type: 'category' as const, data: timestamps, axisLabel: { fontSize: 10 }, boundaryGap: false },
      yAxis: { type: 'value' as const, axisLabel: { formatter: '{value}%', fontSize: 10 }, min: 0, max: 100 },
      series: [
        { name: 'CPU', type: 'line' as const, data: cpuData, smooth: true, symbol: 'none', lineStyle: { width: 1.5, color: '#38bdf8' }, areaStyle: { color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [{ offset: 0, color: '#38bdf820' }, { offset: 1, color: '#38bdf805' }]) } },
        { name: '内存', type: 'line' as const, data: memData, smooth: true, symbol: 'none', lineStyle: { width: 1.5, color: '#4ade80' }, areaStyle: { color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [{ offset: 0, color: '#4ade8020' }, { offset: 1, color: '#4ade8005' }]) } },
        { name: 'GPU', type: 'line' as const, data: gpuData, smooth: true, symbol: 'none', lineStyle: { width: 1.5, color: '#a78bfa' }, areaStyle: { color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [{ offset: 0, color: '#a78bfa20' }, { offset: 1, color: '#a78bfa05' }]) } },
        { name: 'Swap', type: 'line' as const, data: swapData, smooth: true, symbol: 'none', lineStyle: { width: 1.5, color: '#fbbf24' }, areaStyle: { color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [{ offset: 0, color: '#fbbf2420' }, { offset: 1, color: '#fbbf2405' }]) } },
      ],
    }
  }, [historyData])

  return (
    <div className="bg-card border border-border rounded-lg p-3 relative">
      <div className="absolute top-3 right-3 flex gap-1 z-10">
        {PERIOD_OPTIONS.map((opt) => (
          <button
            key={opt.value}
            onClick={() => setPeriod(opt.value)}
            className={cn(
              'px-2 py-0.5 text-[10px] rounded font-medium transition-colors',
              period === opt.value
                ? 'bg-accent text-white'
                : 'bg-bg2 text-text3 hover:text-text hover:bg-border',
            )}
          >
            {opt.label}
          </button>
        ))}
      </div>
      <ReactECharts option={option} theme={THEME_NAME} style={{ height: 280, width: '100%' }} opts={{ renderer: 'canvas' }} notMerge lazyUpdate />
    </div>
  )
}

// ---------------------------------------------------------------------------
// Overview: Alert Distribution donut (4 cols)
// ---------------------------------------------------------------------------
export function AlertDonut({ summary }: { summary: AlertSummary | null }) {
  const option = useMemo(() => {
    const critical = summary?.critical ?? 0
    const warning = summary?.warning ?? 0
    const info = summary?.info ?? 0
    const total = critical + warning + info

    return {
      title: { text: '告警分布', subtext: total > 0 ? `共 ${total} 条` : '无告警', textStyle: { color: '#e2e8f0', fontSize: 13, fontWeight: 500 }, subtextStyle: { color: '#64748b', fontSize: 10 }, left: 'center', top: 8 },
      tooltip: { trigger: 'item' as const },
      series: [{
        type: 'pie' as const,
        radius: ['40%', '65%'],
        center: ['50%', '58%'],
        data: [
          { value: critical, name: '严重', itemStyle: { color: '#f87171' } },
          { value: warning, name: '警告', itemStyle: { color: '#fbbf24' } },
          { value: info, name: '信息', itemStyle: { color: '#38bdf8' } },
        ].filter((d) => d.value > 0),
        label: { show: true, color: '#94a3b8', fontSize: 10 },
        emphasis: { itemStyle: { shadowBlur: 10, shadowColor: 'rgba(0,0,0,0.3)' } },
      }],
    }
  }, [summary])

  return (
    <div className="bg-card border border-border rounded-lg p-3">
      <ReactECharts option={option} theme={THEME_NAME} style={{ height: 180, width: '100%' }} opts={{ renderer: 'canvas' }} notMerge lazyUpdate />
    </div>
  )
}

// ---------------------------------------------------------------------------
// Overview: Docker Health donut (4 cols)
// ---------------------------------------------------------------------------
export function DockerHealthDonut({ containers }: { containers: Array<{ state: string }> | null }) {
  const option = useMemo(() => {
    const items = ensureArray<{ state: string }>(containers)
    const running = items.filter((c) => c.state === 'running').length
    const stopped = items.filter((c) => c.state === 'exited' || c.state === 'dead').length
    const restarting = items.filter((c) => c.state === 'restarting').length
    const other = items.length - running - stopped - restarting
    const total = items.length

    return {
      title: { text: '容器健康度', subtext: total > 0 ? `共 ${total} 个` : '无容器', textStyle: { color: '#e2e8f0', fontSize: 13, fontWeight: 500 }, subtextStyle: { color: '#64748b', fontSize: 10 }, left: 'center', top: 8 },
      tooltip: { trigger: 'item' as const },
      series: [{
        type: 'pie' as const,
        radius: ['40%', '65%'],
        center: ['50%', '58%'],
        data: [
          { value: running, name: '运行中', itemStyle: { color: '#4ade80' } },
          { value: stopped, name: '已停止', itemStyle: { color: '#f87171' } },
          { value: restarting, name: '重启中', itemStyle: { color: '#fbbf24' } },
          ...(other > 0 ? [{ value: other, name: '其他', itemStyle: { color: '#64748b' } }] : []),
        ].filter((d) => d.value > 0),
        label: { show: true, color: '#94a3b8', fontSize: 10 },
        emphasis: { itemStyle: { shadowBlur: 10, shadowColor: 'rgba(0,0,0,0.3)' } },
      }],
    }
  }, [containers])

  return (
    <div className="bg-card border border-border rounded-lg p-3">
      <ReactECharts option={option} theme={THEME_NAME} style={{ height: 180, width: '100%' }} opts={{ renderer: 'canvas' }} notMerge lazyUpdate />
    </div>
  )
}

// ---------------------------------------------------------------------------
// Overview: Network Throughput Trend (4 cols)
// ---------------------------------------------------------------------------
export function NetworkTrendChart({ history }: { history: MetricsData[] }) {
  const option = useMemo(() => {
    const recvRates: number[] = []
    const sentRates: number[] = []
    const labels: string[] = []
    for (let i = 1; i < history.length; i++) {
      const dt = new Date(history[i].timestamp).getTime() - new Date(history[i - 1].timestamp).getTime()
      const rx = Math.max(0, ((history[i].network?.bytes_recv ?? 0) - (history[i - 1].network?.bytes_recv ?? 0)) * 1000 / (dt || 1000))
      const tx = Math.max(0, ((history[i].network?.bytes_sent ?? 0) - (history[i - 1].network?.bytes_sent ?? 0)) * 1000 / (dt || 1000))
      recvRates.push(Math.round(rx / 1024))
      sentRates.push(Math.round(tx / 1024))
      labels.push(`${i}`)
    }

    return {
      grid: { top: 40, right: 12, bottom: 24, left: 48 },
      title: { text: '网络吞吐趋势', textStyle: { color: '#e2e8f0', fontSize: 13, fontWeight: 500 }, left: 8, top: 8 },
      legend: { top: 8, right: 8, textStyle: { fontSize: 10 } },
      tooltip: { trigger: 'axis' as const },
      xAxis: { type: 'category' as const, data: labels, show: false },
      yAxis: { type: 'value' as const, axisLabel: { formatter: '{value}', fontSize: 9 }, name: 'KB/s', nameTextStyle: { fontSize: 9, color: '#64748b' } },
      series: [
        { name: '接收', type: 'line' as const, data: recvRates, smooth: true, symbol: 'none', lineStyle: { width: 1.5, color: '#38bdf8' }, areaStyle: { color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [{ offset: 0, color: '#38bdf820' }, { offset: 1, color: '#38bdf805' }]) } },
        { name: '发送', type: 'line' as const, data: sentRates, smooth: true, symbol: 'none', lineStyle: { width: 1.5, color: '#4ade80' }, areaStyle: { color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [{ offset: 0, color: '#4ade8020' }, { offset: 1, color: '#4ade8005' }]) } },
      ],
    }
  }, [history])

  if (history.length < 2) {
    return (
      <div className="bg-card border border-border rounded-lg p-3 flex items-center justify-center h-[220px]">
        <span className="text-text3 text-xs">等待数据...</span>
      </div>
    )
  }

  return (
    <div className="bg-card border border-border rounded-lg p-3">
      <ReactECharts option={option} theme={THEME_NAME} style={{ height: 200, width: '100%' }} opts={{ renderer: 'canvas' }} notMerge lazyUpdate />
    </div>
  )
}

// ---------------------------------------------------------------------------
// Overview: Disk & Mount Pressure (4 cols)
// ---------------------------------------------------------------------------
export function DiskPressureChart({ metrics }: { metrics: MetricsData }) {
  const option = useMemo(() => {
    const partitions = (metrics.disk?.partitions ?? []).slice(0, 8)
    const names = partitions.map((p) => p.mountpoint.length > 12 ? '...' + p.mountpoint.slice(-10) : p.mountpoint)
    const values = partitions.map((p) => p.percent)

    return {
      grid: { top: 36, right: 16, bottom: 8, left: 80 },
      title: { text: '磁盘与挂载点压力', textStyle: { color: '#e2e8f0', fontSize: 13, fontWeight: 500 }, left: 8, top: 8 },
      tooltip: { trigger: 'axis' as const, formatter: (params: Array<{ name: string; value: number }>) => `${params[0].name}: ${params[0].value}%` },
      xAxis: { type: 'value' as const, max: 100, axisLabel: { formatter: '{value}%', fontSize: 9 } },
      yAxis: { type: 'category' as const, data: names, axisLabel: { fontSize: 9 }, inverse: true },
      series: [{
        type: 'bar' as const,
        data: values.map((v) => ({
          value: v,
          itemStyle: { color: statusHex(v), borderRadius: [0, 3, 3, 0] },
        })),
        barWidth: 14,
        label: { show: true, position: 'right' as const, formatter: '{c}%', fontSize: 9, color: '#94a3b8' },
      }],
    }
  }, [metrics])

  return (
    <div className="bg-card border border-border rounded-lg p-3">
      <ReactECharts option={option} theme={THEME_NAME} style={{ height: 200, width: '100%' }} opts={{ renderer: 'canvas' }} notMerge lazyUpdate />
    </div>
  )
}

// ---------------------------------------------------------------------------
// Overview: Top Process Resource (4 cols)
// ---------------------------------------------------------------------------
export function TopProcessChart({ processes }: { processes: Array<{ name: string; cpu_percent: number; mem_rss_mb: number }> | null }) {
  const option = useMemo(() => {
    const top5 = ensureArray<{ name: string; cpu_percent: number; mem_rss_mb: number }>(processes).slice(0, 5)
    const names = top5.map((p) => p.name.length > 12 ? p.name.slice(0, 12) + '...' : p.name)

    return {
      grid: { top: 36, right: 16, bottom: 24, left: 80 },
      title: { text: 'Top 进程资源', textStyle: { color: '#e2e8f0', fontSize: 13, fontWeight: 500 }, left: 8, top: 8 },
      tooltip: { trigger: 'axis' as const },
      legend: { top: 8, right: 8, textStyle: { fontSize: 10 } },
      xAxis: { type: 'value' as const, axisLabel: { fontSize: 9 } },
      yAxis: { type: 'category' as const, data: names, axisLabel: { fontSize: 9 }, inverse: true },
      series: [
        { name: 'CPU %', type: 'bar' as const, data: top5.map((p) => p.cpu_percent), barWidth: 8, itemStyle: { color: '#38bdf8', borderRadius: [0, 3, 3, 0] } },
        { name: 'Mem MB', type: 'bar' as const, data: top5.map((p) => p.mem_rss_mb), barWidth: 8, itemStyle: { color: '#4ade80', borderRadius: [0, 3, 3, 0] } },
      ],
    }
  }, [processes])

  return (
    <div className="bg-card border border-border rounded-lg p-3">
      <ReactECharts option={option} theme={THEME_NAME} style={{ height: 200, width: '100%' }} opts={{ renderer: 'canvas' }} notMerge lazyUpdate />
    </div>
  )
}

// ---------------------------------------------------------------------------
// Overview: Container Group Resource (4 cols)
// ---------------------------------------------------------------------------
export function ContainerGroupChart({ containers }: { containers: Array<{ name: string; state: string }> | null }) {
  const option = useMemo(() => {
    // Group by compose project prefix (name before the first hyphen-number pattern)
    const groups: Record<string, { running: number; stopped: number }> = {}
    for (const c of ensureArray<{ name: string; state: string }>(containers)) {
      // Try to extract stack name: e.g., "docker-api-1" -> "docker", "grid-autopilot-redis" -> "grid-autopilot"
      const name = typeof c.name === 'string' ? c.name : 'unknown'
      const match = name.match(/^(.+?)-[^-]+-?\d*$/) || name.match(/^(.+?)-\d+$/)
      const stack = match?.[1] ?? name
      if (!groups[stack]) groups[stack] = { running: 0, stopped: 0 }
      if (c.state === 'running') groups[stack].running++
      else groups[stack].stopped++
    }
    const stacks = Object.entries(groups).sort((a, b) => (b[1].running + b[1].stopped) - (a[1].running + a[1].stopped)).slice(0, 6)
    const names = stacks.map(([k]) => k.length > 14 ? k.slice(0, 14) + '...' : k)

    return {
      grid: { top: 36, right: 16, bottom: 24, left: 90 },
      title: { text: '容器组资源', textStyle: { color: '#e2e8f0', fontSize: 13, fontWeight: 500 }, left: 8, top: 8 },
      tooltip: { trigger: 'axis' as const },
      legend: { top: 8, right: 8, textStyle: { fontSize: 10 } },
      xAxis: { type: 'value' as const, axisLabel: { fontSize: 9 } },
      yAxis: { type: 'category' as const, data: names, axisLabel: { fontSize: 9 }, inverse: true },
      series: [
        { name: '运行', type: 'bar' as const, stack: 'total', data: stacks.map(([, v]) => v.running), barWidth: 14, itemStyle: { color: '#4ade80', borderRadius: [0, 0, 0, 0] } },
        { name: '停止', type: 'bar' as const, stack: 'total', data: stacks.map(([, v]) => v.stopped), barWidth: 14, itemStyle: { color: '#f87171', borderRadius: [0, 3, 3, 0] } },
      ],
    }
  }, [containers])

  return (
    <div className="bg-card border border-border rounded-lg p-3">
      <ReactECharts option={option} theme={THEME_NAME} style={{ height: 200, width: '100%' }} opts={{ renderer: 'canvas' }} notMerge lazyUpdate />
    </div>
  )
}

// ---------------------------------------------------------------------------
// Overview: Resource Mix Radar (4 cols)
// ---------------------------------------------------------------------------
export function ResourceRadar({ metrics }: { metrics: MetricsData }) {
  const option = useMemo(() => {
    const cpu = metrics.cpu?.overall_percent ?? 0
    const mem = metrics.memory?.percent ?? 0
    const swap = (metrics.swap?.total ?? 0) > 0 ? (metrics.swap?.percent ?? 0) : 0
    const root = metrics.disk?.partitions?.find((p) => p.mountpoint === '/') ?? metrics.disk?.partitions?.[0]
    const disk = root?.percent ?? 0
    const gpu = metrics.gpu?.utilization ?? 0

    return {
      title: { text: '资源配比', textStyle: { color: '#e2e8f0', fontSize: 13, fontWeight: 500 }, left: 'center', top: 8 },
      tooltip: { trigger: 'item' as const },
      radar: {
        indicator: [
          { name: 'CPU', max: 100 },
          { name: '内存', max: 100 },
          { name: 'Swap', max: 100 },
          { name: '磁盘', max: 100 },
          { name: 'GPU', max: 100 },
        ],
        center: ['50%', '58%'],
        radius: '55%',
        axisName: { color: '#94a3b8', fontSize: 10 },
        splitArea: { areaStyle: { color: ['transparent'] } },
        splitLine: { lineStyle: { color: '#1e293b' } },
        axisLine: { lineStyle: { color: '#334155' } },
      },
      series: [{
        type: 'radar' as const,
        data: [{
          value: [cpu, mem, swap, disk, gpu],
          name: '当前使用率',
          areaStyle: { color: 'rgba(56,189,248,0.15)' },
          lineStyle: { color: '#38bdf8', width: 1.5 },
          itemStyle: { color: '#38bdf8' },
        }],
      }],
    }
  }, [metrics])

  return (
    <div className="bg-card border border-border rounded-lg p-3">
      <ReactECharts option={option} theme={THEME_NAME} style={{ height: 200, width: '100%' }} opts={{ renderer: 'canvas' }} notMerge lazyUpdate />
    </div>
  )
}

// ---------------------------------------------------------------------------
// Overview Charts Grid (the complete 8-chart overview)
// ---------------------------------------------------------------------------
export function OverviewChartsGrid({
  historyData,
  period,
  setPeriod,
  alertSummary,
  containers,
  wsHistory,
  metrics,
  topProcesses,
}: {
  historyData: HistoryPoint[]
  period: HistoryPeriod
  setPeriod: (p: HistoryPeriod) => void
  alertSummary: AlertSummary | null
  containers: Array<{ name: string; state: string; image: string; status: string }> | null
  wsHistory: MetricsData[]
  metrics: MetricsData
  topProcesses: Array<{ name: string; cpu_percent: number; mem_rss_mb: number }> | null
}) {
  return (
    <div className="mt-6">
      <h3 className="text-sm font-medium text-text3 mb-3 uppercase tracking-wider">概览图表</h3>
      {/* Row 1: System Trend (8 cols) + Alert + Docker donuts (4 cols stacked) */}
      <div className="grid grid-cols-12 gap-4 mb-4">
        <div className="col-span-12 xl:col-span-8">
          <ErrorBoundary><SystemTrendChart historyData={historyData} period={period} setPeriod={setPeriod} /></ErrorBoundary>
        </div>
        <div className="col-span-12 sm:col-span-6 xl:col-span-4 flex flex-col gap-4">
          <ErrorBoundary><AlertDonut summary={alertSummary} /></ErrorBoundary>
          <ErrorBoundary><DockerHealthDonut containers={containers} /></ErrorBoundary>
        </div>
      </div>
      {/* Row 2: Network (4) + Disk (4) + Top Process (4) */}
      <div className="grid grid-cols-12 gap-4 mb-4">
        <div className="col-span-12 sm:col-span-6 xl:col-span-4">
          <ErrorBoundary><NetworkTrendChart history={wsHistory} /></ErrorBoundary>
        </div>
        <div className="col-span-12 sm:col-span-6 xl:col-span-4">
          <ErrorBoundary><DiskPressureChart metrics={metrics} /></ErrorBoundary>
        </div>
        <div className="col-span-12 sm:col-span-6 xl:col-span-4">
          <ErrorBoundary><TopProcessChart processes={topProcesses} /></ErrorBoundary>
        </div>
      </div>
      {/* Row 3: Container Groups (4) + Resource Mix (4) */}
      <div className="grid grid-cols-12 gap-4">
        <div className="col-span-12 sm:col-span-6 xl:col-span-4">
          <ErrorBoundary><ContainerGroupChart containers={containers} /></ErrorBoundary>
        </div>
        <div className="col-span-12 sm:col-span-6 xl:col-span-4">
          <ErrorBoundary><ResourceRadar metrics={metrics} /></ErrorBoundary>
        </div>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Disk I/O chart (used in DiskDetail)
// ---------------------------------------------------------------------------
export function DiskIoChart({ history }: { history: MetricsData[] }) {
  const labels = history.map((_, i) => `${i}`)
  const readRates: number[] = []
  const writeRates: number[] = []

  for (let i = 1; i < history.length; i++) {
    const curr = (history[i] as unknown as Record<string, unknown>).diskio as { read_bytes?: number; write_bytes?: number } | undefined
    const prev = (history[i - 1] as unknown as Record<string, unknown>).diskio as { read_bytes?: number; write_bytes?: number } | undefined
    const dt = new Date(history[i].timestamp).getTime() - new Date(history[i - 1].timestamp).getTime()
    if (curr && prev && dt > 0) {
      readRates.push(Math.max(0, Math.round(((curr.read_bytes ?? 0) - (prev.read_bytes ?? 0)) * 1000 / dt / 1024)))
      writeRates.push(Math.max(0, Math.round(((curr.write_bytes ?? 0) - (prev.write_bytes ?? 0)) * 1000 / dt / 1024)))
    } else {
      readRates.push(0)
      writeRates.push(0)
    }
  }

  if (readRates.length < 2) {
    return (
      <div className="bg-card border border-border rounded-lg p-3 text-center text-text3 text-xs py-6">
        磁盘 I/O 数据不足
      </div>
    )
  }

  return (
    <div className="bg-card border border-border rounded-lg p-3">
      <MultiLineChart
        series={[
          { name: '读取', data: readRates, color: '#38bdf8' },
          { name: '写入', data: writeRates, color: '#fb923c' },
        ]}
        labels={labels.slice(1)}
        title="磁盘 I/O 速率 (KB/s)"
        unit=" KB/s"
      />
    </div>
  )
}
