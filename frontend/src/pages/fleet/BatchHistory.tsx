/**
 * BatchHistory — 批量操作历史列表
 * GET /api/servers/batch/history
 */
import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import client from '@/api/client'
import { cn, formatDate } from '@/lib/utils'

// ---------------------------------------------------------------------------
// 类型
// ---------------------------------------------------------------------------
interface BatchJobSummary {
  id: string
  name: string
  type: string
  status: string
  strategy: string
  server_count: number
  completed_count: number
  failed_count: number
  created_at: string
  completed_at: string | null
  duration_ms: number | null
  created_by: string
}

interface HistoryResponse {
  jobs: BatchJobSummary[]
  total: number
}

// ---------------------------------------------------------------------------
// 配置
// ---------------------------------------------------------------------------
const STATUS_CONFIG: Record<string, { color: string; label: string }> = {
  pending: { color: 'text-text3', label: '等待' },
  running: { color: 'text-accent', label: '执行中' },
  completed: { color: 'text-green', label: '已完成' },
  failed: { color: 'text-red', label: '失败' },
  cancelled: { color: 'text-text3', label: '已取消' },
}

const TYPE_LABEL: Record<string, string> = {
  command: '命令',
  service_action: '服务操作',
  docker_action: 'Docker',
  script: '脚本',
  playbook: '剧本',
}

const STRATEGY_LABEL: Record<string, string> = {
  parallel: '并行',
  serial: '串行',
  rolling: '滚动',
}

// ---------------------------------------------------------------------------
// 组件
// ---------------------------------------------------------------------------
interface BatchHistoryProps {
  onViewJob: (jobId: string) => void
}

export default function BatchHistory({ onViewJob }: BatchHistoryProps) {
  const [page, setPage] = useState(1)
  const pageSize = 20

  const { data, isLoading, isError } = useQuery<HistoryResponse>({
    queryKey: ['batch-history', page],
    queryFn: async () => {
      const res = await client.get('/api/servers/batch/history', {
        params: { page, page_size: pageSize },
      })
      return res.data as HistoryResponse
    },
    refetchInterval: 10_000,
  })

  const jobs = data?.jobs ?? []
  const total = data?.total ?? 0
  const totalPages = Math.ceil(total / pageSize)

  if (isLoading) {
    return (
      <div className="text-center text-text3 text-sm py-12">加载历史记录...</div>
    )
  }

  if (isError) {
    return (
      <div className="text-center text-red text-sm py-12">加载失败，请刷新重试</div>
    )
  }

  if (jobs.length === 0) {
    return (
      <div className="text-center text-text3 text-sm py-16">
        <i className="ti ti-history text-4xl text-text3/20 block mb-3" />
        暂无批量操作记录
      </div>
    )
  }

  return (
    <div className="space-y-3">
      {jobs.map((job) => {
        const cfg = STATUS_CONFIG[job.status] ?? STATUS_CONFIG.pending
        const successPct =
          job.server_count > 0
            ? Math.round((job.completed_count / job.server_count) * 100)
            : 0
        const durationSec =
          job.duration_ms != null ? (job.duration_ms / 1000).toFixed(1) : null

        return (
          <button
            key={job.id}
            onClick={() => onViewJob(job.id)}
            className="w-full bg-bg2 border border-border rounded-lg p-4 text-left hover:border-border-light transition-colors group"
          >
            <div className="flex items-start justify-between gap-3">
              <div className="flex-1 min-w-0">
                {/* 名称 + 类型标签 */}
                <div className="flex items-center gap-2 mb-1.5">
                  <span className="text-sm font-medium text-text truncate">
                    {job.name}
                  </span>
                  <span className="text-[10px] bg-bg text-text3 px-1.5 py-0.5 rounded shrink-0">
                    {TYPE_LABEL[job.type] ?? job.type}
                  </span>
                </div>

                {/* 元信息行 */}
                <div className="flex items-center gap-3 text-[10px] text-text3 flex-wrap">
                  <span>{formatDate(job.created_at)}</span>
                  <span>{job.server_count} 台服务器</span>
                  <span>{STRATEGY_LABEL[job.strategy] ?? job.strategy}</span>
                  {durationSec && <span>耗时 {durationSec}s</span>}
                </div>
              </div>

              {/* 状态 + 箭头 */}
              <div className="flex items-center gap-2 shrink-0">
                <div className="text-right">
                  <div className={cn('text-xs font-medium', cfg.color)}>
                    {cfg.label}
                  </div>
                  {job.status === 'completed' && job.server_count > 0 && (
                    <div className="text-[10px] text-text3">
                      {job.completed_count}/{job.server_count}
                      {job.failed_count > 0 && (
                        <span className="text-red ml-1">
                          ({job.failed_count} 失败)
                        </span>
                      )}
                    </div>
                  )}
                </div>
                <i className="ti ti-chevron-right text-text3 text-xs group-hover:text-text2 transition-colors" />
              </div>
            </div>

            {/* 进度条（非等待状态） */}
            {job.status !== 'pending' && job.server_count > 0 && (
              <div className="mt-3">
                <div className="h-1 bg-bg rounded-full overflow-hidden">
                  <div
                    className={cn(
                      'h-full rounded-full transition-all',
                      job.failed_count > 0
                        ? 'bg-gradient-to-r from-green to-red'
                        : job.status === 'completed'
                          ? 'bg-green'
                          : 'bg-accent',
                    )}
                    style={{ width: `${successPct}%` }}
                  />
                </div>
              </div>
            )}
          </button>
        )
      })}

      {/* 分页 */}
      {totalPages > 1 && (
        <div className="flex items-center justify-center gap-2 pt-2">
          <button
            onClick={() => setPage((p) => Math.max(1, p - 1))}
            disabled={page === 1}
            className="px-3 py-1.5 text-xs bg-bg2 border border-border rounded-md text-text2 disabled:opacity-40 hover:border-border-light"
          >
            上一页
          </button>
          <span className="text-xs text-text3">
            {page} / {totalPages}
          </span>
          <button
            onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
            disabled={page === totalPages}
            className="px-3 py-1.5 text-xs bg-bg2 border border-border rounded-md text-text2 disabled:opacity-40 hover:border-border-light"
          >
            下一页
          </button>
        </div>
      )}
    </div>
  )
}
