/**
 * Fleet Dashboard — 舰队总览页面
 *
 * 三个标签页: 概览网格 / 对比图表 / 热力图
 * API: /api/monitoring/fleet/*
 */

import { useState, useEffect, useMemo, useCallback } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate, useSearchParams } from 'react-router-dom'
import ReactECharts from 'echarts-for-react'
import * as echarts from 'echarts/core'
import client from '@/api/client'
import { useServerStore } from '@/stores/serverStore'
import { cn, formatPercent } from '@/lib/utils'

// ---------------------------------------------------------------------------
// ECharts dark theme (reuse registration from DashboardPage if loaded,
// otherwise register here idempotently)
// ---------------------------------------------------------------------------
const THEME_NAME = 'serverhub-dark'
const ECHARTS_COLORS = ['#38bdf8', '#4ade80', '#fbbf24', '#f87171', '#a78bfa', '#fb923c']

try {
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
} catch {
  // theme already registered
}

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------
/** 舰队中单台服务器的实时指标 */
interface FleetServer {
  id: string
  name: string
  status: string
  cpu_percent: number
  memory_percent: number
  disk_percent: number
  gpu_percent: number
  hostname: string
  uptime: number
}

/** 舰队总览数据：服务器列表 + 聚合统计 */
interface FleetSummary {
  servers: FleetServer[]
  aggregate: {
    total_servers: number
    online: number
    offline: number
    degraded: number
    avg_cpu: number
    avg_memory: number
    avg_disk: number
  }
}

/** 热力图数据：服务器 × 指标矩阵 */
interface HeatmapData {
  servers: { id: string; name: string }[]
  metrics: string[]
  matrix: number[][]
}

