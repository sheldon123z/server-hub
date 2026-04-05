/**
 * 告警规则管理页 — CRUD + 启停开关 + 测试按钮
 */

import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Plus, Pencil, Trash2, Play, ToggleLeft, ToggleRight, AlertTriangle, ArrowLeft } from 'lucide-react'
import { Link } from 'react-router-dom'
import client from '@/api/client'
import toast from 'react-hot-toast'
import { cn } from '@/lib/utils'

interface AlertRule {
  id: string
  name: string
  enabled: boolean
  resource: string
  server_scope: string
  metric: string
  operator: string
  threshold: number | null
  duration_seconds: number
  severity: 'info' | 'warning' | 'critical'
  cooldown_seconds: number
  auto_action: string | null
  notification_channels: string | null
  created_by: string | null
  created_at: string | null
}

const SEVERITY_COLORS: Record<string, string> = {
  critical: 'text-red',
  warning: 'text-yellow',
  info: 'text-accent',
}

const BUILTIN_PREFIX = 'builtin-'

function RuleFormModal({
  rule,
  onClose,
  onSaved,
}: {
  rule: AlertRule | null
  onClose: () => void
  onSaved: () => void
}) {
  const isEdit = !!rule
  const [form, setForm] = useState<Partial<AlertRule>>(
    rule ?? {
      name: '',
      enabled: true,
      resource: 'system',
      server_scope: '*',
      metric: '',
      operator: '>',
      threshold: null,
      duration_seconds: 60,
      severity: 'warning',
      cooldown_seconds: 300,
    },
  )

  const mutation = useMutation({
    mutationFn: (data: Partial<AlertRule>) =>
      isEdit
        ? client.put(`/api/alerts/rules/${rule!.id}`, data)
        : client.post('/api/alerts/rules', data),
    onSuccess: () => {
      toast.success(isEdit ? '规则已更新' : '规则已创建')
      onSaved()
      onClose()
    },
    onError: (e: any) => toast.error(e?.response?.data?.detail ?? '保存失败'),
  })

  const set = (key: keyof AlertRule, val: unknown) =>
    setForm((f) => ({ ...f, [key]: val }))

  return (
    <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4">
      <div className="bg-card border border-border rounded-xl w-full max-w-lg p-6 space-y-4">
        <h2 className="text-lg font-semibold text-text">{isEdit ? '编辑规则' : '新建规则'}</h2>

        <div className="grid grid-cols-2 gap-3">
          <div className="col-span-2">
            <label className="block text-xs text-text3 mb-1">规则名称</label>
            <input
              className="w-full bg-bg border border-border rounded-lg px-3 py-2 text-sm text-text"
              value={form.name ?? ''}
              onChange={(e) => set('name', e.target.value)}
              placeholder="如: 磁盘使用率警告"
            />
          </div>

          <div>
            <label className="block text-xs text-text3 mb-1">资源类型</label>
            <select
              className="w-full bg-bg border border-border rounded-lg px-3 py-2 text-sm text-text"
              value={form.resource ?? 'system'}
              onChange={(e) => set('resource', e.target.value)}
            >
              {['system', 'docker', 'users', 'services', 'gpu'].map((r) => (
                <option key={r} value={r}>{r}</option>
              ))}
            </select>
          </div>

          <div>
            <label className="block text-xs text-text3 mb-1">严重度</label>
            <select
              className="w-full bg-bg border border-border rounded-lg px-3 py-2 text-sm text-text"
              value={form.severity ?? 'warning'}
              onChange={(e) => set('severity', e.target.value as AlertRule['severity'])}
            >
              {['info', 'warning', 'critical'].map((s) => (
                <option key={s} value={s}>{s}</option>
              ))}
            </select>
          </div>

          <div className="col-span-2">
            <label className="block text-xs text-text3 mb-1">指标路径</label>
            <input
              className="w-full bg-bg border border-border rounded-lg px-3 py-2 text-sm text-text font-mono"
              value={form.metric ?? ''}
              onChange={(e) => set('metric', e.target.value)}
              placeholder="如: swap.percent / disks./.percent / gpu.0.temperature"
            />
          </div>

          <div>
            <label className="block text-xs text-text3 mb-1">运算符</label>
            <select
              className="w-full bg-bg border border-border rounded-lg px-3 py-2 text-sm text-text"
              value={form.operator ?? '>'}
              onChange={(e) => set('operator', e.target.value)}
            >
              {['>', '>=', '<', '<=', '==', '!='].map((op) => (
                <option key={op} value={op}>{op}</option>
              ))}
            </select>
          </div>

          <div>
            <label className="block text-xs text-text3 mb-1">阈值</label>
            <input
              type="number"
              className="w-full bg-bg border border-border rounded-lg px-3 py-2 text-sm text-text"
              value={form.threshold ?? ''}
              onChange={(e) => set('threshold', e.target.value === '' ? null : Number(e.target.value))}
              placeholder="如: 85"
            />
          </div>

          <div>
            <label className="block text-xs text-text3 mb-1">持续时间 (秒)</label>
            <input
              type="number"
              className="w-full bg-bg border border-border rounded-lg px-3 py-2 text-sm text-text"
              value={form.duration_seconds ?? 60}
              onChange={(e) => set('duration_seconds', Number(e.target.value))}
            />
          </div>

          <div>
            <label className="block text-xs text-text3 mb-1">冷却时间 (秒)</label>
            <input
              type="number"
              className="w-full bg-bg border border-border rounded-lg px-3 py-2 text-sm text-text"
              value={form.cooldown_seconds ?? 300}
              onChange={(e) => set('cooldown_seconds', Number(e.target.value))}
            />
          </div>
        </div>

        <div className="flex justify-end gap-2 pt-2">
          <button onClick={onClose} className="px-4 py-2 text-sm text-text3 hover:text-text border border-border rounded-lg">
            取消
          </button>
          <button
            onClick={() => mutation.mutate(form)}
            disabled={mutation.isPending || !form.name || !form.metric}
            className="px-4 py-2 text-sm bg-accent hover:bg-accent/90 text-white rounded-lg disabled:opacity-50"
          >
            {mutation.isPending ? '保存中...' : '保存'}
          </button>
        </div>
      </div>
    </div>
  )
}

