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
        <p><span className="text-text3">步数:</span> {data.total_steps ?? '-'} / <span className="text-text3">耗时:</span> {data.duration_seconds != null ? `${data.duration_seconds.toFixed(1)}s` : '-'}</p>
      </div>
    </div>
  )
}
