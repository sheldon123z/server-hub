/**
 * PatrolPanel - 5-view patrol management panel.
 * Sub-views: tasks | alerts | templates | reports | cases
 */

import { useState, useEffect, useRef } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import client from '@/api/client'
import toast from 'react-hot-toast'
import { cn, ensureArray, formatDate } from '@/lib/utils'
import { renderMarkdown } from '@/lib/markdown'

/** Compute "N分钟后运行" text from a next_run ISO timestamp. */
function nextRunText(nextRun: string | null): string {
  if (!nextRun) return ''
  const diff = new Date(nextRun).getTime() - Date.now()
  if (diff <= 0) return '即将运行'
  const minutes = Math.ceil(diff / 60_000)
  if (minutes < 60) return `${minutes}分钟后运行`
  const hours = Math.floor(minutes / 60)
  const mins = minutes % 60
  if (hours < 24) return mins > 0 ? `${hours}小时${mins}分后运行` : `${hours}小时后运行`
  const days = Math.floor(hours / 24)
  return `${days}天后运行`
}

type PatrolView = 'tasks' | 'alerts' | 'templates' | 'reports' | 'cases' | 'admin'

export function PatrolPanel() {
  const [view, setView] = useState<PatrolView>('tasks')

  const views: { key: PatrolView; label: string }[] = [
    { key: 'tasks', label: '巡检' },
    { key: 'alerts', label: '告警' },
    { key: 'templates', label: '模板' },
    { key: 'reports', label: '报告' },
    { key: 'cases', label: '案例' },
    { key: 'admin', label: '提示词' },
  ]

  return (
    <div className="flex flex-col h-full">
      {/* View tabs */}
      <div className="flex items-center gap-1 px-3 py-2 border-b border-border bg-bg2 shrink-0">
        {views.map((v) => (
          <button
            key={v.key}
            className={cn(
              'px-2.5 py-1 text-xs rounded transition-colors',
              view === v.key
                ? 'bg-accent-dim text-accent'
                : 'text-text3 hover:text-text hover:bg-card',
            )}
            onClick={() => setView(v.key)}
          >
            {v.label}
          </button>
        ))}
      </div>

      {/* View content */}
      <div className="flex-1 min-h-0 overflow-hidden">
        {view === 'tasks' && <TasksView />}
        {view === 'alerts' && <AlertsView />}
        {view === 'templates' && <TemplatesView />}
        {view === 'reports' && <ReportsView />}
        {view === 'cases' && <CasesView />}
        {view === 'admin' && <PatrolAdminView />}
      </div>
    </div>
  )
}

/* ── Tasks View ────────────────────────────────────── */

interface PatrolTask {
  id: string
  display_name: string
  description: string
  enabled: boolean
  interval_minutes: number
  last_run: string | null
  last_status: string | null
  last_report: string | null
  next_run: string | null
  prompt: string
  check_tools: string
}

