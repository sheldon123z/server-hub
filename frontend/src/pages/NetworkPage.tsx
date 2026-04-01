import { useQuery } from '@tanstack/react-query'
import client from '@/api/client'
import { cn, ensureArray, ensureRecord, toNumber, toString } from '@/lib/utils'
import { useServerStore } from '@/stores/serverStore'

/** 端口监听信息 */
interface PortInfo {
  /** 端口号 */
  port: number
  /** 协议 (tcp/udp) */
  protocol: string
  /** 监听进程名 */
  process: string
  /** 进程 PID */
  pid: number
  /** 绑定地址 */
  address: string
}

/** 代理运行状态 */
interface ProxyInfo {
  /** 代理是否运行中 */
  running: boolean
  /** 代理监听端口 */
  port?: number
  /** HTTP 代理地址 */
  http_proxy?: string
}

/** 将 API 返回的端口列表数据统一规范化 */
function normalizePorts(value: unknown): { ports: PortInfo[]; count: number } {
  const record = ensureRecord(value)
  const ports = ensureArray<Record<string, unknown>>(record.ports).map((item) => ({
    port: toNumber(item.port),
    protocol: toString(item.protocol ?? item.proto ?? item.state).toLowerCase(),
    process: toString(item.process),
    pid: toNumber(item.pid),
    address: toString(item.address ?? item.local_addr ?? item.local_address),
  }))
  return {
    ports,
    count: toNumber(record.count, ports.length),
  }
}

/** 将 API 返回的代理状态数据统一规范化 */
function normalizeProxy(value: unknown): ProxyInfo {
  const record = ensureRecord(value)
  return {
    running: Boolean(record.running ?? record.clash_running),
    port: typeof record.port === 'number' ? record.port : undefined,
    http_proxy: toString(record.http_proxy) || undefined,
  }
}

function flattenConnectionStats(data: Record<string, unknown>): Record<string, number> {
  const result: Record<string, number> = {}
  for (const [key, value] of Object.entries(data)) {
    if (typeof value === 'number') {
      result[key] = value
    } else if (typeof value === 'string') {
      const num = Number(value)
      if (!isNaN(num)) result[key] = num
    } else if (value && typeof value === 'object' && !Array.isArray(value)) {
      for (const [subKey, subVal] of Object.entries(value as Record<string, unknown>)) {
        if (typeof subVal === 'number') {
          result[subKey] = subVal
        } else if (typeof subVal === 'string') {
          const num = Number(subVal)
          if (!isNaN(num)) result[subKey] = num
        }
      }
    }
  }
  return result
}

/** 将 API 返回的连接统计数据统一规范化为扁平的 state->count 映射 */
function normalizeConnections(value: unknown): Record<string, number> {
  const record = ensureRecord(value)
  return flattenConnectionStats(record)
}

/** Color hint for TCP state labels */
function tcpStateColor(state: string): string {
  const s = state.toUpperCase()
  if (s === 'ESTABLISHED') return 'text-green'
  if (s === 'LISTEN' || s === 'LISTENING') return 'text-accent'
  if (s === 'TIME_WAIT') return 'text-yellow'
  if (s === 'CLOSE_WAIT' || s === 'CLOSING') return 'text-red'
  if (s === 'SYN_SENT' || s === 'SYN_RECV') return 'text-yellow'
  return 'text-text'
}

/**
 * 网络状态页面
 * 展示代理配置状态、TCP 连接统计 (按状态分类) 和监听端口列表
 * API 前缀: /api/network
 */
