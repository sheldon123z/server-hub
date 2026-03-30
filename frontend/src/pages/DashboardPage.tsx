/**
 * Dashboard page - main landing page with 9 metric cards,
 * real-time sparklines, and drill-down detail panels.
 */

import { useState, useEffect, useMemo, useCallback } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import ReactECharts from 'echarts-for-react'
import * as echarts from 'echarts/core'
import {
  Monitor, Cpu, MemoryStick, HardDrive, Network,
  Activity, Container, Thermometer, RefreshCw, Disc3, ChevronLeft,
  Skull, AlertTriangle, Bell,
} from 'lucide-react'
import client from '@/api/client'
import toast from 'react-hot-toast'
import { useWebSocket, type MetricsData, type AlertData } from '@/hooks/useWebSocket'
import {
  normalizeDockerContainers,
  normalizeGpuProcesses,
  normalizeMetricsSnapshot,
  normalizeTimestamp,
  normalizeTopProcesses,
} from '@/lib/monitoring'
import { useServerStore } from '@/stores/serverStore'
import { cn, ensureArray, ensureRecord, formatBytes, formatPercent } from '@/lib/utils'
import ErrorBoundary from '@/components/ErrorBoundary'

// ---------------------------------------------------------------------------
// ECharts dark theme (registered once)
// ---------------------------------------------------------------------------
const THEME_NAME = 'serverhub-dark'
const ECHARTS_COLORS = ['#38bdf8', '#4ade80', '#fbbf24', '#f87171', '#a78bfa', '#fb923c']

echarts.registerTheme(THEME_NAME, {
  backgroundColor: 'transparent',
  color: ECHARTS_COLORS,
  tooltip: {
    backgroundColor: 'rgba(15,23,42,0.95)',
    borderColor: '#334155',
    textStyle: { color: '#e2e8f0', fontSize: 12 },
  },
  legend: { textStyle: { color: '#94a3b8' } },
  categoryAxis: {
    axisLine: { lineStyle: { color: '#334155' } },
    axisTick: { lineStyle: { color: '#334155' } },
    axisLabel: { color: '#64748b' },
    splitLine: { lineStyle: { color: '#1e293b' } },
  },
  valueAxis: {
    axisLine: { lineStyle: { color: '#334155' } },
    axisTick: { lineStyle: { color: '#334155' } },
    axisLabel: { color: '#64748b' },
    splitLine: { lineStyle: { color: '#1e293b' } },
  },
})

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------
function statusColor(percent: number): string {
  if (percent < 30) return 'text-green'
  if (percent < 60) return 'text-accent'
  if (percent < 85) return 'text-yellow'
  return 'text-red'
}

function statusHex(percent: number): string {
  if (percent < 30) return '#4ade80'
  if (percent < 60) return '#38bdf8'
  if (percent < 85) return '#fbbf24'
  return '#f87171'
}

