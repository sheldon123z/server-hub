/**
 * 执行历史标签页
 */

import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import client from '@/api/client'
import { cn, ensureArray, formatDate } from '@/lib/utils'
import type { TeamExecution } from '@/types/team'
import { STATUS_BADGES } from './constants'
import { normalizeExecutions } from './normalizers'
import { ExecutionDetail } from './ExecutionDetail'

export function ExecutionsTab({ teamId }: { teamId: string }) {
  const [selectedExecId, setSelectedExecId] = useState<string | null>(null)

  const { data, isLoading } = useQuery<TeamExecution[]>({
    queryKey: ['team-executions', teamId],
    queryFn: () => client.get(`/api/agents/teams/${teamId}/executions`, { params: { limit: 30 } }).then((r) => normalizeExecutions(r.data)),
    refetchInterval: 10000,
  })

  if (isLoading) return <p className="text-text3 text-sm">加载中...</p>

  const executions = ensureArray<TeamExecution>(data)

  return (
    <>
      <div className="overflow-y-auto max-h-[480px]">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border">
              <th className="text-text3 text-left text-xs uppercase py-2 sticky top-0 z-10 bg-card">时间</th>
              <th className="text-text3 text-left text-xs uppercase py-2 sticky top-0 z-10 bg-card">指令</th>
              <th className="text-text3 text-left text-xs uppercase py-2 sticky top-0 z-10 bg-card">状态</th>
              <th className="text-text3 text-left text-xs uppercase py-2 sticky top-0 z-10 bg-card">耗时</th>
              <th className="text-text3 text-left text-xs uppercase py-2 sticky top-0 z-10 bg-card">Tokens</th>
              <th className="text-text3 text-left text-xs uppercase py-2 sticky top-0 z-10 bg-card">操作</th>
            </tr>
          </thead>
          <tbody>
            {executions.map((e) => (
              <tr key={e.id} className="border-b border-border">
                <td className="py-2 text-text2 text-xs">{formatDate(e.started_at)}</td>
                <td className="py-2 text-text text-xs max-w-xs truncate" title={e.instruction}>{e.instruction.slice(0, 50)}</td>
                <td className="py-2">
                  <span className={cn('px-2 py-0.5 rounded text-xs font-medium', STATUS_BADGES[e.status] ?? 'bg-text3/20 text-text3')}>{e.status}</span>
                </td>
                <td className="py-2 text-text2 text-xs">{e.duration_seconds != null ? `${e.duration_seconds.toFixed(1)}s` : '-'}</td>
                <td className="py-2 text-text2 text-xs">{e.total_tokens != null ? e.total_tokens.toLocaleString() : '-'}</td>
                <td className="py-2">
                  <button onClick={() => setSelectedExecId(selectedExecId === e.id ? null : e.id)} className="text-accent text-xs hover:underline">详情</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {selectedExecId && <ExecutionDetail executionId={selectedExecId} />}
    </>
  )
}
