/**
 * Docker detail panel - shows container list with status indicators.
 */

import { useQuery } from '@tanstack/react-query'
import { useServerStore } from '@/stores/serverStore'
import client from '@/api/client'
import { normalizeDockerContainers } from '@/lib/monitoring'
import { cn } from '@/lib/utils'
import { MiniStat } from './cards'

type DockerContainer = { name: string; status: string; image: string; state: string }

export function DockerDetail() {
  const serverId = useServerStore((s) => s.selectedServerId)
  const { data: containers } = useQuery<DockerContainer[]>({
    queryKey: ['docker-containers-detail', serverId],
    queryFn: async (): Promise<DockerContainer[]> => {
      const res = await client.get('/api/docker/containers', { params: { server_id: serverId } })
      return normalizeDockerContainers(res.data)
    },
    refetchInterval: 15_000,
  })

  if (!containers) return <p className="text-text3 text-sm">加载中...</p>

  const running = containers.filter((c) => c.state === 'running').length
  const stopped = containers.filter((c) => c.state === 'exited' || c.state === 'dead').length
  const restarting = containers.filter((c) => c.state === 'restarting').length
  const total = containers.length

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <MiniStat label="运行中" value={`${running}`} />
        <MiniStat label="已停止" value={`${stopped}`} />
        <MiniStat label="重启中" value={`${restarting}`} />
        <MiniStat label="总数" value={`${total}`} />
      </div>
      <div className="bg-card border border-border rounded-lg overflow-hidden">
        <table className="w-full text-xs">
          <thead>
            <tr className="text-text3 border-b border-border">
              <th className="text-left p-2 pl-3">名称</th>
              <th className="text-left p-2">镜像</th>
              <th className="text-left p-2">状态</th>
              <th className="text-left p-2">详情</th>
            </tr>
          </thead>
          <tbody>
            {containers.map((c) => (
              <tr key={c.name} className="border-b border-border/30 hover:bg-card-hover transition-colors">
                <td className="p-2 pl-3 font-medium">{c.name}</td>
                <td className="p-2 text-text3 truncate max-w-[200px]" title={c.image}>{c.image}</td>
                <td className="p-2">
                  <span className={cn(
                    'inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-medium',
                    c.state === 'running' ? 'bg-green/10 text-green' :
                    c.state === 'restarting' ? 'bg-yellow/10 text-yellow' :
                    'bg-red/10 text-red',
                  )}>
                    <span className={cn(
                      'w-1.5 h-1.5 rounded-full',
                      c.state === 'running' ? 'bg-green' :
                      c.state === 'restarting' ? 'bg-yellow animate-pulse' :
                      'bg-red',
                    )} />
                    {c.state}
                  </span>
                </td>
                <td className="p-2 text-text3">{c.status}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