export default function NetworkPage() {
  const serverId = useServerStore((s) => s.selectedServerId)

  const { data: portsData, isLoading: portsLoading } = useQuery<{
    ports: PortInfo[]
    count: number
  }>({
    queryKey: ['network-ports', serverId],
    queryFn: () => client.get('/api/network/ports', { params: { server_id: serverId } }).then((r) => normalizePorts(r.data)),
  })

  const { data: connStats, isLoading: connLoading } = useQuery<Record<string, number>>({
    queryKey: ['network-connections', serverId],
    queryFn: () => client.get('/api/network/connections', { params: { server_id: serverId } }).then((r) => normalizeConnections(r.data)),
  })

  const { data: proxyData } = useQuery<ProxyInfo>({
    queryKey: ['network-proxy', serverId],
    queryFn: () => client.get('/api/network/proxy', { params: { server_id: serverId } }).then((r) => normalizeProxy(r.data)),
  })
  const ports = ensureArray<PortInfo>(portsData?.ports)

  return (
    <div className="space-y-6">
      <h2 className="text-lg font-semibold text-text">网络状态</h2>

      {/* 代理状态 */}
      {proxyData && (
        <div className="bg-card border border-border rounded-lg p-4">
          <h3 className="text-sm font-medium text-text2 mb-3">代理配置</h3>
          <div className="flex items-center gap-4 text-sm">
            <div className="flex items-center gap-2">
              <span className={cn(
                'inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-xs font-medium',
                proxyData.running ? 'bg-green/15 text-green' : 'bg-red/15 text-red',
              )}>
                <span className={cn('w-1.5 h-1.5 rounded-full', proxyData.running ? 'bg-green' : 'bg-red')} />
                {proxyData.running ? '运行中' : '未运行'}
              </span>
            </div>
            {proxyData.port && (
              <span className="text-text3 text-xs">端口: <span className="text-accent font-mono">{proxyData.port}</span></span>
            )}
            {proxyData.http_proxy && (
              <span className="text-text3 text-xs">地址: <span className="text-text2 font-mono">{proxyData.http_proxy}</span></span>
            )}
          </div>
        </div>
      )}

      {/* 连接统计 */}
      <div className="bg-card border border-border rounded-lg p-4">
        <h3 className="text-sm font-medium text-text2 mb-3">连接统计</h3>
        {connLoading ? (
          <p className="text-text3 text-sm">加载中...</p>
        ) : !connStats || Object.keys(connStats).length === 0 ? (
          <p className="text-text3 text-sm">暂无数据</p>
        ) : (
          <div className="grid grid-cols-3 sm:grid-cols-4 md:grid-cols-6 gap-3">
            {Object.entries(connStats)
              .sort(([, a], [, b]) => b - a)
              .map(([state, count]) => (
              <div key={state} className="bg-bg2 rounded-md px-3 py-2 text-center">
                <div className={cn('text-lg font-semibold', tcpStateColor(state))}>{count}</div>
                <div className="text-xs text-text3 mt-0.5 font-mono">{state}</div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* 监听端口 */}
      <div className="bg-card border border-border rounded-lg overflow-hidden">
        <div className="px-4 py-3 border-b border-border">
          <h3 className="text-sm font-medium text-text2">
            监听端口
            {portsData && (
              <span className="ml-2 text-text3 font-normal">({portsData.count})</span>
            )}
          </h3>
        </div>
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border text-text3 text-left">
              <th className="px-4 py-3 font-medium">端口</th>
              <th className="px-4 py-3 font-medium">协议</th>
              <th className="px-4 py-3 font-medium">进程</th>
              <th className="px-4 py-3 font-medium">PID</th>
              <th className="px-4 py-3 font-medium">绑定地址</th>
            </tr>
          </thead>
          <tbody>
            {portsLoading ? (
              <tr>
                <td colSpan={5} className="px-4 py-8 text-center text-text3">
                  加载中...
                </td>
              </tr>
            ) : ports.length === 0 ? (
              <tr>
                <td colSpan={5} className="px-4 py-8 text-center text-text3">
                  暂无数据
                </td>
              </tr>
            ) : (
              ports.map((p, i) => (
                <tr key={i} className="border-b border-border hover:bg-bg2/50">
                  <td className="px-4 py-2.5 text-accent font-mono font-medium">{p.port}</td>
                  <td className="px-4 py-2.5 text-text2 uppercase text-xs">{p.protocol}</td>
                  <td className="px-4 py-2.5 text-text">{p.process || '-'}</td>
                  <td className="px-4 py-2.5 text-text3 font-mono">{p.pid || '-'}</td>
                  <td className="px-4 py-2.5 text-text3 font-mono text-xs">{p.address}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}