function TasksView() {
  const qc = useQueryClient()
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [editInterval, setEditInterval] = useState<number | null>(null)

  const { data: tasks = [] } = useQuery({
    queryKey: ['patrols'],
    queryFn: () => client.get('/api/agents/patrols').then((r) => ensureArray<PatrolTask>(r.data)),
  })

  const selected = tasks.find((t) => t.id === selectedId) ?? null

  // Sync editInterval when selection changes — use useEffect, NOT setState during render
  const prevSelectedIdRef = useRef<string | null>(null)
  useEffect(() => {
    if (selected && prevSelectedIdRef.current !== selected.id) {
      prevSelectedIdRef.current = selected.id
      setEditInterval(selected.interval_minutes)
    }
  }, [selected])

  const toggleMut = useMutation({
    mutationFn: (task: PatrolTask) =>
      client.put(`/api/agents/patrols/${task.id}`, { enabled: !task.enabled }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['patrols'] })
      toast.success('已更新')
    },
  })

  const runMut = useMutation({
    mutationFn: (id: string) => client.post(`/api/agents/patrols/${id}/run`),
    onSuccess: () => toast.success('巡检已触发'),
  })

  const intervalMut = useMutation({
    mutationFn: ({ id, minutes }: { id: string; minutes: number }) =>
      client.put(`/api/agents/patrols/${id}`, { interval_minutes: minutes }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['patrols'] })
      toast.success('间隔已更新')
    },
  })

  const handleSaveInterval = () => {
    if (!selected || !editInterval || editInterval < 1) {
      toast.error('间隔至少 1 分钟')
      return
    }
    intervalMut.mutate({ id: selected.id, minutes: editInterval })
  }

  return (
    <div className="flex h-full">
      {/* Left list */}
      <div className="w-[200px] border-r border-border overflow-y-auto shrink-0">
        {tasks.map((t) => (
          <button
            key={t.id}
            className={cn(
              'w-full text-left px-3 py-2.5 border-b border-border text-xs transition-colors',
              selectedId === t.id ? 'bg-card' : 'hover:bg-bg2',
            )}
            onClick={() => {
              setSelectedId(t.id)
              setEditInterval(t.interval_minutes)
            }}
          >
            <div className="flex items-center gap-2">
              <span className={cn('w-1.5 h-1.5 rounded-full shrink-0', t.enabled ? 'bg-green' : 'bg-text3')} />
              <span className="text-text truncate font-medium">{t.display_name}</span>
            </div>
            <div className="text-text3 mt-0.5 truncate">{t.description}</div>
          </button>
        ))}
        {tasks.length === 0 && (
          <div className="text-text3 text-xs p-3 text-center">暂无巡检任务</div>
        )}
      </div>

      {/* Right detail */}
      <div className="flex-1 overflow-y-auto p-4">
        {selected ? (
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-medium text-text">{selected.display_name}</h3>
              <div className="flex items-center gap-2">
                <button
                  className="px-2 py-1 text-xs rounded bg-accent-dim text-accent hover:opacity-80"
                  onClick={() => runMut.mutate(selected.id)}
                  disabled={runMut.isPending}
                >
                  立即执行
                </button>
                <button
                  className={cn(
                    'px-2 py-1 text-xs rounded',
                    selected.enabled
                      ? 'bg-red/10 text-red hover:bg-red/20'
                      : 'bg-green/10 text-green hover:bg-green/20',
                  )}
                  onClick={() => toggleMut.mutate(selected)}
                >
                  {selected.enabled ? '禁用' : '启用'}
                </button>
              </div>
            </div>
            <p className="text-xs text-text2">{selected.description}</p>
            {/* Inline interval editor */}
            <div className="flex items-center gap-2 text-xs text-text3 flex-wrap">
              <label className="flex items-center gap-1">
                间隔
                <input
                  type="number"
                  min={1}
                  max={10080}
                  className="w-14 bg-bg border border-border rounded px-1.5 py-0.5 text-text text-center text-xs focus:border-accent focus:outline-none"
                  value={editInterval ?? selected.interval_minutes}
                  onChange={(e) => setEditInterval(Number(e.target.value))}
                />
                分钟
              </label>
              {editInterval !== null && editInterval !== selected.interval_minutes && (
                <button
                  className="px-2 py-0.5 text-[10px] rounded bg-accent-dim text-accent hover:opacity-80"
                  onClick={handleSaveInterval}
                  disabled={intervalMut.isPending}
                >
                  保存
                </button>
              )}
              {selected.last_run && (
                <span>上次: {formatDate(selected.last_run)}</span>
              )}
              {selected.enabled ? (
                <span className="text-accent" title={selected.next_run ? formatDate(selected.next_run) : ''}>
                  {selected.next_run ? nextRunText(selected.next_run) : ''}
                </span>
              ) : (
                <span className="text-yellow">已禁用</span>
              )}
            </div>
            <div className="grid grid-cols-2 gap-3 text-xs">
              <InfoItem label="状态" value={selected.enabled ? '已启用' : '已禁用'} />
              <InfoItem label="上次结果" value={selected.last_status ?? '-'} />
            </div>
            {selected.check_tools && (
              <div>
                <label className="text-xs text-text3 block mb-1">关联工具/脚本</label>
                <div className="flex items-center gap-1.5 flex-wrap">
                  {selected.check_tools.split(',').filter(Boolean).map((t) => (
                    <span key={t.trim()} className="px-1.5 py-0.5 rounded bg-accent-dim text-accent text-[10px]">
                      {t.trim()}
                    </span>
                  ))}
                </div>
              </div>
            )}
            <div>
              <label className="text-xs text-text3 block mb-1">提示词</label>
              <pre className="text-xs text-text2 bg-bg rounded p-2 whitespace-pre-wrap max-h-40 overflow-y-auto">
                {selected.prompt}
              </pre>
            </div>
            {selected.last_report && (
              <div>
                <label className="text-xs text-text3 block mb-1">最近报告</label>
                <div
                  className="text-xs text-text2 bg-bg rounded p-3 max-h-60 overflow-y-auto markdown-body"
                  dangerouslySetInnerHTML={{ __html: renderMarkdown(selected.last_report) }}
                />
              </div>
            )}
          </div>
        ) : (
          <div className="text-text3 text-xs text-center pt-10">选择巡检任务查看详情</div>
        )}
      </div>
    </div>
  )
}

/* ── Alerts View ───────────────────────────────────── */

interface AlertRule {
  id: string
  name: string
  metric: string
  operator: string
  warning_threshold: number | null
  critical_threshold: number | null
  cooldown_minutes: number
  notify: boolean
  severity: string
  enabled: boolean
}

interface AlertHistory {
  id: string
  rule_name: string
  severity: string
  message: string
  created_at: string
  resolved: boolean
}

