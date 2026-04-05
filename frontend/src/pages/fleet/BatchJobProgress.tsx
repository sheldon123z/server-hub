/**
 * BatchJobProgress — 批量操作实时进度面板
 * SSE 订阅 /api/servers/batch/{job_id}/stream
 * 展示总进度条、每台服务器状态行、可展开 output
 */
import { useState, useEffect, useRef, useCallback } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import client from '@/api/client'
import toast from 'react-hot-toast'
import { cn, formatDate, getErrorMessage } from '@/lib/utils'

// ---------------------------------------------------------------------------
// 类型
// ---------------------------------------------------------------------------
interface ServerResult {
  server_id: string
  status: 'pending' | 'running' | 'success' | 'failed' | 'cancelled'
  output: string | null
  error: string | null
  started_at: string | null
  completed_at: string | null
  duration_ms: number | null
}

interface OverallProgress {
  total: number
  completed: number
  failed: number
  running: number
  pending: number
}

interface BatchJobDetail {
  id: string
  name: string
  type: string
  status: string
  strategy: string
  rolling_batch_size: number
  server_ids: string // JSON array
  progress: string | null // JSON OverallProgress
  created_at: string
  completed_at: string | null
  results: ServerResult[]
}

interface Server {
  id: string
  name: string
}

interface SSEEvent {
  type: 'server_update' | 'progress' | 'completed' | 'error'
  server_id?: string
  status?: string
  output?: string
  error?: string
  overall?: OverallProgress
}

// ---------------------------------------------------------------------------
// 状态配置
// ---------------------------------------------------------------------------
const STATUS_CONFIG: Record<
  string,
  { icon: string; color: string; label: string; spin?: boolean }
> = {
  pending: { icon: 'ti-clock', color: 'text-text3', label: '等待' },
  running: { icon: 'ti-loader-2', color: 'text-accent', label: '执行中', spin: true },
  success: { icon: 'ti-circle-check', color: 'text-green', label: '成功' },
  failed: { icon: 'ti-circle-x', color: 'text-red', label: '失败' },
  cancelled: { icon: 'ti-ban', color: 'text-text3', label: '已取消' },
}

const JOB_STATUS_CONFIG: Record<string, { label: string; cls: string }> = {
  pending: { label: '等待', cls: 'bg-bg2 text-text3' },
  running: { label: '执行中', cls: 'bg-accent/20 text-accent' },
  completed: { label: '已完成', cls: 'bg-green/20 text-green' },
  failed: { label: '失败', cls: 'bg-red/20 text-red' },
  cancelled: { label: '已取消', cls: 'bg-bg2 text-text3' },
}

// ---------------------------------------------------------------------------
// 组件
// ---------------------------------------------------------------------------
interface BatchJobProgressProps {
  jobId: string
  onClose: () => void
}

