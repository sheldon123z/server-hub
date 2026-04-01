/**
 * Process table component - displays top processes with kill capability.
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useServerStore } from '@/stores/serverStore'
import client from '@/api/client'
import toast from 'react-hot-toast'
import { normalizeTopProcesses } from '@/lib/monitoring'
import { ensureRecord, cn } from '@/lib/utils'
import { Skull } from 'lucide-react'

export function ProcessTable({ sort = 'cpu' }: { sort?: 'cpu' | 'mem' }) {
  const queryClient = useQueryClient()
  const serverId = useServerStore((s) => s.selectedServerId)
  const sortKey = sort === 'mem' ? 'by_mem' : 'by_cpu'

  const { data: processes } = useQuery({
    queryKey: ['top-processes', sort, serverId],
    queryFn: async () => {
      const res = await client.get('/api/monitoring/top-processes', { params: { limit: 15, sort, server_id: serverId } })
      const raw = ensureRecord(res.data)
      return normalizeTopProcesses(raw[sortKey] ?? raw.by_cpu ?? raw.cpu ?? raw.memory ?? res.data)
    },
    refetchInterval: 10_000,
  })

  const killMutation = useMutation({
    mutationFn: async ({ pid, username }: { pid: number; username: string }) => {
      const res = await client.post(`/api/users/${username}/kill/${pid}`, null, { params: { server_id: serverId } })
      return res.data
    },
    onSuccess: (d: { message?: string }) => {
      toast.success(d.message ?? '进程已终止')
      queryClient.invalidateQueries({ queryKey: ['top-processes'] })
    },
    onError: () => toast.error('终止进程失败'),
  })

  if (!processes) return null

  return (
    <div className="bg-card border border-border rounded-lg overflow-hidden">
      <div className="px-3 py-2 border-b border-border text-xs font-medium text-text3">进程排行 (Top 15)</div>
      <table className="w-full text-xs">
        <thead>
          <tr className="text-text3 border-b border-border/50">
            <th className="text-left p-2 pl-3">PID</th>
            <th className="text-left p-2">名称</th>
            <th className="text-left p-2">用户</th>
            <th className="text-right p-2">CPU %</th>
            <th className="text-right p-2">内存 MB</th>
            <th className="text-left p-2">命令</th>
            <th className="text-center p-2 pr-3">操作</th>
          </tr>
        </thead>
        <tbody>
          {processes.map((p) => (
            <tr key={p.pid} className="border-b border-border/30 hover:bg-card-hover transition-colors">
              <td className="p-2 pl-3 font-mono text-text3">{p.pid}</td>
              <td className="p-2 font-medium">{p.name}</td>
              <td className="p-2 text-text3">{p.user}</td>
              <td className={cn('p-2 text-right', p.cpu_percent > 50 ? 'text-red' : p.cpu_percent > 20 ? 'text-yellow' : 'text-text')}>
                {p.cpu_percent.toFixed(1)}
              </td>
              <td className="p-2 text-right">{p.mem_rss_mb.toFixed(0)}</td>
              <td className="p-2 text-text3 truncate max-w-[200px]" title={p.cmdline}>{p.cmdline}</td>
              <td className="p-2 pr-3 text-center">
                <button
                  onClick={(e) => {
                    e.stopPropagation()
                    if (confirm(`确认终止进程 ${p.pid} (${p.name})?`)) {
                      killMutation.mutate({ pid: p.pid, username: p.user })
                    }
                  }}
                  disabled={killMutation.isPending}
                  className="inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded text-[10px] font-medium bg-red/10 text-red hover:bg-red/20 transition-colors disabled:opacity-50"
                  title={`终止进程 ${p.pid}`}
                >
                  <Skull size={10} />
                  Kill
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
