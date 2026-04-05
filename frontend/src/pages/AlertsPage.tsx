/**
 * 告警管理页 — 活跃告警列表 + 历史记录 + 严重度筛选 + 确认按钮
 */

import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Bell, CheckCircle, AlertTriangle, Info, RefreshCw } from 'lucide-react'
import client from '@/api/client'
import toast from 'react-hot-toast'
import { cn, formatDate } from '@/lib/utils'

interface AlertHistory {
  id: number
  rule_id: string | null
  rule_name: string | null
  server_id: string
  status: string
  value: number | null
  message: string | null
  severity: string
  fired_at: string
  resolved_at: string | null
  acknowledged_by: string | null
  acknowledged_at: string | null
}

const SEVERITY_STYLES: Record<string, { badge: string; icon: React.ReactNode }> = {
  critical: { badge: 'bg-red/15 text-red border border-red/30', icon: <AlertTriangle size={12} /> },
  warning: { badge: 'bg-yellow/15 text-yellow border border-yellow/30', icon: <AlertTriangle size={12} /> },
  info: { badge: 'bg-accent/15 text-accent border border-accent/30', icon: <Info size={12} /> },
}

const STATUS_STYLES: Record<string, string> = {
  firing: 'bg-red/15 text-red',
  resolved: 'bg-green/15 text-green',
}

function SeverityBadge({ severity }: { severity: string }) {
  const s = SEVERITY_STYLES[severity] ?? SEVERITY_STYLES.info
  return (
    <span className={cn('inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-medium', s.badge)}>
      {s.icon}
      {severity}
    </span>
  )
}

function StatusBadge({ status }: { status: string }) {
  return (
    <span className={cn('px-2 py-0.5 rounded text-[11px] font-medium', STATUS_STYLES[status] ?? 'bg-text3/10 text-text3')}>
      {status === 'firing' ? '触发中' : status === 'resolved' ? '已恢复' : status}
    </span>
  )
}

type TabKey = 'active' | 'history'