export default function BatchJobProgress({ jobId, onClose }: BatchJobProgressProps) {
  const queryClient = useQueryClient()

  const [results, setResults] = useState<Record<string, ServerResult>>({})
  const [progress, setProgress] = useState<OverallProgress | null>(null)
  const [expandedIds, setExpandedIds] = useState<Set<string>>(new Set())
  const [sseConnected, setSseConnected] = useState(false)
  const [jobDone, setJobDone] = useState(false)

  const abortRef = useRef<AbortController | null>(null)

  // 服务器名称映射
  const { data: servers = [] } = useQuery<Server[]>({
    queryKey: ['servers'],
    queryFn: async () => {
      const res = await client.get('/api/servers')
      return Array.isArray(res.data) ? res.data : (res.data?.servers ?? [])
    },
    staleTime: 60_000,
  })

  const serverNameMap = Object.fromEntries(servers.map((s) => [s.id, s.name]))

  // 批量任务详情
  const { data: job } = useQuery<BatchJobDetail>({
    queryKey: ['batch-job', jobId],
    queryFn: async () => {
      const res = await client.get(`/api/servers/batch/${jobId}`)
      return res.data as BatchJobDetail
    },
    refetchInterval: jobDone ? false : 5_000,
  })

  // 初始化 results + progress
  useEffect(() => {
    if (!job) return
    const map: Record<string, ServerResult> = {}
    for (const r of job.results) {
      map[r.server_id] = r
    }
    setResults(map)
    if (job.progress) {
      try {
        setProgress(JSON.parse(job.progress) as OverallProgress)
      } catch { /* ignore */ }
    }
    if (['completed', 'failed', 'cancelled'].includes(job.status)) {
      setJobDone(true)
    }
  }, [job])

  // ---------------------------------------------------------------------------
  // SSE 连接
  // ---------------------------------------------------------------------------
  const connectSSE = useCallback(() => {
    if (jobDone) return
    abortRef.current?.abort()
    const controller = new AbortController()
    abortRef.current = controller

    void (async () => {
      try {
        const resp = await fetch(`/api/servers/batch/${jobId}/stream`, {
          credentials: 'include',
          signal: controller.signal,
        })
        if (!resp.ok || !resp.body) return

        setSseConnected(true)
        const reader = resp.body.getReader()
        const decoder = new TextDecoder()
        let buffer = ''
        let currentEvent = ''

        while (true) {
          const { done, value } = await reader.read()
          if (done) break
          buffer += decoder.decode(value, { stream: true })
          const lines = buffer.split('\n')
          buffer = lines.pop() ?? ''

          for (const line of lines) {
            const trimmed = line.trim()
            if (!trimmed) {
              currentEvent = ''
              continue
            }
            if (trimmed.startsWith('event:')) {
              currentEvent = trimmed.slice(6).trim()
              continue
            }
            if (!trimmed.startsWith('data:')) continue
            const dataStr = trimmed.slice(5).trim()
            if (!dataStr) continue
            try {
              const evt = JSON.parse(dataStr) as SSEEvent
              // 注入 type from SSE event field if missing
              if (!evt.type && currentEvent) {
                ;(evt as unknown as Record<string, unknown>).type = currentEvent
              }
              handleSSEEvent(evt)
            } catch { /* ignore */ }
          }
        }
      } catch (err) {
        if (err instanceof DOMException && err.name === 'AbortError') return
      } finally {
        setSseConnected(false)
      }
    })()
  }, [jobId, jobDone]) // eslint-disable-line react-hooks/exhaustive-deps

  function handleSSEEvent(evt: SSEEvent) {
    if (evt.type === 'server_update' && evt.server_id) {
      const sid = evt.server_id
      setResults((prev) => ({
        ...prev,
        [sid]: {
          server_id: sid,
          status: (evt.status as ServerResult['status']) ?? prev[sid]?.status ?? 'running',
          output: evt.output !== undefined ? evt.output : (prev[sid]?.output ?? null),
          error: evt.error !== undefined ? evt.error : (prev[sid]?.error ?? null),
          started_at: prev[sid]?.started_at ?? null,
          completed_at: null,
          duration_ms: null,
        },
      }))
    }
    if (evt.overall) {
      setProgress(evt.overall)
    }
    if (evt.type === 'completed') {
      setJobDone(true)
      abortRef.current?.abort()
      queryClient.invalidateQueries({ queryKey: ['batch-job', jobId] })
      queryClient.invalidateQueries({ queryKey: ['batch-history'] })
    }
  }

  useEffect(() => {
    connectSSE()
    return () => { abortRef.current?.abort() }
  }, [connectSSE])

  // ---------------------------------------------------------------------------
  // 取消任务
  // ---------------------------------------------------------------------------
  const cancelMut = useMutation({
    mutationFn: () => client.post(`/api/servers/batch/${jobId}/cancel`),
    onSuccess: () => {
      toast.success('已取消')
      setJobDone(true)
      queryClient.invalidateQueries({ queryKey: ['batch-job', jobId] })
      queryClient.invalidateQueries({ queryKey: ['batch-history'] })
    },
    onError: (err: unknown) => toast.error(getErrorMessage(err, '取消失败')),
  })

  // ---------------------------------------------------------------------------
  // 派生数据
  // ---------------------------------------------------------------------------
  const serverIds: string[] = (() => {
    if (!job?.server_ids) return []
    try { return JSON.parse(job.server_ids) as string[] } catch { return [] }
  })()

  const total = progress?.total ?? serverIds.length
  const completed = progress?.completed ?? 0
  const failed = progress?.failed ?? 0
  const pct = total > 0 ? Math.round((completed / total) * 100) : 0

  const jobStatus = job?.status ?? 'pending'
  const isActive = jobStatus === 'pending' || jobStatus === 'running'
  const jobStatusCfg = JOB_STATUS_CONFIG[jobStatus] ?? JOB_STATUS_CONFIG.pending

  const toggleExpand = (id: string) => {
    setExpandedIds((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  // ---------------------------------------------------------------------------
  // 渲染
  // ---------------------------------------------------------------------------
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
      onClick={onClose}
    >
      <div
        className="bg-bg border border-border rounded-xl shadow-2xl w-full max-w-2xl max-h-[90vh] flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        {/* ── Header ── */}
        <div className="flex items-center justify-between p-5 border-b border-border shrink-0">
          <div className="flex items-start gap-3">
            <div>
              <h2 className="text-base font-semibold text-text">
                {job?.name ?? '批量操作进度'}
              </h2>
              <div className="flex items-center gap-2 mt-1">
                <span
                  className={cn(
                    'text-[10px] px-2 py-0.5 rounded-full font-medium',
                    jobStatusCfg.cls,
                  )}
                >
                  {jobStatusCfg.label}
                </span>
                {sseConnected && isActive && (
                  <span className="flex items-center gap-1 text-[10px] text-green">
                    <span className="w-1.5 h-1.5 rounded-full bg-green animate-pulse" />
                    实时更新
                  </span>
                )}
                {job?.created_at && (
                  <span className="text-[10px] text-text3">
                    {formatDate(job.created_at)}
                  </span>
                )}
              </div>
            </div>
          </div>
          <div className="flex items-center gap-2">
            {isActive && (
              <button
                onClick={() => cancelMut.mutate()}
                disabled={cancelMut.isPending}
                className="px-3 py-1.5 text-xs bg-red/20 text-red rounded-md hover:bg-red/30 disabled:opacity-50"
              >
                {cancelMut.isPending ? '取消中...' : '取消任务'}
              </button>
            )}
            <button onClick={onClose} className="text-text3 hover:text-text p-1">
              <i className="ti ti-x text-lg" />
            </button>
          </div>
        </div>

        {/* ── 总进度 ── */}
        <div className="p-5 border-b border-border shrink-0 space-y-2">
          <div className="flex justify-between items-center text-xs">
            <span className="text-text3">总进度</span>
            <span className="text-text font-medium">
              {completed}/{total}（{pct}%）
            </span>
          </div>
          <div className="h-2 bg-bg2 rounded-full overflow-hidden">
            <div
              className={cn(
                'h-full rounded-full transition-all duration-500',
                failed > 0
                  ? 'bg-gradient-to-r from-accent to-red'
                  : jobDone
                    ? 'bg-green'
                    : 'bg-accent',
              )}
              style={{ width: `${pct}%` }}
            />
          </div>
          {progress && (
            <div className="flex gap-4 text-[11px]">
              {progress.running > 0 && (
                <span className="text-accent">
                  <i className="ti ti-loader-2 mr-1 animate-spin" />
                  {progress.running} 执行中
                </span>
              )}
              <span className="text-green">
                <i className="ti ti-circle-check mr-1" />
                {completed} 成功
              </span>
              {failed > 0 && (
                <span className="text-red">
                  <i className="ti ti-circle-x mr-1" />
                  {failed} 失败
                </span>
              )}
              {progress.pending > 0 && (
                <span className="text-text3">
                  <i className="ti ti-clock mr-1" />
                  {progress.pending} 等待
                </span>
              )}
            </div>
          )}
        </div>

        {/* ── 每台服务器状态 ── */}
        <div className="flex-1 overflow-y-auto p-5 space-y-2">
          {serverIds.length === 0 && !job && (
            <div className="text-center text-text3 text-sm py-8">加载中...</div>
          )}
          {serverIds.map((sid) => {
            const r = results[sid]
            const status = r?.status ?? 'pending'
            const cfg = STATUS_CONFIG[status] ?? STATUS_CONFIG.pending
            const expanded = expandedIds.has(sid)
            const hasOutput = !!(r?.output || r?.error)
            const serverName = serverNameMap[sid] ?? sid

            return (
              <div
                key={sid}
                className={cn(
                  'border rounded-lg overflow-hidden transition-colors',
                  status === 'success'
                    ? 'border-green/20 bg-green/5'
                    : status === 'failed'
                      ? 'border-red/20 bg-red/5'
                      : status === 'running'
                        ? 'border-accent/30 bg-accent/5'
                        : 'border-border bg-bg2',
                )}
              >
                {/* 行头 */}
                <div
                  className={cn(
                    'flex items-center gap-3 p-3',
                    hasOutput && 'cursor-pointer',
                  )}
                  onClick={() => hasOutput && toggleExpand(sid)}
                >
                  <i
                    className={cn(
                      'ti',
                      cfg.icon,
                      cfg.color,
                      'text-sm shrink-0',
                      cfg.spin && 'animate-spin',
                    )}
                  />
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="text-sm text-text truncate">{serverName}</span>
                      <span className={cn('text-[10px]', cfg.color)}>{cfg.label}</span>
                    </div>
                    {r?.duration_ms != null && (
                      <span className="text-[10px] text-text3">{r.duration_ms} ms</span>
                    )}
                  </div>
                  {hasOutput && (
                    <i
                      className={cn(
                        'ti text-text3 text-sm',
                        expanded ? 'ti-chevron-up' : 'ti-chevron-down',
                      )}
                    />
                  )}
                </div>

                {/* 展开的 output */}
                {expanded && hasOutput && (
                  <div className="px-3 pb-3 space-y-2">
                    {r?.output && (
                      <pre className="bg-bg rounded p-2 text-[11px] text-text2 font-mono overflow-x-auto max-h-48 overflow-y-auto whitespace-pre-wrap">
                        {r.output}
                      </pre>
                    )}
                    {r?.error && (
                      <pre className="bg-red/5 border border-red/20 rounded p-2 text-[11px] text-red font-mono overflow-x-auto max-h-48 overflow-y-auto whitespace-pre-wrap">
                        {r.error}
                      </pre>
                    )}
                  </div>
                )}
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}
