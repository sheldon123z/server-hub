/**
 * 执行详情组件
 */

import { useQuery } from '@tanstack/react-query'
import client from '@/api/client'
import { cn } from '@/lib/utils'
import type { TeamExecution } from '@/types/team'
import { STATUS_BADGES } from './constants'

export function ExecutionDetail({ executionId }: { executionId: string }) {
  const { data, isLoading } = useQuery<TeamExecution>({
    queryKey: ['team-execution', executionId],
    queryFn: () => client.get(`/api/agents/teams/executions/${executionId}`).then((r) => {
      const raw = r.data as Record<string, unknown>
      return raw.execution as TeamExecution
    }),
  })

  if (isLoading) return <p className="text-text3 text-xs py-2">加载中...</p>
  if (!data) return null

  return (
    <div className="bg-card border border-border rounded-lg p-4 mt-4">
      <h3 className="text-sm font-medium mb-2">执行详情</h3>
      <div className="space-y-1 text-xs">
        <p><span className="text-text3">状态:</span> <span className={cn('px-1.5 py-0.5 rounded font-medium', STATUS_BADGES[data.status] ?? '')}>{data.status}</span></p>
        <p><span className="text-text3">指令:</span> <span className="text-text">{data.instruction}</span></p>
        {data.result && <p><span className="text-text3">结果:</span> <span className="text-text">{data.result}</span></p>}
        {data.error && <p><span className="text-text3">错误:</span> <span className="text-red">{data.error}</span></p>}
        <p><span className="text-text3">步数:</span> {data.total_steps ?? '-'} / <span className="text-text3">耗时:</span> {data.duration_seconds != null ? `${data.duration_seconds.toFixed(1)}s` : '-'} / <span className="text-text3">Tokens:</span> {data.total_tokens != null ? data.total_tokens.toLocaleString() : '-'}</p>
        {data.usage_json && (() => {
          try {
            const usage = JSON.parse(data.usage_json)
            const agents = usage.agents as Record<string, { input_tokens: number; output_tokens: number; total_tokens: number; tool_calls: number }> | undefined
            if (!agents || Object.keys(agents).length === 0) return null
            return (
              <div className="mt-2">
                <p className="text-text3 mb-1">Token 分布:</p>
                <div className="space-y-1">
                  {Object.entries(agents).map(([name, u]) => (
                    <div key={name} className="flex items-center gap-2">
                      <span className="text-accent w-24 truncate" title={name}>{name}</span>
                      <div className="flex-1 bg-bg2 rounded-full h-2 overflow-hidden">
                        <div className="bg-accent/60 h-full rounded-full" style={{ width: `${Math.min(100, usage.total_tokens > 0 ? (u.total_tokens / usage.total_tokens) * 100 : 0)}%` }} />
                      </div>
                      <span className="text-text2 w-20 text-right">{u.total_tokens.toLocaleString()}</span>
                    </div>
                  ))}
                </div>
              </div>
            )
          } catch { return null }
        })()}
      </div>
    </div>
  )
}