function AlertsView() {
  const qc = useQueryClient()
  const [selectedId, setSelectedId] = useState<string | null>(null)
  // Local editable copies of rule fields
  const [editFields, setEditFields] = useState<Record<string, Partial<AlertRule>>>({})

  const { data: rules = [] } = useQuery({
    queryKey: ['alert-rules'],
    queryFn: () => client.get('/api/agents/alerts/rules').then((r) => ensureArray<AlertRule>(r.data)),
  })

  const { data: history = [] } = useQuery({
    queryKey: ['alert-history'],
    queryFn: () => client.get('/api/agents/alerts/history').then((r) => ensureArray<AlertHistory>(r.data)),
  })

  const selectedRule = rules.find((r) => r.id === selectedId) ?? null
  const filteredHistory = selectedId
    ? history.filter((h) => h.rule_name === selectedRule?.name)
    : history

  // Get editable value for a rule field
  const getField = <K extends keyof AlertRule>(rule: AlertRule, field: K): AlertRule[K] => {
    const edit = editFields[rule.id]
    if (edit && field in edit) return edit[field] as AlertRule[K]
    return rule[field]
  }

  const setField = (ruleId: string, field: string, value: unknown) => {
    setEditFields((prev) => ({
      ...prev,
      [ruleId]: { ...prev[ruleId], [field]: value },
    }))
  }

  const saveMut = useMutation({
    mutationFn: ({ rule }: { rule: AlertRule }) => {
      const edit = editFields[rule.id] ?? {}
      return client.put(`/api/agents/alerts/rules/${rule.id}`, {
        warning_threshold: edit.warning_threshold ?? rule.warning_threshold,
        critical_threshold: edit.critical_threshold ?? rule.critical_threshold,
        cooldown_minutes: edit.cooldown_minutes ?? rule.cooldown_minutes,
        notify: edit.notify ?? rule.notify,
        enabled: edit.enabled ?? rule.enabled,
      })
    },
    onSuccess: (_data, { rule }) => {
      qc.invalidateQueries({ queryKey: ['alert-rules'] })
      setEditFields((prev) => {
        const next = { ...prev }
        delete next[rule.id]
        return next
      })
      toast.success('规则已保存')
    },
  })

  return (
    <div className="flex h-full">
      <div className="w-[200px] border-r border-border overflow-y-auto shrink-0">
        <button
          className={cn(
            'w-full text-left px-3 py-2 border-b border-border text-xs transition-colors',
            !selectedId ? 'bg-card' : 'hover:bg-bg2',
          )}
          onClick={() => setSelectedId(null)}
        >
          <span className="text-text font-medium">全部告警</span>
          <span className="ml-1 text-text3">({history.length})</span>
        </button>
        {rules.map((r) => (
          <button
            key={r.id}
            className={cn(
              'w-full text-left px-3 py-2 border-b border-border text-xs transition-colors',
              selectedId === r.id ? 'bg-card' : 'hover:bg-bg2',
              !getField(r, 'enabled') && 'opacity-50',
            )}
            onClick={() => setSelectedId(r.id)}
          >
            <div className="flex items-center gap-2">
              <span className={cn('w-1.5 h-1.5 rounded-full shrink-0', getField(r, 'enabled') ? 'bg-yellow' : 'bg-text3')} />
              <span className="text-text truncate">{r.name}</span>
            </div>
            <div className="text-text3 mt-0.5 font-mono text-[10px]">
              {r.metric} {r.operator} {r.warning_threshold ?? '?'}/{r.critical_threshold ?? '?'}
            </div>
          </button>
        ))}
      </div>
      <div className="flex-1 overflow-y-auto">
        {/* Rule editing section */}
        {selectedRule && (
          <div className="p-4 border-b border-border space-y-3">
            <h4 className="text-sm font-medium text-text">{selectedRule.name}</h4>
            <div className="text-xs text-text2">
              指标: <span className="font-mono text-accent">{selectedRule.metric}</span>
              <span className="text-text3 ml-1">{selectedRule.operator}</span>
            </div>
            <div className="grid grid-cols-2 gap-3 text-xs">
              <div>
                <label className="text-text3 block mb-0.5">警告阈值</label>
                <input
                  type="number"
                  step="any"
                  className="w-full bg-bg border border-border rounded px-2 py-1 text-text text-xs focus:border-accent focus:outline-none"
                  value={getField(selectedRule, 'warning_threshold') ?? ''}
                  onChange={(e) => setField(selectedRule.id, 'warning_threshold', e.target.value === '' ? null : Number(e.target.value))}
                />
              </div>
              <div>
                <label className="text-text3 block mb-0.5">严重阈值</label>
                <input
                  type="number"
                  step="any"
                  className="w-full bg-bg border border-border rounded px-2 py-1 text-text text-xs focus:border-accent focus:outline-none"
                  value={getField(selectedRule, 'critical_threshold') ?? ''}
                  onChange={(e) => setField(selectedRule.id, 'critical_threshold', e.target.value === '' ? null : Number(e.target.value))}
                />
              </div>
              <div>
                <label className="text-text3 block mb-0.5">冷却(分钟)</label>
                <input
                  type="number"
                  min={1}
                  className="w-full bg-bg border border-border rounded px-2 py-1 text-text text-xs focus:border-accent focus:outline-none"
                  value={getField(selectedRule, 'cooldown_minutes')}
                  onChange={(e) => setField(selectedRule.id, 'cooldown_minutes', Number(e.target.value))}
                />
              </div>
              <div className="flex items-end gap-2">
                <button
                  className={cn(
                    'px-2 py-1 text-xs rounded',
                    getField(selectedRule, 'notify')
                      ? 'bg-green/15 text-green'
                      : 'bg-bg text-text3 border border-border',
                  )}
                  onClick={() => setField(selectedRule.id, 'notify', !getField(selectedRule, 'notify'))}
                >
                  通知 {getField(selectedRule, 'notify') ? '开启' : '关闭'}
                </button>
                <button
                  className={cn(
                    'px-2 py-1 text-xs rounded',
                    getField(selectedRule, 'enabled')
                      ? 'bg-accent-dim text-accent'
                      : 'bg-yellow/15 text-yellow',
                  )}
                  onClick={() => setField(selectedRule.id, 'enabled', !getField(selectedRule, 'enabled'))}
                >
                  {getField(selectedRule, 'enabled') ? '已启用' : '已禁用'}
                </button>
              </div>
            </div>
            <div className="flex justify-end">
              <button
                className="px-2.5 py-1 text-xs rounded bg-accent-dim text-accent hover:opacity-80"
                onClick={() => saveMut.mutate({ rule: selectedRule })}
                disabled={saveMut.isPending}
              >
                保存规则
              </button>
            </div>
          </div>
        )}
        {/* Alert history */}
        <div className="px-4 py-2 border-b border-border shrink-0">
          <span className="text-xs font-medium text-text2">告警历史</span>
        </div>
        <div className="p-4 space-y-2">
          {filteredHistory.length === 0 && (
            <div className="text-text3 text-xs text-center pt-10">暂无告警记录</div>
          )}
          {filteredHistory.map((h) => (
            <div key={h.id} className="bg-bg2 rounded p-3 text-xs space-y-1">
              <div className="flex items-center justify-between">
                <span className="text-text font-medium">{h.rule_name}</span>
                <SeverityBadge severity={h.severity} />
              </div>
              <p className="text-text2">{h.message}</p>
              <div className="flex items-center justify-between text-text3">
                <span>{formatDate(h.created_at)}</span>
                <span className={h.resolved ? 'text-green' : 'text-yellow'}>
                  {h.resolved ? '已解决' : '未解决'}
                </span>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

/* ── Templates View ────────────────────────────────── */

interface TemplateVariable {
  name: string
  type: string
  default: string
  description: string
}

interface PatrolTemplate {
  id: string
  name: string
  description: string
  prompt: string
  prompt_template: string
  tools: string
  check_tools: string
  category: string
  is_builtin: boolean
  variables: TemplateVariable[]
}

interface CreateFromTplState {
  show: boolean
  tpl: PatrolTemplate | null
  displayName: string
  interval: number
  variables: Record<string, string>
}

function TemplatesView() {
  const qc = useQueryClient()
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [createState, setCreateState] = useState<CreateFromTplState>({
    show: false,
    tpl: null,
    displayName: '',
    interval: 60,
    variables: {},
  })

  const { data: templates = [] } = useQuery({
    queryKey: ['patrol-templates'],
    queryFn: () => client.get('/api/agents/templates').then((r) => ensureArray<PatrolTemplate>(r.data)),
  })

  const selected = templates.find((t) => t.id === selectedId) ?? null

  const categoryLabels: Record<string, string> = {
    performance: '性能',
    availability: '可用性',
    security: '安全',
    general: '通用',
  }

  const categories = ['performance', 'availability', 'security', 'general']

  const openCreateModal = (tpl: PatrolTemplate) => {
    const vars: Record<string, string> = {}
    for (const v of tpl.variables ?? []) {
      vars[v.name] = v.default ?? ''
    }
    setCreateState({ show: true, tpl, displayName: tpl.name, interval: 60, variables: vars })
  }

  const createMut = useMutation({
    mutationFn: () => {
      const { tpl, variables, interval, displayName } = createState
      return client.post('/api/agents/patrols/from-template', {
        template_id: tpl!.id,
        variables,
        interval_minutes: interval,
        display_name: displayName,
      })
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['patrols'] })
      setCreateState((s) => ({ ...s, show: false }))
      toast.success('已从模板创建巡检任务')
    },
  })

  return (
    <div className="flex h-full">
      <div className="w-[200px] border-r border-border overflow-y-auto shrink-0">
        {categories.map((cat) => {
          const catTpls = templates.filter((t) => t.category === cat)
          if (catTpls.length === 0) return null
          return (
            <div key={cat}>
              <div className="px-3 py-1.5 text-[10px] font-medium text-text3 uppercase bg-bg">
                {categoryLabels[cat] ?? cat}
              </div>
              {catTpls.map((t) => (
                <button
                  key={t.id}
                  className={cn(
                    'w-full text-left px-3 py-2.5 border-b border-border text-xs transition-colors',
                    selectedId === t.id ? 'bg-card' : 'hover:bg-bg2',
                  )}
                  onClick={() => setSelectedId(t.id)}
                >
                  <div className="flex items-center gap-1.5 text-text font-medium truncate">
                    <span className="truncate">{t.name}</span>
                    {t.is_builtin && (
                      <span className="shrink-0 px-1 py-0 rounded bg-accent-dim text-accent text-[9px]">内置</span>
                    )}
                  </div>
                </button>
              ))}
            </div>
          )
        })}
        {/* Templates without recognized category */}
        {templates.filter((t) => !categories.includes(t.category)).map((t) => (
          <button
            key={t.id}
            className={cn(
              'w-full text-left px-3 py-2.5 border-b border-border text-xs transition-colors',
              selectedId === t.id ? 'bg-card' : 'hover:bg-bg2',
            )}
            onClick={() => setSelectedId(t.id)}
          >
            <div className="text-text font-medium truncate">{t.name}</div>
          </button>
        ))}
        {templates.length === 0 && (
          <div className="text-text3 text-xs p-3 text-center">暂无模板</div>
        )}
      </div>
      <div className="flex-1 overflow-y-auto p-4">
        {selected ? (
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <h3 className="text-sm font-medium text-text">{selected.name}</h3>
                {selected.is_builtin && (
                  <span className="px-1.5 py-0.5 rounded bg-accent-dim text-accent text-[10px]">内置</span>
                )}
              </div>
              <button
                className="px-2 py-1 text-xs rounded bg-accent-dim text-accent hover:opacity-80"
                onClick={() => openCreateModal(selected)}
              >
                从此模板创建巡检任务
              </button>
            </div>
            <p className="text-xs text-text2">{selected.description}</p>
            <div className="flex items-center gap-1.5 flex-wrap">
              <span className="px-1.5 py-0.5 rounded bg-green/15 text-green text-[10px]">
                {categoryLabels[selected.category] ?? selected.category}
              </span>
              {(selected.check_tools || selected.tools || '').split(',').filter(Boolean).map((tool) => (
                <span key={tool} className="px-1.5 py-0.5 rounded bg-accent-dim text-accent text-[10px]">
                  {tool.trim()}
                </span>
              ))}
            </div>
            <div>
              <label className="text-xs text-text2 font-medium block mb-1">Prompt 模板</label>
              <pre className="text-xs text-text2 bg-bg rounded p-2 whitespace-pre-wrap max-h-40 overflow-y-auto">
                {selected.prompt_template || selected.prompt}
              </pre>
            </div>
            {/* Variable table (#5) */}
            {selected.variables && selected.variables.length > 0 && (
              <div>
                <label className="text-xs text-text2 font-medium block mb-1">变量定义</label>
                <div className="border border-border rounded overflow-hidden">
                  <table className="w-full text-xs">
                    <thead>
                      <tr className="bg-bg text-text3">
                        <th className="text-left px-2 py-1.5 font-medium">变量名</th>
                        <th className="text-left px-2 py-1.5 font-medium">类型</th>
                        <th className="text-left px-2 py-1.5 font-medium">默认值</th>
                        <th className="text-left px-2 py-1.5 font-medium">说明</th>
                      </tr>
                    </thead>
                    <tbody>
                      {selected.variables.map((v) => (
                        <tr key={v.name} className="border-t border-border">
                          <td className="px-2 py-1.5 font-mono text-accent">{v.name}</td>
                          <td className="px-2 py-1.5 text-text2">{v.type}</td>
                          <td className="px-2 py-1.5 text-text2">{v.default}</td>
                          <td className="px-2 py-1.5 text-text2">{v.description}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </div>
        ) : (
          <div className="text-text3 text-xs text-center pt-10">选择模板查看详情</div>
        )}
      </div>

      {/* Create-from-template modal (#2) */}
      {createState.show && createState.tpl && (
        <div
          className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center"
          onClick={(e) => { if (e.target === e.currentTarget) setCreateState((s) => ({ ...s, show: false })) }}
        >
          <div className="bg-card rounded-lg p-5 w-full max-w-md shadow-xl border border-border" onClick={(e) => e.stopPropagation()}>
            <h3 className="text-sm font-medium text-text mb-1">从模板创建巡检任务</h3>
            <p className="text-xs text-text2 mb-4">{createState.tpl.name}</p>
            <div className="space-y-3">
              <div>
                <label className="text-xs text-text3 block mb-0.5">任务名称</label>
                <input
                  className="w-full bg-bg border border-border rounded px-2 py-1.5 text-xs text-text focus:border-accent focus:outline-none"
                  value={createState.displayName}
                  onChange={(e) => setCreateState((s) => ({ ...s, displayName: e.target.value }))}
                />
              </div>
              <div>
                <label className="text-xs text-text3 block mb-0.5">执行间隔（分钟）</label>
                <input
                  type="number"
                  min={1}
                  className="w-24 bg-bg border border-border rounded px-2 py-1.5 text-xs text-text focus:border-accent focus:outline-none"
                  value={createState.interval}
                  onChange={(e) => setCreateState((s) => ({ ...s, interval: Number(e.target.value) }))}
                />
              </div>
              {(createState.tpl.variables ?? []).map((v) => (
                <div key={v.name}>
                  <label className="text-xs text-text3 block mb-0.5">
                    {v.description} ({v.name})
                  </label>
                  <input
                    type={v.type === 'number' ? 'number' : 'text'}
                    className="w-full bg-bg border border-border rounded px-2 py-1.5 text-xs text-text focus:border-accent focus:outline-none"
                    placeholder={v.default}
                    value={createState.variables[v.name] ?? ''}
                    onChange={(e) =>
                      setCreateState((s) => ({
                        ...s,
                        variables: { ...s.variables, [v.name]: e.target.value },
                      }))
                    }
                  />
                </div>
              ))}
            </div>
            <div className="flex justify-end gap-2 mt-5">
              <button
                className="px-3 py-1.5 text-xs rounded border border-border text-text2 hover:bg-bg2"
                onClick={() => setCreateState((s) => ({ ...s, show: false }))}
              >
                取消
              </button>
              <button
                className="px-3 py-1.5 text-xs rounded bg-accent-dim text-accent hover:opacity-80"
                onClick={() => createMut.mutate()}
                disabled={createMut.isPending}
              >
                创建
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

/* ── Reports View ──────────────────────────────────── */

interface FaultReport {
  id: string
  title: string
  severity: string
  status: string
  created_at: string
  detected_at?: string
  summary?: string
  source?: string
  root_cause?: string
}

interface FaultReportDetail extends FaultReport {
  detail?: string
  root_cause?: string
  symptoms?: string[]
  immediate_actions?: string[]
  long_term_solutions?: string[]
  evidence?: string[]
}

function ReportsView() {
  const qc = useQueryClient()
  const [selectedId, setSelectedId] = useState<string | null>(null)

  const { data: reports = [] } = useQuery({
    queryKey: ['fault-reports'],
    queryFn: () => client.get('/api/agents/fault-reports').then((r) => ensureArray<FaultReport>(r.data)),
  })

  const { data: detail } = useQuery({
    queryKey: ['fault-report', selectedId],
    queryFn: () => client.get<FaultReportDetail>(`/api/agents/fault-reports/${selectedId}`).then((r) => r.data),
    enabled: !!selectedId,
  })

  const resolveMut = useMutation({
    mutationFn: (id: string) =>
      client.put(`/api/agents/fault-reports/${id}/resolve`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['fault-reports'] })
      qc.invalidateQueries({ queryKey: ['fault-report', selectedId] })
      toast.success('已标记为解决')
    },
  })

  return (
    <div className="flex h-full">
      <div className="w-[200px] border-r border-border overflow-y-auto shrink-0">
        {reports.map((r) => (
          <button
            key={r.id}
            className={cn(
              'w-full text-left px-3 py-2.5 border-b border-border text-xs transition-colors',
              selectedId === r.id ? 'bg-card' : 'hover:bg-bg2',
            )}
            onClick={() => setSelectedId(r.id)}
          >
            <div className="text-text truncate font-medium">
              {(r.root_cause || r.source || r.title || '').slice(0, 40)}
            </div>
            <div className="flex items-center gap-1.5 mt-0.5">
              <StatusBadge status={r.status} />
              <span className="text-text3">
                {formatDate(r.detected_at || r.created_at)}
              </span>
            </div>
          </button>
        ))}
        {reports.length === 0 && (
          <div className="text-text3 text-xs p-3 text-center">暂无故障报告</div>
        )}
      </div>
      <div className="flex-1 overflow-y-auto p-4">
        {detail ? (
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <StatusBadge status={detail.status} />
                <SeverityBadge severity={detail.severity} />
              </div>
              {detail.status === 'open' && (
                <button
                  className="px-2 py-1 text-xs rounded bg-green/10 text-green hover:bg-green/20"
                  onClick={() => resolveMut.mutate(detail.id)}
                >
                  标记为已解决
                </button>
              )}
            </div>
            <div className="text-xs text-text3">
              {detail.source && <span>来源: {detail.source}</span>}
              {detail.source && ' | '}
              <span>{formatDate(detail.detected_at || detail.created_at)}</span>
            </div>
            {/* Root cause */}
            <FaultSection title="根本原因">
              <p className="text-xs text-text2">{detail.root_cause || '分析中...'}</p>
            </FaultSection>
            {/* Symptoms */}
            {detail.symptoms && detail.symptoms.length > 0 && (
              <FaultSection title="症状">
                <ul className="list-disc list-inside text-xs text-text2 space-y-0.5">
                  {detail.symptoms.map((s, i) => <li key={i}>{s}</li>)}
                </ul>
              </FaultSection>
            )}
            {/* Immediate actions */}
            {detail.immediate_actions && detail.immediate_actions.length > 0 && (
              <FaultSection title="紧急处置">
                <ul className="list-disc list-inside text-xs text-text2 space-y-0.5">
                  {detail.immediate_actions.map((a, i) => <li key={i}>{a}</li>)}
                </ul>
              </FaultSection>
            )}
            {/* Long-term solutions */}
            {detail.long_term_solutions && detail.long_term_solutions.length > 0 && (
              <FaultSection title="长期方案">
                <ul className="list-disc list-inside text-xs text-text2 space-y-0.5">
                  {detail.long_term_solutions.map((s, i) => <li key={i}>{s}</li>)}
                </ul>
              </FaultSection>
            )}
            {/* Evidence */}
            {detail.evidence && detail.evidence.length > 0 && (
              <FaultSection title="证据">
                <ul className="list-disc list-inside text-xs text-text2 space-y-0.5 font-mono">
                  {detail.evidence.map((e, i) => <li key={i} className="text-[11px]">{e}</li>)}
                </ul>
              </FaultSection>
            )}
          </div>
        ) : (
          <div className="text-text3 text-xs text-center pt-10">选择一个故障报告查看详情</div>
        )}
      </div>
    </div>
  )
}

function CreateCaseModal({ onClose, onSaved }: { onClose: () => void; onSaved: () => void }) {
  const [form, setForm] = useState({ title: '', category: '', symptoms: '', root_cause: '', solution: '', tags: '' })
  const mutation = useMutation({
    mutationFn: (data: typeof form) => client.post('/api/agents/fault-cases', data),
    onSuccess: () => { toast.success('案例已创建'); onSaved(); onClose() },
    onError: () => toast.error('创建失败'),
  })
  const set = (k: keyof typeof form, v: string) => setForm(f => ({ ...f, [k]: v }))

  return (
    <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4">
      <div className="bg-card border border-border rounded-xl w-full max-w-lg p-6 space-y-3">
        <h2 className="text-sm font-semibold text-text">新建故障案例</h2>
        {(['title', 'category', 'symptoms', 'root_cause', 'solution', 'tags'] as const).map(field => (
          <div key={field}>
            <label className="block text-xs text-text3 mb-1 capitalize">{field.replace('_', ' ')}</label>
            <input
              className="w-full bg-bg border border-border rounded px-2 py-1.5 text-xs text-text"
              value={form[field]}
              onChange={e => set(field, e.target.value)}
              placeholder={field === 'title' ? '必填' : '可选'}
            />
          </div>
        ))}
        <div className="flex justify-end gap-2 pt-1">
          <button onClick={onClose} className="px-3 py-1.5 text-xs text-text3 border border-border rounded-lg hover:text-text">取消</button>
          <button
            onClick={() => mutation.mutate(form)}
            disabled={mutation.isPending || !form.title}
            className="px-3 py-1.5 text-xs bg-accent text-white rounded-lg disabled:opacity-50"
          >
            {mutation.isPending ? '创建中...' : '创建'}
          </button>
        </div>
      </div>
    </div>
  )
}

/* ── Cases View ────────────────────────────────────── */

interface FaultCase {
  id: string
  title: string
  category: string
  summary: string
  symptoms?: string
  root_cause?: string
  solution?: string
  tags?: string
  source?: string
  created_at: string
}

function CasesView() {
  const qc = useQueryClient()
  const [query, setQuery] = useState('')
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [showCreate, setShowCreate] = useState(false)

  const { data: cases = [] } = useQuery({
    queryKey: ['fault-cases', query],
    queryFn: () => client.get('/api/agents/fault-cases', { params: { q: query } }).then((r) => ensureArray<FaultCase>(r.data)),
  })

  const deleteMut = useMutation({
    mutationFn: (id: string) => client.delete(`/api/agents/fault-cases/${id}`),
    onSuccess: (_d, id) => {
      toast.success('案例已删除')
      qc.invalidateQueries({ queryKey: ['fault-cases'] })
      if (selectedId === id) setSelectedId(null)
    },
    onError: () => toast.error('删除失败'),
  })

  const selected = cases.find((c) => c.id === selectedId) ?? null

  return (
    <>
      {showCreate && (
        <CreateCaseModal
          onClose={() => setShowCreate(false)}
          onSaved={() => qc.invalidateQueries({ queryKey: ['fault-cases'] })}
        />
      )}
      <div className="flex h-full">
        <div className="w-[200px] border-r border-border flex flex-col shrink-0">
          <div className="p-2 border-b border-border shrink-0 space-y-1">
            <input
              className="w-full bg-bg border border-border rounded px-2 py-1 text-xs text-text placeholder:text-text3 focus:border-accent focus:outline-none"
              placeholder="搜索案例..."
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
            <button
              onClick={() => setShowCreate(true)}
              className="w-full py-1 text-xs bg-accent/10 hover:bg-accent/20 text-accent rounded transition-colors"
            >
              + 新建案例
            </button>
          </div>
          <div className="flex-1 overflow-y-auto">
            {cases.map((c) => (
              <div
                key={c.id}
                className={cn(
                  'group border-b border-border text-xs',
                  selectedId === c.id ? 'bg-card' : 'hover:bg-bg2',
                )}
              >
                <button className="w-full text-left px-3 py-2.5 transition-colors" onClick={() => setSelectedId(c.id)}>
                  <div className="text-text font-medium truncate">{c.title}</div>
                  <div className="text-text3 mt-0.5 flex items-center gap-2">
                    <span className="px-1 rounded bg-accent-dim text-accent text-[9px]">{c.category || '通用'}</span>
                    <span className="text-[10px]">{c.source === 'auto' ? '自动' : '手动'}</span>
                  </div>
                </button>
                {c.source !== 'auto' && (
                  <div className="px-3 pb-1.5 hidden group-hover:block">
                    <button
                      onClick={() => {
                        if (window.confirm(`删除「${c.title}」？`)) deleteMut.mutate(c.id)
                      }}
                      className="text-[10px] text-red hover:underline"
                    >
                      删除
                    </button>
                  </div>
                )}
              </div>
            ))}
            {cases.length === 0 && (
              <div className="text-text3 text-xs p-3 text-center">暂无案例</div>
            )}
          </div>
        </div>
        <div className="flex-1 overflow-y-auto p-4">
          {selected ? (
            <div className="space-y-3">
              <h3 className="text-sm font-medium text-text">{selected.title}</h3>
              <div className="flex items-center gap-1.5 flex-wrap">
                <span className="px-1.5 py-0.5 rounded bg-accent-dim text-accent text-[10px]">
                  {selected.category || '通用'}
                </span>
                <span className={cn(
                  'px-1.5 py-0.5 rounded text-[10px]',
                  selected.source === 'auto' ? 'bg-yellow/15 text-yellow' : 'bg-green/15 text-green',
                )}>
                  {selected.source === 'auto' ? '自动生成' : '手动录入'}
                </span>
                {(selected.tags || '').split(',').filter(Boolean).map((tag) => (
                  <span key={tag} className="px-1.5 py-0.5 rounded bg-accent-dim text-accent text-[9px]">
                    {tag.trim()}
                  </span>
                ))}
              </div>
              {selected.symptoms && (
                <FaultSection title="症状描述">
                  <p className="text-xs text-text2">{selected.symptoms}</p>
                </FaultSection>
              )}
              {selected.root_cause && (
                <FaultSection title="根本原因">
                  <p className="text-xs text-text2">{selected.root_cause}</p>
                </FaultSection>
              )}
              {selected.solution && (
                <FaultSection title="解决方案">
                  <p className="text-xs text-text2">{selected.solution}</p>
                </FaultSection>
              )}
              <div className="text-[10px] text-text3 mt-2">
                创建于: {formatDate(selected.created_at)}
              </div>
            </div>
          ) : (
            <div className="text-text3 text-xs text-center pt-10">搜索或选择一个案例查看详情</div>
          )}
        </div>
      </div>
    </>
  )
}

/* ── Patrol Admin View (#7) ────────────────────────── */

function PatrolAdminView() {
  const qc = useQueryClient()
  const [openIds, setOpenIds] = useState<Set<string>>(new Set())
  const [editPrompts, setEditPrompts] = useState<Record<string, { prompt: string; check_tools: string }>>({})

  const { data: tasks = [] } = useQuery({
    queryKey: ['patrols'],
    queryFn: () => client.get('/api/agents/patrols').then((r) => ensureArray<PatrolTask>(r.data)),
  })

  const toggleOpen = (id: string) => {
    setOpenIds((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
    // Initialize edit state for this patrol if not already
    const task = tasks.find((t) => t.id === id)
    if (task && !editPrompts[id]) {
      setEditPrompts((prev) => ({
        ...prev,
        [id]: { prompt: task.prompt, check_tools: task.check_tools },
      }))
    }
  }

  const saveMut = useMutation({
    mutationFn: ({ id, prompt, check_tools }: { id: string; prompt: string; check_tools: string }) =>
      client.put(`/api/agents/patrols/${id}`, { prompt, check_tools }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['patrols'] })
      toast.success('巡检提示词已保存')
    },
  })

  return (
    <div className="overflow-y-auto p-4 space-y-2">
      <h3 className="text-sm font-medium text-text mb-2">巡检任务提示词</h3>
      {tasks.map((p) => {
        const isOpen = openIds.has(p.id)
        const edit = editPrompts[p.id] ?? { prompt: p.prompt, check_tools: p.check_tools }
        return (
          <div key={p.id} className="border border-border rounded">
            <button
              className="w-full flex items-center gap-2 px-3 py-2 text-left hover:bg-bg2 transition-colors"
              onClick={() => toggleOpen(p.id)}
            >
              <span className="text-[10px] text-text3">{isOpen ? '\u25BC' : '\u25B6'}</span>
              <span className="text-xs font-medium text-text">{p.display_name}</span>
              <span className="text-[10px] text-text3 ml-auto">{p.check_tools}</span>
            </button>
            {isOpen && (
              <div className="px-3 pb-3 space-y-2">
                <textarea
                  className="w-full bg-bg border border-border rounded p-2 text-xs text-text min-h-[80px] resize-y focus:border-accent focus:outline-none"
                  value={edit.prompt}
                  onChange={(e) =>
                    setEditPrompts((prev) => ({
                      ...prev,
                      [p.id]: { ...edit, prompt: e.target.value },
                    }))
                  }
                />
                <div>
                  <label className="text-[10px] text-text3 block mb-0.5">工具 (逗号分隔)</label>
                  <input
                    className="w-full bg-bg border border-border rounded px-2 py-1 text-xs text-text focus:border-accent focus:outline-none"
                    value={edit.check_tools}
                    onChange={(e) =>
                      setEditPrompts((prev) => ({
                        ...prev,
                        [p.id]: { ...edit, check_tools: e.target.value },
                      }))
                    }
                  />
                </div>
                <div className="flex justify-end">
                  <button
                    className="px-2.5 py-1 text-xs rounded bg-accent-dim text-accent hover:opacity-80"
                    onClick={() => saveMut.mutate({ id: p.id, prompt: edit.prompt, check_tools: edit.check_tools })}
                    disabled={saveMut.isPending}
                  >
                    保存
                  </button>
                </div>
              </div>
            )}
          </div>
        )
      })}
      {tasks.length === 0 && (
        <div className="text-text3 text-xs text-center pt-10">暂无巡检任务</div>
      )}
    </div>
  )
}

/* ── Shared components ─────────────────────────────── */

function FaultSection({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <h4 className="text-xs font-medium text-text mb-1">{title}</h4>
      {children}
    </div>
  )
}

function StatusBadge({ status }: { status: string }) {
  const isOpen = status === 'open'
  return (
    <span className={cn(
      'px-1.5 py-0.5 rounded text-[9px] shrink-0',
      isOpen ? 'bg-red/15 text-red' : 'bg-green/15 text-green',
    )}>
      {isOpen ? '待处理' : '已解决'}
    </span>
  )
}

function InfoItem({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-text3 mb-0.5">{label}</div>
      <div className="text-text">{value}</div>
    </div>
  )
}

function SeverityBadge({ severity }: { severity: string }) {
  const colors: Record<string, string> = {
    critical: 'bg-red/15 text-red',
    high: 'bg-orange/15 text-orange',
    medium: 'bg-yellow/15 text-yellow',
    low: 'bg-green/15 text-green',
    info: 'bg-accent-dim text-accent',
  }
  const cls = colors[severity.toLowerCase()] ?? 'bg-bg text-text3'
  return (
    <span className={cn('px-1.5 py-0.5 rounded text-xs shrink-0', cls)}>
      {severity}
    </span>
  )
}
