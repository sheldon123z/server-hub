/**
 * Recent alerts list component - displays the latest alerts in a table.
 */

import { useQuery } from '@tanstack/react-query'
import { useServerStore } from '@/stores/serverStore'
import client from '@/api/client'
import { normalizeTimestamp } from '@/lib/monitoring'
import { ensureArray, cn } from '@/lib/utils'
import { Bell, AlertTriangle } from 'lucide-react'

export function RecentAlertsList() {
  const serverId = useServerStore((s) => s.selectedServerId)
  const { data: recentAlerts } = useQuery({
    queryKey: ['recent-alerts', serverId],
    queryFn: async () => {
      const res = await client.get('/api/monitoring/alerts/recent', { params: { limit: 6, server_id: serverId } })
      return ensureArray<Record<string, unknown>>(res.data).map((item) => ({
        id: Number(item.id ?? 0),
        rule_name: typeof item.rule_name === 'string' ? item.rule_name : '告警',
        level: typeof item.level === 'string' ? item.level : typeof item.severity === 'string' ? item.severity : 'info',
        message: typeof item.message === 'string' ? item.message : '',
        created_at: normalizeTimestamp(item.created_at ?? item.timestamp),
      }))
    },
    refetchInterval: 30_000,
  })

  const alerts = recentAlerts ?? []

  if (alerts.length === 0) return null

  const levelStyles: Record<string, string> = {
    critical: 'bg-red/15 text-red',
    warning: 'bg-yellow/15 text-yellow',
    info: 'bg-accent/15 text-accent',
  }

  return (
    <div className="mt-6">
      <h3 className="text-sm font-medium text-text3 mb-3 uppercase tracking-wider flex items-center gap-2">
        <Bell size={14} />
        最近告警
      </h3>
      <div className="bg-card border border-border rounded-lg overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border text-text3 text-xs">
              <th className="text-left p-3">时间</th>
              <th className="text-left p-3">级别</th>
              <th className="text-left p-3">规则</th>
              <th className="text-left p-3">消息</th>
            </tr>
          </thead>
          <tbody>
            {alerts.map((a) => (
              <tr key={a.id} className="border-b border-border/30 hover:bg-card-hover transition-colors">
                <td className="p-3 text-text3 text-xs whitespace-nowrap">
                  {new Date(a.created_at).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })}
                </td>
                <td className="p-3">
                  <span className={cn('inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-medium', levelStyles[a.level] ?? levelStyles.info)}>
                    {a.level === 'critical' && <AlertTriangle size={10} />}
                    {a.level}
                  </span>
                </td>
                <td className="p-3 text-text2 text-xs font-medium">{a.rule_name}</td>
                <td className="p-3 text-text3 text-xs truncate max-w-[300px]" title={a.message}>{a.message}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