function formatUptime(seconds: number): string {
  const d = Math.floor(seconds / 86400)
  const h = Math.floor((seconds % 86400) / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  if (d > 0) return `${d}d ${h}h ${m}m`
  if (h > 0) return `${h}h ${m}m`
  return `${m}m`
}

function formatRate(curr: number, prev: number, intervalMs: number): string {
  if (intervalMs <= 0) return '0 B/s'
  const rate = Math.max(0, (curr - prev) * 1000 / intervalMs)
  return formatBytes(rate) + '/s'
}

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------
interface AlertSummary {
  active_rules: number
  critical: number
  warning: number
  info: number
  total_24h: number
}

interface RecentAlert {
  id: number
  rule_name: string
  level: string
  message: string
  created_at: string
}

type CardId = 'host' | 'cpu' | 'memory' | 'swap' | 'disk' | 'network' | 'diskio' | 'docker' | 'gpu'

interface CardConfig {
  id: CardId
  label: string
  icon: typeof Cpu
}

const CARDS: CardConfig[] = [
  { id: 'host', label: '主机状态', icon: Monitor },
  { id: 'cpu', label: 'CPU', icon: Cpu },
  { id: 'memory', label: '内存', icon: MemoryStick },
  { id: 'swap', label: 'Swap', icon: Disc3 },
  { id: 'disk', label: '磁盘', icon: HardDrive },
  { id: 'network', label: '网络', icon: Network },
  { id: 'diskio', label: '磁盘 I/O', icon: Activity },
  { id: 'docker', label: 'Docker', icon: Container },
  { id: 'gpu', label: 'GPU', icon: Thermometer },
]

// ---------------------------------------------------------------------------
// Sparkline mini chart
// ---------------------------------------------------------------------------
function Sparkline({ data, color }: { data: number[]; color: string }) {
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
function DetailChart({
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
function MultiLineChart({
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
// History period options
// ---------------------------------------------------------------------------
type HistoryPeriod = '1' | '6' | '24' | '72'

const PERIOD_OPTIONS: { value: HistoryPeriod; label: string }[] = [
  { value: '1', label: '1h' },
  { value: '6', label: '6h' },
  { value: '24', label: '24h' },
  { value: '72', label: '3d' },
]

// ---------------------------------------------------------------------------
// History data types
// ---------------------------------------------------------------------------
interface HistoryPoint {
  timestamp: string
  value: {
    cpu?: { overall_percent: number }
    memory?: { percent: number }
    swap?: { percent: number }
    gpu?: { utilization: number }
    network?: { bytes_recv: number; bytes_sent: number }
    disk?: { partitions: Array<{ mountpoint: string; total: number; used: number; percent: number }> }
  }
}

// ---------------------------------------------------------------------------
// Overview: System Resource Trend (8 cols)
// ---------------------------------------------------------------------------
function SystemTrendChart({
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
function AlertDonut({ summary }: { summary: AlertSummary | null }) {
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
function DockerHealthDonut({ containers }: { containers: Array<{ state: string }> | null }) {
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
function NetworkTrendChart({ history }: { history: MetricsData[] }) {
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
function DiskPressureChart({ metrics }: { metrics: MetricsData }) {
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
function TopProcessChart({ processes }: { processes: Array<{ name: string; cpu_percent: number; mem_rss_mb: number }> | null }) {
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
function ContainerGroupChart({ containers }: { containers: Array<{ name: string; state: string }> | null }) {
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
function ResourceRadar({ metrics }: { metrics: MetricsData }) {
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
function OverviewChartsGrid({
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
// Card value extractors
// ---------------------------------------------------------------------------
function getCardValue(id: CardId, m: MetricsData | null, dockerCount: number | null): string {
  if (!m) return '--'
  try {
    switch (id) {
      case 'host': return m.hostname || '--'
      case 'cpu': return formatPercent(m.cpu?.overall_percent ?? 0)
      case 'memory': return formatPercent(m.memory?.percent ?? 0)
      case 'swap': return (m.swap?.total ?? 0) > 0 ? formatPercent(m.swap?.percent ?? 0) : 'N/A'
      case 'disk': {
        const root = m.disk?.partitions?.find((p) => p.mountpoint === '/') ?? m.disk?.partitions?.[0]
        return root ? formatPercent(root.percent) : '--'
      }
      case 'network': return formatBytes(m.network?.bytes_recv ?? 0)
      case 'diskio': return '--'
      case 'docker': return dockerCount != null ? `${dockerCount} 容器` : '--'
      case 'gpu': return m.gpu ? formatPercent(m.gpu.utilization) : 'N/A'
    }
  } catch { return '--' }
}

function getCardSub(id: CardId, m: MetricsData | null): string {
  if (!m) return ''
  try {
    switch (id) {
      case 'host': return `运行 ${formatUptime(m.uptime ?? 0)}`
      case 'cpu': return `${m.cpu?.count ?? 0} 核 | 负载 ${(m.load?.['1min'] ?? 0).toFixed(1)}`
      case 'memory': return `${formatBytes(m.memory?.used ?? 0)} / ${formatBytes(m.memory?.total ?? 0)}`
      case 'swap': return (m.swap?.total ?? 0) > 0 ? `${formatBytes(m.swap?.used ?? 0)} / ${formatBytes(m.swap?.total ?? 0)}` : '未启用'
      case 'disk': {
        const root = m.disk?.partitions?.find((p) => p.mountpoint === '/') ?? m.disk?.partitions?.[0]
        return root ? `${formatBytes(root.used)} / ${formatBytes(root.total)}` : ''
      }
      case 'network': return `发 ${formatBytes(m.network?.bytes_sent ?? 0)}`
      case 'diskio': return '暂无数据'
      case 'docker': return ''
      case 'gpu': return m.gpu ? `${m.gpu.temperature}C | ${formatBytes(m.gpu.memory_used)} VRAM` : '未检测到'
    }
  } catch { return '' }
}

function getCardPercent(id: CardId, m: MetricsData | null): number {
  if (!m) return 0
  try {
    switch (id) {
      case 'cpu': return m.cpu?.overall_percent ?? 0
      case 'memory': return m.memory?.percent ?? 0
      case 'swap': return m.swap?.percent ?? 0
      case 'disk': {
        const root = m.disk?.partitions?.find((p) => p.mountpoint === '/') ?? m.disk?.partitions?.[0]
        return root?.percent ?? 0
      }
      case 'gpu': return m.gpu?.utilization ?? 0
      default: return -1
    }
  } catch { return 0 }
}

function getSparklineData(id: CardId, history: MetricsData[]): number[] {
  return history.map((m) => {
    try {
      switch (id) {
        case 'cpu': return m.cpu?.overall_percent ?? 0
        case 'memory': return m.memory?.percent ?? 0
        case 'swap': return m.swap?.percent ?? 0
        case 'disk': {
          const root = m.disk?.partitions?.find((p) => p.mountpoint === '/') ?? m.disk?.partitions?.[0]
          return root?.percent ?? 0
        }
        case 'gpu': return m.gpu?.utilization ?? 0
        case 'host': return (m.load?.['1min'] ?? 0) / (m.cpu?.count || 1) * 100
        case 'network': return Math.min(100, (m.network?.bytes_recv ?? 0) / 1e8 * 100)
        default: return 0
      }
    } catch { return 0 }
  })
}

// ---------------------------------------------------------------------------
// Alert bar
// ---------------------------------------------------------------------------
function AlertBar({ summary, connected, alerts }: { summary: AlertSummary | null; connected: boolean; alerts: AlertData[] }) {
  const hasCritical = (summary?.critical ?? 0) > 0 || alerts.some((a) => a.level === 'critical')
  const hasWarning = (summary?.warning ?? 0) > 0 || alerts.some((a) => a.level === 'warning')

  return (
    <div className={cn(
      'flex items-center justify-between px-4 py-2 rounded-lg mb-4 border text-sm',
      hasCritical ? 'bg-red/10 border-red/30 text-red' :
      hasWarning ? 'bg-yellow/10 border-yellow/30 text-yellow' :
      'bg-green/5 border-green/20 text-green',
    )}>
      <div className="flex items-center gap-3">
        {hasCritical ? (
          <span>严重告警 {summary?.critical ?? 0} | 警告 {summary?.warning ?? 0}</span>
        ) : hasWarning ? (
          <span>警告 {summary?.warning ?? 0} | 24h 告警数 {summary?.total_24h ?? 0}</span>
        ) : (
          <span>系统正常</span>
        )}
      </div>
      <div className="flex items-center gap-2 text-xs text-text3">
        <span className={cn('inline-block w-2 h-2 rounded-full', connected ? 'bg-green animate-pulse' : 'bg-red')} />
        {connected ? 'WS 已连接' : 'WS 断开'}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Stat card
// ---------------------------------------------------------------------------
function StatCard({
  config,
  value,
  sub,
  percent,
  sparkData,
  color,
  onClick,
}: {
  config: CardConfig
  value: string
  sub: string
  percent: number
  sparkData: number[]
  color: string
  onClick: () => void
}) {
  const Icon = config.icon
  const showBar = percent >= 0

  return (
    <div
      onClick={onClick}
      className="bg-card border border-border rounded-lg p-4 cursor-pointer hover:border-accent/30 transition-colors group relative overflow-hidden"
    >
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <Icon size={16} className="text-text3 group-hover:text-accent transition-colors" />
          <span className="text-xs text-text3 font-medium">{config.label}</span>
        </div>
      </div>

      <div className={cn('text-2xl font-bold tracking-tight', showBar ? statusColor(percent) : 'text-text')}>
        {value}
      </div>
      <div className="text-xs text-text3 mt-0.5 truncate">{sub}</div>

      {showBar && (
        <div className="mt-2 h-1 rounded-full bg-border overflow-hidden">
          <div
            className="h-full rounded-full transition-all duration-500"
            style={{ width: `${Math.min(percent, 100)}%`, backgroundColor: statusHex(percent) }}
          />
        </div>
      )}

      {sparkData.length > 1 && (
        <div className="mt-2 -mx-1">
          <Sparkline data={sparkData} color={color} />
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Drill-down panels
// ---------------------------------------------------------------------------
function CpuDetail({ metrics, history }: { metrics: MetricsData; history: MetricsData[] }) {
  const labels = history.map((_, i) => `${i}`)
  const overall = history.map((m) => m.cpu?.overall_percent ?? 0)
  const perCpu = metrics.cpu?.per_cpu ?? []

  const cpuSeries = perCpu.length > 0
    ? perCpu.slice(0, 8).map((_, idx) => ({
        name: `Core ${idx}`,
        data: history.map((m) => m.cpu?.per_cpu?.[idx] ?? 0),
        color: ECHARTS_COLORS[idx % ECHARTS_COLORS.length],
      }))
    : []

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <MiniStat label="总使用率" value={formatPercent(metrics.cpu?.overall_percent ?? 0)} />
        <MiniStat label="核心数" value={`${metrics.cpu?.count ?? 0}`} />
        <MiniStat label="负载 1m" value={(metrics.load?.['1min'] ?? 0).toFixed(2)} />
        <MiniStat label="负载 5m" value={(metrics.load?.['5min'] ?? 0).toFixed(2)} />
      </div>
      <div className="bg-card border border-border rounded-lg p-3">
        <DetailChart data={overall} labels={labels} color="#38bdf8" title="CPU 使用率趋势" max={100} />
      </div>
      {cpuSeries.length > 0 && (
        <div className="bg-card border border-border rounded-lg p-3">
          <MultiLineChart series={cpuSeries} labels={labels} title="每核使用率 (前8核)" />
        </div>
      )}
      <ProcessTable />
    </div>
  )
}

function MemoryDetail({ metrics, history }: { metrics: MetricsData; history: MetricsData[] }) {
  const labels = history.map((_, i) => `${i}`)
  const memData = history.map((m) => m.memory?.percent ?? 0)

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <MiniStat label="已用" value={formatBytes(metrics.memory?.used ?? 0)} />
        <MiniStat label="总量" value={formatBytes(metrics.memory?.total ?? 0)} />
        <MiniStat label="可用" value={formatBytes(metrics.memory?.available ?? 0)} />
        <MiniStat label="使用率" value={formatPercent(metrics.memory?.percent ?? 0)} />
      </div>
      <div className="bg-card border border-border rounded-lg p-3">
        <DetailChart data={memData} labels={labels} color="#4ade80" title="内存使用率趋势" max={100} />
      </div>
      <ProcessTable sort="mem" />
    </div>
  )
}

function DiskDetail({ metrics, history }: { metrics: MetricsData; history: MetricsData[] }) {
  // Try to compute disk I/O from diskio field if available
  const hasDiskIo = history.some((m) => (m as unknown as Record<string, unknown>).diskio != null)

  return (
    <div className="space-y-4">
      <div className="bg-card border border-border rounded-lg overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border text-text3 text-xs">
              <th className="text-left p-3">挂载点</th>
              <th className="text-right p-3">已用</th>
              <th className="text-right p-3">总量</th>
              <th className="text-right p-3">使用率</th>
              <th className="p-3 w-32"></th>
            </tr>
          </thead>
          <tbody>
            {(metrics.disk?.partitions ?? []).map((p) => (
              <tr key={p.mountpoint} className="border-b border-border/50 hover:bg-card-hover transition-colors">
                <td className="p-3 font-mono text-xs">{p.mountpoint}</td>
                <td className="p-3 text-right">{formatBytes(p.used)}</td>
                <td className="p-3 text-right text-text3">{formatBytes(p.total)}</td>
                <td className={cn('p-3 text-right font-medium', statusColor(p.percent))}>{formatPercent(p.percent)}</td>
                <td className="p-3">
                  <div className="h-1.5 rounded-full bg-border overflow-hidden">
                    <div className="h-full rounded-full" style={{ width: `${p.percent}%`, backgroundColor: statusHex(p.percent) }} />
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {/* Disk I/O chart when data is available */}
      {hasDiskIo && <DiskIoChart history={history} />}
    </div>
  )
}

function DiskIoChart({ history }: { history: MetricsData[] }) {
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

function NetworkDetail({ metrics, history }: { metrics: MetricsData; history: MetricsData[] }) {
  const labels = history.map((_, i) => `${i}`)
  const recvRates: number[] = []
  const sentRates: number[] = []
  for (let i = 1; i < history.length; i++) {
    const dt = new Date(history[i].timestamp).getTime() - new Date(history[i - 1].timestamp).getTime()
    const rx = Math.max(0, ((history[i].network?.bytes_recv ?? 0) - (history[i - 1].network?.bytes_recv ?? 0)) * 1000 / (dt || 1000))
    const tx = Math.max(0, ((history[i].network?.bytes_sent ?? 0) - (history[i - 1].network?.bytes_sent ?? 0)) * 1000 / (dt || 1000))
    recvRates.push(rx)
    sentRates.push(tx)
  }

  const prevMetrics = history.length >= 2 ? history[history.length - 2] : null
  const dt = prevMetrics
    ? new Date(metrics.timestamp).getTime() - new Date(prevMetrics.timestamp).getTime()
    : 1000

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <MiniStat label="接收速率" value={prevMetrics ? formatRate(metrics.network?.bytes_recv ?? 0, prevMetrics.network?.bytes_recv ?? 0, dt) : '--'} />
        <MiniStat label="发送速率" value={prevMetrics ? formatRate(metrics.network?.bytes_sent ?? 0, prevMetrics.network?.bytes_sent ?? 0, dt) : '--'} />
        <MiniStat label="总接收" value={formatBytes(metrics.network?.bytes_recv ?? 0)} />
        <MiniStat label="总发送" value={formatBytes(metrics.network?.bytes_sent ?? 0)} />
      </div>
      {recvRates.length > 1 && (
        <div className="bg-card border border-border rounded-lg p-3">
          <MultiLineChart
            series={[
              { name: '接收', data: recvRates.map((r) => Math.round(r / 1024)), color: '#38bdf8' },
              { name: '发送', data: sentRates.map((r) => Math.round(r / 1024)), color: '#4ade80' },
            ]}
            labels={labels.slice(1)}
            title="网络速率 (KB/s)"
            unit=" KB/s"
          />
        </div>
      )}
    </div>
  )
}

function GpuDetail({ metrics, history }: { metrics: MetricsData; history: MetricsData[] }) {
  const serverId = useServerStore((s) => s.selectedServerId)
  // All hooks MUST be called before any conditional return (Rules of Hooks)
  const { data: gpuData } = useQuery({
    queryKey: ['gpu-processes', serverId],
    queryFn: async () => {
      const res = await client.get('/api/monitoring/gpu', { params: { server_id: serverId } })
      const raw = ensureRecord(res.data)
      return { processes: normalizeGpuProcesses(raw.processes ?? res.data) }
    },
    refetchInterval: 10_000,
  })

  const gpu = metrics.gpu
  if (!gpu) return <p className="text-text3 text-sm">未检测到 GPU</p>

  const labels = history.map((_, i) => `${i}`)
  const utilData = history.map((m) => m.gpu?.utilization ?? 0)
  const tempData = history.map((m) => m.gpu?.temperature ?? 0)
  const gpuProcesses = normalizeGpuProcesses(gpu.processes ?? gpuData?.processes ?? [])

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <MiniStat label="型号" value={gpu.name} />
        <MiniStat label="使用率" value={formatPercent(gpu.utilization)} />
        <MiniStat label="显存" value={`${formatBytes(gpu.memory_used)} / ${formatBytes(gpu.memory_total)}`} />
        <MiniStat label="温度" value={`${gpu.temperature} C`} />
      </div>
      <div className="bg-card border border-border rounded-lg p-3">
        <MultiLineChart
          series={[
            { name: 'GPU 使用率', data: utilData, color: '#a78bfa' },
            { name: '温度', data: tempData, color: '#f87171' },
          ]}
          labels={labels}
          title="GPU 趋势"
        />
      </div>
      {/* GPU Process table */}
      {gpuProcesses.length > 0 && (
        <div className="bg-card border border-border rounded-lg overflow-hidden">
          <div className="px-3 py-2 border-b border-border text-xs font-medium text-text3">GPU 进程</div>
          <table className="w-full text-xs">
            <thead>
              <tr className="text-text3 border-b border-border/50">
                <th className="text-left p-2 pl-3">PID</th>
                <th className="text-left p-2">进程名</th>
                <th className="text-right p-2 pr-3">显存占用</th>
              </tr>
            </thead>
            <tbody>
              {gpuProcesses.map((p) => (
                <tr key={p.pid} className="border-b border-border/30 hover:bg-card-hover transition-colors">
                  <td className="p-2 pl-3 font-mono text-text3">{p.pid}</td>
                  <td className="p-2 text-text">{p.name}</td>
                  <td className="p-2 pr-3 text-right text-text2">
                    {typeof p.gpu_memory_usage === 'number' ? formatBytes(p.gpu_memory_usage) : p.gpu_memory_usage}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

function SwapDetail({ metrics, history }: { metrics: MetricsData; history: MetricsData[] }) {
  const labels = history.map((_, i) => `${i}`)
  const swapData = history.map((m) => m.swap?.percent ?? 0)

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
        <MiniStat label="已用" value={formatBytes(metrics.swap?.used ?? 0)} />
        <MiniStat label="总量" value={formatBytes(metrics.swap?.total ?? 0)} />
        <MiniStat label="使用率" value={formatPercent(metrics.swap?.percent ?? 0)} />
      </div>
      <div className="bg-card border border-border rounded-lg p-3">
        <DetailChart data={swapData} labels={labels} color="#fbbf24" title="Swap 使用率趋势" max={100} />
      </div>
    </div>
  )
}

function HostDetail({ metrics, history }: { metrics: MetricsData; history: MetricsData[] }) {
  const labels = history.map((_, i) => `${i}`)
  const loadData = history.map((m) => (m.load?.['1min'] ?? 0))
  const cpuCount = metrics.cpu?.count ?? 0

  const serverId = useServerStore((s) => s.selectedServerId)
  // Fetch additional system info (OS, kernel, CPU model) from overview endpoint
  const { data: sysInfo } = useQuery({
    queryKey: ['system-info-detail', serverId],
    queryFn: async () => {
      const res = await client.get<Record<string, unknown>>('/api/dashboard/overview', { params: { server_id: serverId } })
      return res.data
    },
    staleTime: 300_000, // Cache for 5 min since this rarely changes
  })

  const osName = (metrics.os ?? sysInfo?.os ?? sysInfo?.platform ?? '--') as string
  const kernel = (metrics.kernel ?? sysInfo?.kernel ?? '--') as string
  const cpuModel = (metrics.cpu?.model ?? sysInfo?.cpu_model ?? '--') as string

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <MiniStat label="主机名" value={metrics.hostname ?? '--'} />
        <MiniStat label="运行时间" value={formatUptime(metrics.uptime ?? 0)} />
        <MiniStat label="负载 1/5/15" value={`${(metrics.load?.['1min'] ?? 0).toFixed(1)} / ${(metrics.load?.['5min'] ?? 0).toFixed(1)} / ${(metrics.load?.['15min'] ?? 0).toFixed(1)}`} />
        <MiniStat label="CPU 核心" value={`${cpuCount}`} />
      </div>
      {/* System info row */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        <MiniStat label="操作系统" value={osName} />
        <MiniStat label="内核" value={kernel} />
        <MiniStat label="CPU 型号" value={cpuModel} />
      </div>
      <div className="bg-card border border-border rounded-lg p-3">
        <DetailChart data={loadData} labels={labels} color="#a78bfa" title="系统负载 (1min)" unit="" max={Math.max(cpuCount || 1, ...loadData) * 1.2} />
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Mini stat label
// ---------------------------------------------------------------------------
function MiniStat({ label, value }: { label: string; value: string }) {
  return (
    <div className="bg-bg2 border border-border rounded-lg px-3 py-2">
      <div className="text-[10px] text-text3 uppercase tracking-wider">{label}</div>
      <div className="text-sm font-semibold text-text mt-0.5 truncate">{value}</div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Process table
// ---------------------------------------------------------------------------
function ProcessTable({ sort = 'cpu' }: { sort?: 'cpu' | 'mem' }) {
  const queryClient = useQueryClient()
  const serverId = useServerStore((s) => s.selectedServerId)
  const sortKey = sort === 'mem' ? 'by_mem' : 'by_cpu'

  const { data: processes } = useQuery({
    queryKey: ['top-processes', sort, serverId],
    queryFn: async () => {
      const res = await client.get('/api/monitoring/top-processes', { params: { limit: 15, sort, server_id: serverId } })
      const raw = ensureRecord(res.data)
      return normalizeTopProcesses(raw[sortKey] ?? raw.by_cpu ?? raw.cpu ?? raw.memory ?? res.data)
    },
    refetchInterval: 10_000,
  })

  const killMutation = useMutation({
    mutationFn: async ({ pid, username }: { pid: number; username: string }) => {
      const res = await client.post(`/api/users/${username}/kill/${pid}`, null, { params: { server_id: serverId } })
      return res.data
    },
    onSuccess: (d: { message?: string }) => {
      toast.success(d.message ?? '进程已终止')
      queryClient.invalidateQueries({ queryKey: ['top-processes'] })
    },
    onError: () => toast.error('终止进程失败'),
  })

  if (!processes) return null

  return (
    <div className="bg-card border border-border rounded-lg overflow-hidden">
      <div className="px-3 py-2 border-b border-border text-xs font-medium text-text3">进程排行 (Top 15)</div>
      <table className="w-full text-xs">
        <thead>
          <tr className="text-text3 border-b border-border/50">
            <th className="text-left p-2 pl-3">PID</th>
            <th className="text-left p-2">名称</th>
            <th className="text-left p-2">用户</th>
            <th className="text-right p-2">CPU %</th>
            <th className="text-right p-2">内存 MB</th>
            <th className="text-left p-2">命令</th>
            <th className="text-center p-2 pr-3">操作</th>
          </tr>
        </thead>
        <tbody>
          {processes.map((p) => (
            <tr key={p.pid} className="border-b border-border/30 hover:bg-card-hover transition-colors">
              <td className="p-2 pl-3 font-mono text-text3">{p.pid}</td>
              <td className="p-2 font-medium">{p.name}</td>
              <td className="p-2 text-text3">{p.user}</td>
              <td className={cn('p-2 text-right', p.cpu_percent > 50 ? 'text-red' : p.cpu_percent > 20 ? 'text-yellow' : 'text-text')}>
                {p.cpu_percent.toFixed(1)}
              </td>
              <td className="p-2 text-right">{p.mem_rss_mb.toFixed(0)}</td>
              <td className="p-2 text-text3 truncate max-w-[200px]" title={p.cmdline}>{p.cmdline}</td>
              <td className="p-2 pr-3 text-center">
                <button
                  onClick={(e) => {
                    e.stopPropagation()
                    if (confirm(`确认终止进程 ${p.pid} (${p.name})?`)) {
                      killMutation.mutate({ pid: p.pid, username: p.user })
                    }
                  }}
                  disabled={killMutation.isPending}
                  className="inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded text-[10px] font-medium bg-red/10 text-red hover:bg-red/20 transition-colors disabled:opacity-50"
                  title={`终止进程 ${p.pid}`}
                >
                  <Skull size={10} />
                  Kill
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Recent Alerts List
// ---------------------------------------------------------------------------
function RecentAlertsList() {
  const serverId = useServerStore((s) => s.selectedServerId)
  const { data: recentAlerts } = useQuery({
    queryKey: ['recent-alerts', serverId],
    queryFn: async () => {
      const res = await client.get('/api/monitoring/alerts/recent', { params: { limit: 6, server_id: serverId } })
      return ensureArray<Record<string, unknown>>(res.data).map((item) => ({
        id: Number(item.id ?? 0),
        rule_name: typeof item.rule_name === 'string' ? item.rule_name : '告警',
        level: typeof item.level === 'string' ? item.level : typeof item.severity === 'string' ? item.severity : 'info',
        message: typeof item.message === 'string' ? item.message : '',
        created_at: normalizeTimestamp(item.created_at ?? item.timestamp),
      }))
    },
    refetchInterval: 30_000,
  })

  const alerts = recentAlerts ?? []

  if (alerts.length === 0) return null

  const levelStyles: Record<string, string> = {
    critical: 'bg-red/15 text-red',
    warning: 'bg-yellow/15 text-yellow',
    info: 'bg-accent/15 text-accent',
  }

  return (
    <div className="mt-6">
      <h3 className="text-sm font-medium text-text3 mb-3 uppercase tracking-wider flex items-center gap-2">
        <Bell size={14} />
        最近告警
      </h3>
      <div className="bg-card border border-border rounded-lg overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border text-text3 text-xs">
              <th className="text-left p-3">时间</th>
              <th className="text-left p-3">级别</th>
              <th className="text-left p-3">规则</th>
              <th className="text-left p-3">消息</th>
            </tr>
          </thead>
          <tbody>
            {alerts.map((a) => (
              <tr key={a.id} className="border-b border-border/30 hover:bg-card-hover transition-colors">
                <td className="p-3 text-text3 text-xs whitespace-nowrap">
                  {new Date(a.created_at).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })}
                </td>
                <td className="p-3">
                  <span className={cn('inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-medium', levelStyles[a.level] ?? levelStyles.info)}>
                    {a.level === 'critical' && <AlertTriangle size={10} />}
                    {a.level}
                  </span>
                </td>
                <td className="p-3 text-text2 text-xs font-medium">{a.rule_name}</td>
                <td className="p-3 text-text3 text-xs truncate max-w-[300px]" title={a.message}>{a.message}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main Dashboard
// ---------------------------------------------------------------------------
export default function DashboardPage() {
  const serverId = useServerStore((s) => s.selectedServerId)
  const { metrics, history, connected, alerts } = useWebSocket(serverId)
  const [activeCard, setActiveCard] = useState<CardId | null>(null)
  const [historyPeriod, setHistoryPeriod] = useState<HistoryPeriod>('1')

  // Fallback: fetch snapshot via API until WS delivers real-time data.
  // For remote servers, WS updates arrive every 60s, so this fills the gap.
  const { data: fallbackMetrics } = useQuery({
    queryKey: ['metrics-fallback', serverId],
    queryFn: async () => {
      const res = await client.get('/api/monitoring/realtime', { params: { server_id: serverId } })
      return normalizeMetricsSnapshot(res.data)
    },
    enabled: !metrics,
    refetchInterval: metrics ? false : 5000,
  })

  // Alert summary
  const { data: alertSummary } = useQuery({
    queryKey: ['alert-summary', serverId],
    queryFn: async () => {
      const res = await client.get<AlertSummary>('/api/monitoring/alerts/summary', { params: { server_id: serverId } })
      return res.data
    },
    refetchInterval: 30_000,
  })

  // Docker container count (also used for overview charts)
  const { data: dockerContainers } = useQuery({
    queryKey: ['docker-containers-list', serverId],
    queryFn: async () => {
      const res = await client.get('/api/docker/containers', { params: { server_id: serverId } })
      return normalizeDockerContainers(res.data)
    },
    refetchInterval: 30_000,
  })
  const dockerCount = dockerContainers?.length ?? null

  // History data for overview system trend chart
  const { data: historyData } = useQuery({
    queryKey: ['monitoring-history', historyPeriod, serverId],
    queryFn: async () => {
      const res = await client.get('/api/monitoring/history', { params: { metric: 'all', hours: Number(historyPeriod), server_id: serverId } })
      return ensureArray<Record<string, unknown>>(res.data).map((item) => {
        let rawValue = item.value
        if (typeof rawValue === 'string') {
          try {
            rawValue = JSON.parse(rawValue)
          } catch {
            rawValue = {}
          }
        }
        return {
          timestamp: normalizeTimestamp(item.timestamp),
          value: normalizeMetricsSnapshot(rawValue) ?? {},
        }
      })
    },
    refetchInterval: 60_000,
    enabled: !activeCard,
  })

  // Top processes for overview chart
  const { data: topProcessesData } = useQuery({
    queryKey: ['top-processes-overview', serverId],
    queryFn: async () => {
      const res = await client.get('/api/monitoring/top-processes', { params: { limit: 5, server_id: serverId } })
      const raw = ensureRecord(res.data)
      return normalizeTopProcesses(raw.by_cpu ?? raw.cpu ?? res.data)
    },
    refetchInterval: 15_000,
    enabled: !activeCard,
  })

  const currentMetrics = metrics ?? fallbackMetrics ?? null

  const renderDetail = useCallback(() => {
    if (!activeCard || !currentMetrics) return null

    const EB = ErrorBoundary
    const detailMap: Record<CardId, React.ReactNode> = {
      host: <EB><HostDetail metrics={currentMetrics} history={history} /></EB>,
      cpu: <EB><CpuDetail metrics={currentMetrics} history={history} /></EB>,
      memory: <EB><MemoryDetail metrics={currentMetrics} history={history} /></EB>,
      swap: <EB><SwapDetail metrics={currentMetrics} history={history} /></EB>,
      disk: <EB><DiskDetail metrics={currentMetrics} history={history} /></EB>,
      network: <EB><NetworkDetail metrics={currentMetrics} history={history} /></EB>,
      diskio: <p className="text-text3 text-sm">磁盘 I/O 数据暂未接入</p>,
      docker: <EB><DockerDetail /></EB>,
      gpu: <EB><GpuDetail metrics={currentMetrics} history={history} /></EB>,
    }

    return detailMap[activeCard] ?? null
  }, [activeCard, currentMetrics, history])

  // Loading state
  if (!currentMetrics) {
    return (
      <div className="flex flex-col items-center justify-center h-64 gap-3">
        <RefreshCw size={24} className="text-text3 animate-spin" />
        <span className="text-text3 text-sm">正在连接服务器...</span>
      </div>
    )
  }

  // Drill-down view
  if (activeCard) {
    const cardConfig = CARDS.find((c) => c.id === activeCard)!
    return (
      <div>
        <AlertBar summary={alertSummary ?? null} connected={connected} alerts={alerts} />
        <button
          onClick={() => setActiveCard(null)}
          className="flex items-center gap-1.5 text-sm text-text3 hover:text-accent mb-4 transition-colors"
        >
          <ChevronLeft size={16} />
          返回仪表盘
        </button>
        <h3 className="text-lg font-semibold mb-4 flex items-center gap-2">
          <cardConfig.icon size={20} className="text-accent" />
          {cardConfig.label} 详情
        </h3>
        {renderDetail()}
      </div>
    )
  }

  // Grid view
  return (
    <div>
      <AlertBar summary={alertSummary ?? null} connected={connected} alerts={alerts} />
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
        {CARDS.map((card) => {
          const percent = getCardPercent(card.id, currentMetrics)
          return (
            <StatCard
              key={card.id}
              config={card}
              value={getCardValue(card.id, currentMetrics, dockerCount)}
              sub={getCardSub(card.id, currentMetrics)}
              percent={percent}
              sparkData={getSparklineData(card.id, history)}
              color={percent >= 0 ? statusHex(percent) : '#38bdf8'}
              onClick={() => setActiveCard(card.id)}
            />
          )
        })}
      </div>

      {/* Overview Charts Grid */}
      <OverviewChartsGrid
        historyData={historyData ?? []}
        period={historyPeriod}
        setPeriod={setHistoryPeriod}
        alertSummary={alertSummary ?? null}
        containers={dockerContainers ?? null}
        wsHistory={history}
        metrics={currentMetrics}
        topProcesses={topProcessesData ?? null}
      />

      {/* Recent Alerts */}
      <RecentAlertsList />
    </div>
  )
}

// ---------------------------------------------------------------------------
// Docker detail (fetches its own data)
// ---------------------------------------------------------------------------
type DockerContainer = { name: string; status: string; image: string; state: string }

function DockerDetail() {
  const serverId = useServerStore((s) => s.selectedServerId)
  const { data: containers } = useQuery<DockerContainer[]>({
    queryKey: ['docker-containers-detail', serverId],
    queryFn: async (): Promise<DockerContainer[]> => {
      const res = await client.get('/api/docker/containers', { params: { server_id: serverId } })
      return normalizeDockerContainers(res.data)
    },
    refetchInterval: 15_000,
  })

  if (!containers) return <p className="text-text3 text-sm">加载中...</p>

  const running = containers.filter((c) => c.state === 'running').length
  const stopped = containers.filter((c) => c.state === 'exited' || c.state === 'dead').length
  const restarting = containers.filter((c) => c.state === 'restarting').length
  const total = containers.length

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <MiniStat label="运行中" value={`${running}`} />
        <MiniStat label="已停止" value={`${stopped}`} />
        <MiniStat label="重启中" value={`${restarting}`} />
        <MiniStat label="总数" value={`${total}`} />
      </div>
      <div className="bg-card border border-border rounded-lg overflow-hidden">
        <table className="w-full text-xs">
          <thead>
            <tr className="text-text3 border-b border-border">
              <th className="text-left p-2 pl-3">名称</th>
              <th className="text-left p-2">镜像</th>
              <th className="text-left p-2">状态</th>
              <th className="text-left p-2">详情</th>
            </tr>
          </thead>
          <tbody>
            {containers.map((c) => (
              <tr key={c.name} className="border-b border-border/30 hover:bg-card-hover transition-colors">
                <td className="p-2 pl-3 font-medium">{c.name}</td>
                <td className="p-2 text-text3 truncate max-w-[200px]" title={c.image}>{c.image}</td>
                <td className="p-2">
                  <span className={cn(
                    'inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-medium',
                    c.state === 'running' ? 'bg-green/10 text-green' :
                    c.state === 'restarting' ? 'bg-yellow/10 text-yellow' :
                    'bg-red/10 text-red',
                  )}>
                    <span className={cn(
                      'w-1.5 h-1.5 rounded-full',
                      c.state === 'running' ? 'bg-green' :
                      c.state === 'restarting' ? 'bg-yellow animate-pulse' :
                      'bg-red',
                    )} />
                    {c.state}
                  </span>
                </td>
                <td className="p-2 text-text3">{c.status}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
