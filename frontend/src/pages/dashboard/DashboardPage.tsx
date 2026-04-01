/**
 * Main Dashboard page - composes cards, charts, alerts, and detail panels.
 * Re-exports as the default from the dashboard directory.
 */

import { useState, useCallback } from 'react'
import { useQuery } from '@tanstack/react-query'
import { RefreshCw, ChevronLeft } from 'lucide-react'
import client from '@/api/client'
import { useWebSocket } from '@/hooks/useWebSocket'
import type { MetricsData, AlertData } from '@/hooks/useWebSocket'
import {
  normalizeDockerContainers,
  normalizeMetricsSnapshot,
  normalizeTimestamp,
  normalizeTopProcesses,
} from '@/lib/monitoring'
import { useServerStore } from '@/stores/serverStore'
import { ensureArray, ensureRecord } from '@/lib/utils'
import ErrorBoundary from '@/components/ErrorBoundary'
import { CARDS } from './constants'
import type { CardId, AlertSummary, HistoryPeriod, HistoryPoint } from './types'
import { getCardValue, getCardSub, getCardPercent, getSparklineData, statusHex } from './utils'
import { AlertBar, StatCard } from './cards'
import { OverviewChartsGrid } from './charts'
import { RecentAlertsList } from './RecentAlertsList'
import { ProcessTable } from './ProcessTable'
import { DockerDetail } from './DockerDetail'
import {
  CpuDetail,
  MemoryDetail,
  DiskDetail,
  NetworkDetail,
  GpuDetail,
  SwapDetail,
  HostDetail,
} from './details'

/**
 * 系统仪表盘主页面
 *
 * 通过 WebSocket 实时展示服务器指标（CPU/内存/磁盘/GPU/网络等），
 * 支持点击卡片展开详情面板，包含概览图表、告警列表和进程表。
 */
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