export default function AlertRulesPage() {
  const qc = useQueryClient()
  const [editRule, setEditRule] = useState<AlertRule | null | false>(false) // false=closed, null=new

  const { data, isFetching } = useQuery({
    queryKey: ['alert-rules'],
    queryFn: async () => {
      const res = await client.get('/api/alerts/rules')
      return res.data as { rules: AlertRule[]; count: number }
    },
  })

  const toggleMutation = useMutation({
    mutationFn: ({ id, enabled }: { id: string; enabled: boolean }) =>
      client.put(`/api/alerts/rules/${id}/toggle`, null, { params: { enabled } }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['alert-rules'] }) },
    onError: () => toast.error('操作失败'),
  })

  const deleteMutation = useMutation({
    mutationFn: (id: string) => client.delete(`/api/alerts/rules/${id}`),
    onSuccess: () => {
      toast.success('规则已删除')
      qc.invalidateQueries({ queryKey: ['alert-rules'] })
    },
    onError: (e: any) => toast.error(e?.response?.data?.detail ?? '删除失败'),
  })

  const testMutation = useMutation({
    mutationFn: (id: string) => client.post(`/api/alerts/rules/${id}/test`),
    onSuccess: (res) => {
      const d = res.data as Record<string, unknown>
      if (d.condition_met) {
        toast.error(`触发: ${d.message}`, { duration: 5000 })
      } else {
        toast.success(`未触发: ${d.message}`, { duration: 5000 })
      }
    },
    onError: (e: any) => toast.error(e?.response?.data?.detail ?? '测试失败'),
  })

  const rules = data?.rules ?? []

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Link to="/alerts" className="text-text3 hover:text-text transition-colors">
            <ArrowLeft size={18} />
          </Link>
          <AlertTriangle size={20} className="text-yellow" />
          <h1 className="text-xl font-semibold text-text">告警规则管理</h1>
          <span className="text-text3 text-sm">({rules.length} 条规则)</span>
        </div>
        <button
          onClick={() => setEditRule(null)}
          className="flex items-center gap-1.5 px-3 py-1.5 text-sm bg-accent hover:bg-accent/90 text-white rounded-lg transition-colors"
        >
          <Plus size={15} />
          新建规则
        </button>
      </div>

      {/* Rules Table */}
      <div className="bg-card border border-border rounded-lg overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border bg-bg text-text3 text-xs">
              <th className="text-left p-3 w-8">启用</th>
              <th className="text-left p-3">规则名称</th>
              <th className="text-left p-3 w-24">严重度</th>
              <th className="text-left p-3 w-32">指标路径</th>
              <th className="text-left p-3 w-40">条件</th>
              <th className="text-left p-3 w-24">持续/冷却</th>
              <th className="text-right p-3 w-28">操作</th>
            </tr>
          </thead>
          <tbody>
            {rules.length === 0 && !isFetching ? (
              <tr>
                <td colSpan={7} className="p-8 text-center text-text3 text-sm">暂无规则</td>
              </tr>
            ) : (
              rules.map((r) => (
                <tr key={r.id} className="border-b border-border/30 hover:bg-card-hover transition-colors">
                  <td className="p-3">
                    <button
                      onClick={() => toggleMutation.mutate({ id: r.id, enabled: !r.enabled })}
                      className="text-text3 hover:text-accent transition-colors"
                    >
                      {r.enabled
                        ? <ToggleRight size={20} className="text-accent" />
                        : <ToggleLeft size={20} />}
                    </button>
                  </td>
                  <td className="p-3">
                    <div className="flex items-center gap-2">
                      <span className="text-text2 font-medium">{r.name}</span>
                      {r.id.startsWith(BUILTIN_PREFIX) && (
                        <span className="text-[10px] px-1.5 py-0.5 bg-accent/10 text-accent rounded">内置</span>
                      )}
                    </div>
                    <div className="text-text3 text-xs mt-0.5">{r.resource}</div>
                  </td>
                  <td className="p-3">
                    <span className={cn('text-xs font-medium', SEVERITY_COLORS[r.severity])}>
                      {r.severity}
                    </span>
                  </td>
                  <td className="p-3 font-mono text-xs text-text3 truncate max-w-[8rem]" title={r.metric}>
                    {r.metric}
                  </td>
                  <td className="p-3 text-xs text-text3 font-mono">
                    {r.operator} {r.threshold ?? '—'}
                  </td>
                  <td className="p-3 text-xs text-text3">
                    {r.duration_seconds}s / {r.cooldown_seconds}s
                  </td>
                  <td className="p-3 text-right">
                    <div className="flex items-center justify-end gap-1">
                      <button
                        onClick={() => testMutation.mutate(r.id)}
                        disabled={testMutation.isPending}
                        title="立即测试"
                        className="p-1.5 text-text3 hover:text-accent hover:bg-accent/10 rounded transition-colors"
                      >
                        <Play size={13} />
                      </button>
                      <button
                        onClick={() => setEditRule(r)}
                        title="编辑"
                        className="p-1.5 text-text3 hover:text-text hover:bg-card-hover rounded transition-colors"
                      >
                        <Pencil size={13} />
                      </button>
                      {!r.id.startsWith(BUILTIN_PREFIX) && (
                        <button
                          onClick={() => {
                            if (confirm(`确认删除规则「${r.name}」？`)) deleteMutation.mutate(r.id)
                          }}
                          title="删除"
                          className="p-1.5 text-text3 hover:text-red hover:bg-red/10 rounded transition-colors"
                        >
                          <Trash2 size={13} />
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Modal */}
      {editRule !== false && (
        <RuleFormModal
          rule={editRule}
          onClose={() => setEditRule(false)}
          onSaved={() => qc.invalidateQueries({ queryKey: ['alert-rules'] })}
        />
      )}
    </div>
  )
}
