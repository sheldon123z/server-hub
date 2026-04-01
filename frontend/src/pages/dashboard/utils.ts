import type { MetricsData } from '@/hooks/useWebSocket'
import { formatBytes, formatPercent } from '@/lib/utils'
import type { CardId } from './types'

export function statusColor(percent: number): string {
  if (percent < 30) return 'text-green'
  if (percent < 60) return 'text-accent'
  if (percent < 85) return 'text-yellow'
  return 'text-red'
}

export function statusHex(percent: number): string {
  if (percent < 30) return '#4ade80'
  if (percent < 60) return '#38bdf8'
  if (percent < 85) return '#fbbf24'
  return '#f87171'
}

export function formatUptime(seconds: number): string {
  const d = Math.floor(seconds / 86400)
  const h = Math.floor((seconds % 86400) / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  if (d > 0) return `${d}d ${h}h ${m}m`
  if (h > 0) return `${h}h ${m}m`
  return `${m}m`
}

export function formatRate(curr: number, prev: number, intervalMs: number): string {
  if (intervalMs <= 0) return '0 B/s'
  const rate = Math.max(0, (curr - prev) * 1000 / intervalMs)
  return formatBytes(rate) + '/s'
}

export function getCardValue(id: CardId, m: MetricsData | null, dockerCount: number | null): string {
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

export function getCardSub(id: CardId, m: MetricsData | null): string {
  if (!m) return ''
  try {
    switch (id) {
      case 'host': return `运行 ${formatUptime(m.uptime ?? 0)}`
      case 'cpu': return `${m.cpu?.count ?? 0} 核 | 负载 ${(m.load?.['1min'] ?? 0).toFixed(1)}`
      case 'memory': return `${formatBytes(m.memory?.used ?? 0)} / ${formatBytes(m.memory?.total ?? 0)}`
      case 'swap': return (m.swap?.total ?? 0) > 0 ? `${formatBytes(m.swap?.used ?? 0)} / ${formatBytes(m.swap?.total ?? 0)}` : '未启用'
      case 'disk': {
        const root = m.disk?.partitions?.find((p) => p.mountpoint === '/') ?? m.disk?.partitions?.[0]
        return root ? (root.total != null ? `${formatBytes(root.used ?? 0)} / ${formatBytes(root.total)}` : `${root.percent.toFixed(1)}%`) : ''
      }
      case 'network': return `发 ${formatBytes(m.network?.bytes_sent ?? 0)}`
      case 'diskio': return '暂无数据'
      case 'docker': return ''
      case 'gpu': return m.gpu ? `${m.gpu.temperature}C | ${formatBytes(m.gpu.memory_used)} VRAM` : '未检测到'
    }
  } catch { return '' }
}

export function getCardPercent(id: CardId, m: MetricsData | null): number {
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

export function getSparklineData(id: CardId, history: MetricsData[]): number[] {
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