/** 多服务器对比数据：按服务器 ID 分组的时序指标 */
interface CompareData {
  server_ids: string[]
  metric: string
  hours: number
  data: Record<string, { ts: string; value: number }[]>
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------
function borderColor(percent: number): string {
  if (percent >= 85) return 'border-red/60'
  if (percent >= 60) return 'border-yellow/60'
  return 'border-green/30'
}

function statusDot(status: string) {
  const colors: Record<string, string> = {
    online: 'bg-green',
    offline: 'bg-red',
    degraded: 'bg-yellow',
    unknown: 'bg-text3',
  }
  return (
    <span
      className={cn(
        'inline-block w-2 h-2 rounded-full',
        colors[status] || 'bg-text3',
      )}
    />
  )
}

/**
 * 资源使用率进度条
 * 根据百分比自动着色：<60% 绿色, 60-85% 黄色, >=85% 红色
 */
function ProgressBar({ value, label }: { value: number; label: string }) {
  const color =
    value >= 85 ? 'bg-red' : value >= 60 ? 'bg-yellow' : 'bg-green'
  return (
    <div className="flex items-center gap-2 text-xs">
      <span className="w-10 text-text3 shrink-0">{label}</span>
      <div className="flex-1 h-1.5 bg-bg rounded-full overflow-hidden">
        <div
          className={cn('h-full rounded-full transition-all', color)}
          style={{ width: `${Math.min(value, 100)}%` }}
        />
      </div>
      <span className="w-9 text-right text-text2">{formatPercent(value)}</span>
    </div>
  )
}

const METRIC_LABELS: Record<string, string> = {
  cpu: 'CPU',
  memory: '内存',
  disk: '磁盘',
  gpu: 'GPU',
  swap: 'Swap',
  network: '网络',
}

const TABS = [
  { key: 'overview', label: '概览网格' },
  { key: 'compare', label: '对比图表' },
  { key: 'heatmap', label: '热力图' },
] as const

type TabKey = (typeof TABS)[number]['key']

// ---------------------------------------------------------------------------
// Main Component
// ---------------------------------------------------------------------------
/**
 * 舰队总览页面
 *
 * 三个标签页：
 * - 概览网格：服务器卡片（点击跳转到对应仪表盘）
 * - 对比图表：多服务器指标时间线对比
 * - 热力图：服务器 × 指标矩阵可视化
 */
/**
 * 舰队总览页面
 *
 * 三个标签页：概览网格（服务器卡片 + 聚合统计）、对比图表（多服务器时序对比）、热力图（服务器 × 指标矩阵）。
 * 标签状态通过 URL searchParams 持久化。
 */
export default function FleetDashboardPage() {
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const tab = (searchParams.get('tab') as TabKey) || 'overview'

  const setTab = useCallback(
    (key: TabKey) => {
      setSearchParams((prev) => {
        const next = new URLSearchParams(prev)
        if (key === 'overview') {
          next.delete('tab')
        } else {
          next.set('tab', key)
        }
        return next
      })
    },
    [setSearchParams],
  )

  return (
    <div className="space-y-4">
      {/* Tab bar + 批量操作入口 */}
      <div className="flex items-center justify-between border-b border-border pb-0">
        <div className="flex items-center gap-1" role="tablist">
          {TABS.map((t) => (
            <button
              key={t.key}
              role="tab"
              aria-selected={tab === t.key}
              onClick={() => setTab(t.key)}
              className={cn(
                'px-4 py-2 text-sm transition-colors border-b-2 -mb-px',
                'focus-visible:outline-2 focus-visible:outline-accent focus-visible:outline-offset-2',
                tab === t.key
                  ? 'border-accent text-accent'
                  : 'border-transparent text-text3 hover:text-text2',
              )}
            >
              {t.label}
            </button>
          ))}
        </div>
        <button
          onClick={() => navigate('/fleet/batch')}
          className="flex items-center gap-1.5 px-3 py-1.5 mb-1 text-xs bg-accent text-[#0f172a] rounded-md font-medium hover:opacity-90 transition-opacity"
        >
          <i className="ti ti-bolt" />
          批量操作
        </button>
      </div>

      {/* Tab content */}
      {tab === 'overview' && <OverviewGrid />}
      {tab === 'compare' && <CompareChart />}
      {tab === 'heatmap' && <HeatmapView />}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Tab 1: Overview Grid
// ---------------------------------------------------------------------------
/**
 * 概览网格标签页
 * 展示聚合统计卡片和服务器资源卡片网格，点击卡片跳转到对应服务器仪表盘
 */
/**
 * 概览网格标签页
 * 展示舰队聚合统计卡片和每台服务器的资源使用卡片，点击服务器卡片跳转到对应仪表盘
 */
function OverviewGrid() {
  const navigate = useNavigate()
  const setSelectedServer = useServerStore((s) => s.setSelectedServer)

  const { data, isLoading } = useQuery<FleetSummary>({
    queryKey: ['fleet-overview'],
    queryFn: async () => (await client.get('/api/monitoring/fleet/overview')).data,
    refetchInterval: 15_000,
  })

  const agg = data?.aggregate
  const servers = data?.servers ?? []

  const handleServerClick = useCallback(
    (id: string) => {
      setSelectedServer(id)
      navigate('/dashboard')
    },
    [navigate, setSelectedServer],
  )

  if (isLoading) {
    return (
      <div className="text-text3 text-sm py-12 text-center">
        加载舰队数据...
      </div>
    )
  }

  return (
    <div className="space-y-5">
      {/* Aggregate cards */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
        <AggCard label="总计" value={agg?.total_servers ?? 0} />
        <AggCard label="在线" value={agg?.online ?? 0} color="text-green" />
        <AggCard label="离线" value={agg?.offline ?? 0} color="text-red" />
        <AggCard
          label="平均 CPU"
          value={`${agg?.avg_cpu ?? 0}%`}
          color="text-accent"
        />
        <AggCard
          label="平均内存"
          value={`${agg?.avg_memory ?? 0}%`}
          color="text-accent"
        />
        <AggCard
          label="平均磁盘"
          value={`${agg?.avg_disk ?? 0}%`}
          color="text-accent"
        />
      </div>

      {/* Server card grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3">
        {servers.map((srv) => (
          <button
            key={srv.id}
            onClick={() => handleServerClick(srv.id)}
            className={cn(
              'bg-bg2 rounded-lg p-4 border-2 text-left transition-all',
              'hover:bg-[rgba(56,189,248,0.04)] hover:border-accent/40',
              borderColor(Math.max(srv.cpu_percent, srv.memory_percent)),
            )}
          >
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-2">
                {statusDot(srv.status)}
                <span className="text-sm font-medium text-text truncate max-w-[140px]">
                  {srv.name}
                </span>
              </div>
              <span className="text-[10px] text-text3 uppercase">
                {srv.status}
              </span>
            </div>
            <div className="space-y-1.5">
              <ProgressBar value={srv.cpu_percent} label="CPU" />
              <ProgressBar value={srv.memory_percent} label="MEM" />
              <ProgressBar value={srv.disk_percent} label="DISK" />
            </div>
          </button>
        ))}

        {servers.length === 0 && (
          <div className="col-span-full text-center text-text3 text-sm py-8">
            暂无服务器数据，请先在「服务器管理」中添加服务器
          </div>
        )}
      </div>
    </div>
  )
}

/**
 * 聚合统计卡片
 * 用于概览网格顶部的汇总指标展示
 */
function AggCard({
  label,
  value,
  color = 'text-text',
}: {
  label: string
  value: string | number
  /** Tailwind 文字颜色类名，如 'text-green' */
  color?: string
}) {
  return (
    <div className="bg-bg2 rounded-lg p-3 border border-border">
      <div className="text-[10px] text-text3 uppercase tracking-wider mb-1">
        {label}
      </div>
      <div className={cn('text-xl font-bold', color)}>{value}</div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Tab 2: Compare Chart
// ---------------------------------------------------------------------------
const PERIOD_OPTIONS = [
  { label: '1h', hours: 1 },
  { label: '6h', hours: 6 },
  { label: '24h', hours: 24 },
]

const COMPARE_METRICS = ['cpu', 'memory', 'disk', 'gpu', 'swap', 'network']

/**
 * 对比图表标签页
 * 左侧面板选择服务器、指标和时间范围，右侧展示多服务器指标时间线折线图
 */
/**
 * 对比图表标签页
 * 左侧面板选择服务器、指标和时间范围，右侧 ECharts 折线图对比多服务器时序数据
 */
function CompareChart() {
  const [selectedIds, setSelectedIds] = useState<string[]>([])
  const [metric, setMetric] = useState('cpu')
  const [hours, setHours] = useState(1)

  // Fetch fleet for server list
  const { data: fleetData } = useQuery<FleetSummary>({
    queryKey: ['fleet-overview'],
    queryFn: async () => (await client.get('/api/monitoring/fleet/overview')).data,
    staleTime: 30_000,
  })

  const servers = fleetData?.servers ?? []

  // Auto-select first 2 servers
  useEffect(() => {
    if (selectedIds.length === 0 && servers.length > 0) {
      setSelectedIds(servers.slice(0, Math.min(2, servers.length)).map((s) => s.id))
    }
  }, [servers, selectedIds.length])

  const queryIds = selectedIds.join(',')

  const { data: compareData, isLoading } = useQuery<CompareData>({
    queryKey: ['fleet-compare', queryIds, metric, hours],
    queryFn: async () =>
      (
        await client.get('/api/monitoring/fleet/compare', {
          params: { server_ids: queryIds, metric, hours },
        })
      ).data,
    enabled: queryIds.length > 0,
    refetchInterval: 30_000,
  })

  const toggleServer = useCallback((id: string) => {
    setSelectedIds((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id],
    )
  }, [])

  const chartOption = useMemo(() => {
    if (!compareData?.data) return {}

    const seriesArr = Object.entries(compareData.data).map(
      ([sid, points], idx) => {
        const serverName =
          servers.find((s) => s.id === sid)?.name ?? sid
        return {
          name: serverName,
          type: 'line',
          smooth: true,
          symbol: 'none',
          lineStyle: { width: 2 },
          data: points.map((p) => [p.ts, p.value]),
          color: ECHARTS_COLORS[idx % ECHARTS_COLORS.length],
        }
      },
    )

    return {
      tooltip: { trigger: 'axis' },
      legend: {
        top: 0,
        data: seriesArr.map((s) => s.name),
      },
      grid: { top: 40, right: 20, bottom: 30, left: 50 },
      xAxis: {
        type: 'time',
        axisLabel: {
          formatter: (v: string) => {
            const d = new Date(v)
            return `${d.getHours().toString().padStart(2, '0')}:${d.getMinutes().toString().padStart(2, '0')}`
          },
        },
      },
      yAxis: {
        type: 'value',
        name: metric === 'network' ? 'Bytes' : '%',
        max: metric === 'network' ? undefined : 100,
      },
      series: seriesArr,
    }
  }, [compareData, servers, metric])

  return (
    <div className="flex gap-4">
      {/* Left: server selector */}
      <div className="w-52 shrink-0 bg-bg2 rounded-lg border border-border p-3 space-y-3 max-h-[600px] overflow-y-auto">
        <div className="text-xs text-text3 uppercase tracking-wider mb-2">
          选择服务器
        </div>
        {servers.map((srv) => (
          <label
            key={srv.id}
            className="flex items-center gap-2 text-sm cursor-pointer"
          >
            <input
              type="checkbox"
              checked={selectedIds.includes(srv.id)}
              onChange={() => toggleServer(srv.id)}
              className="rounded border-border bg-bg text-accent focus:ring-accent"
            />
            <span className="flex items-center gap-1.5 text-text2">
              {statusDot(srv.status)}
              <span className="truncate max-w-[120px]">{srv.name}</span>
            </span>
          </label>
        ))}

        {/* Metric selector */}
        <div className="pt-3 border-t border-border">
          <div className="text-xs text-text3 uppercase tracking-wider mb-2">
            指标
          </div>
          <div className="flex flex-wrap gap-1">
            {COMPARE_METRICS.map((m) => (
              <button
                key={m}
                onClick={() => setMetric(m)}
                className={cn(
                  'px-2 py-1 text-xs rounded transition-colors',
                  'focus-visible:outline-2 focus-visible:outline-accent focus-visible:outline-offset-1',
                  metric === m
                    ? 'bg-accent text-white'
                    : 'bg-bg text-text3 hover:text-text2',
                )}
              >
                {METRIC_LABELS[m] || m}
              </button>
            ))}
          </div>
        </div>

        {/* Period selector */}
        <div className="pt-3 border-t border-border">
          <div className="text-xs text-text3 uppercase tracking-wider mb-2">
            时间范围
          </div>
          <div className="flex gap-1">
            {PERIOD_OPTIONS.map((p) => (
              <button
                key={p.hours}
                onClick={() => setHours(p.hours)}
                className={cn(
                  'px-2 py-1 text-xs rounded transition-colors',
                  'focus-visible:outline-2 focus-visible:outline-accent focus-visible:outline-offset-1',
                  hours === p.hours
                    ? 'bg-accent text-white'
                    : 'bg-bg text-text3 hover:text-text2',
                )}
              >
                {p.label}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Right: chart */}
      <div className="flex-1 bg-bg2 rounded-lg border border-border p-4 min-h-[400px]">
        {isLoading ? (
          <div className="flex items-center justify-center h-full text-text3 text-sm">
            加载对比数据...
          </div>
        ) : selectedIds.length === 0 ? (
          <div className="flex items-center justify-center h-full text-text3 text-sm">
            请在左侧选择至少一台服务器
          </div>
        ) : (
          <ReactECharts
            option={chartOption}
            theme={THEME_NAME}
            style={{ height: '100%', width: '100%' }}
            notMerge
          />
        )}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Tab 3: Heatmap
// ---------------------------------------------------------------------------
/**
 * 热力图标签页
 * 以服务器 × 指标的矩阵形式展示所有服务器的资源使用率，颜色从绿到红
 */
/**
 * 热力图标签页
 * 以 ECharts heatmap 展示服务器 × 指标（CPU/内存/磁盘等）的使用率矩阵
 */
function HeatmapView() {
  const { data, isLoading } = useQuery<HeatmapData>({
    queryKey: ['fleet-heatmap'],
    queryFn: async () =>
      (await client.get('/api/monitoring/fleet/heatmap')).data,
    refetchInterval: 30_000,
  })

  const chartOption = useMemo(() => {
    if (!data || data.servers.length === 0) return {}

    const serverNames = data.servers.map((s) => s.name)
    const metricLabels = data.metrics.map((m) => METRIC_LABELS[m] || m)

    // Build heatmap data: [metricIdx, serverIdx, value]
    const heatData: [number, number, number][] = []
    data.matrix.forEach((row, sIdx) => {
      row.forEach((val, mIdx) => {
        heatData.push([mIdx, sIdx, Math.round(val)])
      })
    })

    return {
      tooltip: {
        position: 'top',
        formatter: (params: { value: [number, number, number] }) => {
          const [mIdx, sIdx, val] = params.value
          return `${serverNames[sIdx]}<br/>${metricLabels[mIdx]}: ${val}%`
        },
      },
      grid: { top: 10, right: 20, bottom: 40, left: 100 },
      xAxis: {
        type: 'category',
        data: metricLabels,
        splitArea: { show: true },
        axisLabel: { color: '#94a3b8' },
      },
      yAxis: {
        type: 'category',
        data: serverNames,
        splitArea: { show: true },
        axisLabel: { color: '#94a3b8' },
      },
      visualMap: {
        min: 0,
        max: 100,
        calculable: true,
        orient: 'horizontal',
        left: 'center',
        bottom: 0,
        inRange: {
          color: ['#065f46', '#16a34a', '#facc15', '#f97316', '#dc2626'],
        },
        textStyle: { color: '#94a3b8' },
      },
      series: [
        {
          type: 'heatmap',
          data: heatData,
          label: {
            show: true,
            formatter: (p: { value: [number, number, number] }) => `${p.value[2]}%`,
            color: '#e2e8f0',
            fontSize: 11,
          },
          emphasis: {
            itemStyle: { shadowBlur: 10, shadowColor: 'rgba(0,0,0,0.5)' },
          },
        },
      ],
    }
  }, [data])

  if (isLoading) {
    return (
      <div className="text-text3 text-sm py-12 text-center">
        加载热力图数据...
      </div>
    )
  }

  if (!data || data.servers.length === 0) {
    return (
      <div className="text-text3 text-sm py-12 text-center">
        暂无服务器指标数据
      </div>
    )
  }

  return (
    <div className="bg-bg2 rounded-lg border border-border p-4">
      <ReactECharts
        option={chartOption}
        theme={THEME_NAME}
        style={{ height: Math.max(300, data.servers.length * 50 + 80), width: '100%' }}
        notMerge
      />
    </div>
  )
}
