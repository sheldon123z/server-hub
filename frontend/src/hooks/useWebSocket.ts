/**
 * WebSocket hook for real-time server metrics.
 * Connects to /ws/metrics, auto-reconnects with exponential backoff,
 * maintains a circular buffer of last 60 data points for sparkline history.
 */

import { useCallback, useEffect, useRef, useState } from 'react'
import { normalizeAlertData, normalizeMetricsSnapshot } from '@/lib/monitoring'

export interface GpuProcess {
  pid: number
  name: string
  gpu_memory_usage: number | string
}

export interface MetricsData {
  cpu: { overall_percent: number; count: number; per_cpu?: number[]; model?: string }
  memory: { total: number; used: number; available: number; percent: number }
  swap: { total: number; used: number; percent: number }
  disk: { partitions: Array<{ mountpoint: string; total?: number; used?: number; percent: number }> }
  network: { bytes_sent: number; bytes_recv: number }
  load: { '1min': number; '5min': number; '15min': number }
  gpu?: { name: string; utilization: number; memory_used: number; memory_total: number; temperature: number; processes?: GpuProcess[] }
  uptime: number
  hostname: string
  timestamp: string
  os?: string
  kernel?: string
  platform?: string
}

export interface AlertData {
  id?: string
  level: 'critical' | 'warning' | 'info'
  title: string
  message: string
  timestamp: string
}

interface WsMessage {
  type: 'metrics' | 'metrics_full' | 'alert'
  data: MetricsData | AlertData
  server_id?: string
}

interface UseWebSocketReturn {
  metrics: MetricsData | null
  history: MetricsData[]
  connected: boolean
  alerts: AlertData[]
  subscribe: (serverIds: string[]) => void
}

const HISTORY_SIZE = 60
const RECONNECT_BASE_MS = 1000
const RECONNECT_MAX_MS = 30000

function buildWsUrl(): string {
  const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:'
  // 开发模式下直连后端 9900 端口（Vite WS proxy 对外部 IP 不稳定）
  if (import.meta.env.DEV) {
    return `${protocol}//${location.hostname}:9900/ws/metrics`
  }
  return `${protocol}//${location.host}/ws/metrics`
}

export function useWebSocket(serverFilter?: string): UseWebSocketReturn {
  const [metrics, setMetrics] = useState<MetricsData | null>(null)
  const [history, setHistory] = useState<MetricsData[]>([])
  const [connected, setConnected] = useState(false)
  const [alerts, setAlerts] = useState<AlertData[]>([])

  const wsRef = useRef<WebSocket | null>(null)
  const reconnectDelayRef = useRef(RECONNECT_BASE_MS)
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const mountedRef = useRef(true)

  // Use a ref for connect so it's always fresh and avoids circular useCallback deps
  const connectRef = useRef<() => void>(null as unknown as () => void)
  connectRef.current = () => {
    if (!mountedRef.current) return

    const ws = new WebSocket(buildWsUrl())
    wsRef.current = ws

    ws.onopen = () => {
      if (!mountedRef.current) return
      setConnected(true)
      reconnectDelayRef.current = RECONNECT_BASE_MS
      // Subscribe to selected server (or all for fleet page)
      const subscribeMsg = JSON.stringify({
        type: 'subscribe',
        server_ids: serverFilter === '*' ? ['*'] : [serverFilter ?? 'local'],
      })
      ws.send(subscribeMsg)
    }

    ws.onmessage = (event) => {
      if (!mountedRef.current) return
      try {
        const msg: WsMessage = JSON.parse(event.data)
        // Skip messages for other servers when a filter is active
        // '*' means wildcard (fleet page subscribes to all servers) — never filter
        const msgServerId = msg.server_id ?? 'local'
        if (serverFilter && serverFilter !== '*' && msgServerId !== serverFilter) {
          return
        }
        if (msg.type === 'metrics' || msg.type === 'metrics_full') {
          const data = normalizeMetricsSnapshot(msg.data)
          if (!data) return
          setMetrics(data)
          setHistory((prev) => {
            const next = [...prev, data]
            return next.length > HISTORY_SIZE ? next.slice(next.length - HISTORY_SIZE) : next
          })
        } else if (msg.type === 'alert') {
          const alert = normalizeAlertData(msg.data)
          if (!alert) return
          setAlerts((prev) => [alert, ...prev].slice(0, 50))
        }
      } catch {
        // Ignore malformed messages
      }
    }

    ws.onclose = () => {
      if (!mountedRef.current) return
      setConnected(false)
      // Schedule reconnect with exponential backoff
      const delay = reconnectDelayRef.current
      reconnectDelayRef.current = Math.min(delay * 2, RECONNECT_MAX_MS)
      reconnectTimerRef.current = setTimeout(() => {
        connectRef.current!()
      }, delay)
    }

    ws.onerror = () => {
      // onclose will fire after onerror, reconnect handled there
      ws.close()
    }
  }

  // Imperatively send a subscribe message to the backend
  const subscribe = useCallback((serverIds: string[]) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: 'subscribe', server_ids: serverIds }))
    }
  }, [])

  // Initial connection
  useEffect(() => {
    mountedRef.current = true
    connectRef.current!()

    return () => {
      mountedRef.current = false
      if (reconnectTimerRef.current) {
        clearTimeout(reconnectTimerRef.current)
      }
      if (wsRef.current) {
        wsRef.current.onclose = null
        wsRef.current.close()
      }
    }
  }, []) // Empty deps - connect logic is in refs

  // Re-subscribe when serverFilter changes — clear stale data + push new subscription
  useEffect(() => {
    // Clear old server's data immediately so UI doesn't show stale metrics
    setMetrics(null)
    setHistory([])
    if (!connected) return
    const ids = serverFilter === '*' ? ['*'] : [serverFilter ?? 'local']
    subscribe(ids)
  }, [serverFilter, connected, subscribe])

  return { metrics, history, connected, alerts, subscribe }
}
