/**
 * Dashboard drill-down detail panels - one per card type.
 * Each panel shows expanded charts and tables for its metric domain.
 */

import { useQuery } from '@tanstack/react-query'
import { useServerStore } from '@/stores/serverStore'
import client from '@/api/client'
import { normalizeGpuProcesses } from '@/lib/monitoring'
import { formatBytes, formatPercent, ensureRecord } from '@/lib/utils'
import { cn } from '@/lib/utils'
import { DetailChart, MultiLineChart, DiskIoChart } from './charts'
import { ECHARTS_COLORS } from './constants'
import { MiniStat } from './cards'
import { ProcessTable } from './ProcessTable'
import { formatRate, formatUptime, statusColor, statusHex } from './utils'
import type { MetricsData } from '@/hooks/useWebSocket'

// ---------------------------------------------------------------------------
// CPU detail
// ---------------------------------------------------------------------------
export function CpuDetail({ metrics, history }: { metrics: MetricsData; history: MetricsData[] }) {
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

// ---------------------------------------------------------------------------
// Memory detail
// ---------------------------------------------------------------------------
export function MemoryDetail({ metrics, history }: { metrics: MetricsData; history: MetricsData[] }) {
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

// ---------------------------------------------------------------------------
// Disk detail
// ---------------------------------------------------------------------------
export function DiskDetail({ metrics, history }: { metrics: MetricsData; history: MetricsData[] }) {
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
                <td className="p-3 text-right">{p.used != null ? formatBytes(p.used) : '--'}</td>
                <td className="p-3 text-right text-text3">{p.total != null ? formatBytes(p.total) : '--'}</td>
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

// ---------------------------------------------------------------------------
// Network detail
// ---------------------------------------------------------------------------
export function NetworkDetail({ metrics, history }: { metrics: MetricsData; history: MetricsData[] }) {
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

// ---------------------------------------------------------------------------
// GPU detail
// ---------------------------------------------------------------------------
export function GpuDetail({ metrics, history }: { metrics: MetricsData; history: MetricsData[] }) {
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

// ---------------------------------------------------------------------------
// Swap detail
// ---------------------------------------------------------------------------
export function SwapDetail({ metrics, history }: { metrics: MetricsData; history: MetricsData[] }) {
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

// ---------------------------------------------------------------------------
// Host detail
// ---------------------------------------------------------------------------
export function HostDetail({ metrics, history }: { metrics: MetricsData; history: MetricsData[] }) {
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