export default function AlertsPage() {
  const [tab, setTab] = useState<TabKey>('active')
  const [severity, setSeverity] = useState<string>('')
  const qc = useQueryClient()

  const { data: activeData, isFetching: activeFetching, refetch: refetchActive } = useQuery({
    queryKey: ['alerts-active'],
    queryFn: async () => {
      const res = await client.get('/api/alerts/active', { params: { limit: 100 } })
      return res.data as { alerts: AlertHistory[]; count: number }
    },
    refetchInterval: 30_000,
  })

  const { data: historyData, isFetching: histFetching, refetch: refetchHistory } = useQuery({
    queryKey: ['alerts-history', severity],
    queryFn: async () => {
      const res = await client.get('/api/alerts/history', {
        params: { limit: 100, ...(severity ? { severity } : {}) },
      })
      return res.data as { items: AlertHistory[]; total: number }
    },
    enabled: tab === 'history',
  })

  const ackMutation = useMutation({
    mutationFn: (id: number) => client.put(`/api/alerts/${id}/acknowledge`),
    onSuccess: () => {
      toast.success('告警已确认')
      qc.invalidateQueries({ queryKey: ['alerts-active'] })
    },
    onError: () => toast.error('确认失败'),
  })

  const activeAlerts = activeData?.alerts ?? []
  const historyItems = historyData?.items ?? []

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Bell size={20} className="text-accent" />
          <h1 className="text-xl font-semibold text-text">告警管理</h1>
          {activeAlerts.length > 0 && (
            <span className="px-2 py-0.5 rounded-full bg-red/20 text-red text-xs font-bold">
              {activeAlerts.length} 活跃
            </span>
          )}
        </div>
        <button
          onClick={() => { refetchActive(); refetchHistory() }}
          className="flex items-center gap-1.5 px-3 py-1.5 text-sm text-text3 hover:text-text border border-border rounded-lg transition-colors"
        >
          <RefreshCw size={14} className={activeFetching || histFetching ? 'animate-spin' : ''} />
          刷新
        </button>
      </div>

      {/* Tab Bar */}
      <div className="flex gap-1 border-b border-border">
        {([['active', '活跃告警'], ['history', '历史记录']] as [TabKey, string][]).map(([key, label]) => (
          <button
            key={key}
            onClick={() => setTab(key)}
            className={cn(
              'px-4 py-2 text-sm font-medium border-b-2 -mb-px transition-colors',
              tab === key
                ? 'border-accent text-accent'
                : 'border-transparent text-text3 hover:text-text',
            )}
          >
            {label}
          </button>
        ))}
      </div>

      {/* Active Alerts */}
      {tab === 'active' && (
        <div>
          {activeAlerts.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-16 text-text3">
              <CheckCircle size={48} className="text-green mb-3 opacity-50" />
              <p className="text-sm">当前无活跃告警</p>
            </div>
          ) : (
            <div className="bg-card border border-border rounded-lg overflow-hidden">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border bg-bg text-text3 text-xs">
                    <th className="text-left p-3 w-36">触发时间</th>
                    <th className="text-left p-3 w-24">严重度</th>
                    <th className="text-left p-3">规则</th>
                    <th className="text-left p-3">消息</th>
                    <th className="text-left p-3 w-20">服务器</th>
                    <th className="text-left p-3 w-24">确认人</th>
                    <th className="text-right p-3 w-20">操作</th>
                  </tr>
                </thead>
                <tbody>
                  {activeAlerts.map((a) => (
                    <tr key={a.id} className="border-b border-border/30 hover:bg-card-hover transition-colors">
                      <td className="p-3 text-text3 text-xs whitespace-nowrap">
                        {formatDate(a.fired_at)}
                      </td>
                      <td className="p-3"><SeverityBadge severity={a.severity ?? 'info'} /></td>
                      <td className="p-3 text-text2 font-medium text-xs">{a.rule_name ?? a.rule_id ?? '—'}</td>
                      <td className="p-3 text-text3 text-xs truncate max-w-xs" title={a.message ?? ''}>
                        {a.message ?? '—'}
                      </td>
                      <td className="p-3 text-text3 text-xs">{a.server_id}</td>
                      <td className="p-3 text-text3 text-xs">
                        {a.acknowledged_by ?? <span className="text-text3/40">未确认</span>}
                      </td>
                      <td className="p-3 text-right">
                        {!a.acknowledged_by && (
                          <button
                            onClick={() => ackMutation.mutate(a.id)}
                            disabled={ackMutation.isPending}
                            className="px-2 py-1 text-xs bg-accent/10 hover:bg-accent/20 text-accent rounded transition-colors"
                          >
                            确认
                          </button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* History */}
      {tab === 'history' && (
        <div className="space-y-3">
          {/* Filters */}
          <div className="flex gap-2">
            {['', 'critical', 'warning', 'info'].map((s) => (
              <button
                key={s || 'all'}
                onClick={() => setSeverity(s)}
                className={cn(
                  'px-3 py-1 text-xs rounded-full border transition-colors',
                  severity === s
                    ? 'bg-accent text-white border-accent'
                    : 'border-border text-text3 hover:border-accent hover:text-accent',
                )}
              >
                {s || '全部'}
              </button>
            ))}
          </div>

          <div className="bg-card border border-border rounded-lg overflow-hidden">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border bg-bg text-text3 text-xs">
                  <th className="text-left p-3 w-36">触发时间</th>
                  <th className="text-left p-3 w-24">严重度</th>
                  <th className="text-left p-3 w-20">状态</th>
                  <th className="text-left p-3">规则</th>
                  <th className="text-left p-3">消息</th>
                  <th className="text-left p-3 w-36">恢复时间</th>
                </tr>
              </thead>
              <tbody>
                {historyItems.length === 0 ? (
                  <tr>
                    <td colSpan={6} className="p-8 text-center text-text3 text-sm">暂无历史记录</td>
                  </tr>
                ) : (
                  historyItems.map((a) => (
                    <tr key={a.id} className="border-b border-border/30 hover:bg-card-hover transition-colors">
                      <td className="p-3 text-text3 text-xs whitespace-nowrap">{formatDate(a.fired_at)}</td>
                      <td className="p-3"><SeverityBadge severity={a.severity ?? 'info'} /></td>
                      <td className="p-3"><StatusBadge status={a.status} /></td>
                      <td className="p-3 text-text2 font-medium text-xs">{a.rule_name ?? a.rule_id ?? '—'}</td>
                      <td className="p-3 text-text3 text-xs truncate max-w-xs">{a.message ?? '—'}</td>
                      <td className="p-3 text-text3 text-xs whitespace-nowrap">
                        {a.resolved_at ? formatDate(a.resolved_at) : '—'}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
          {historyData && <p className="text-xs text-text3">共 {historyData.total} 条记录</p>}
        </div>
      )}
    </div>
  )
}
