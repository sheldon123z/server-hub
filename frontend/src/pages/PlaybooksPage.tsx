/**
 * 运维剧本 (Ops Playbook) — 可复用运维工作流模板
 *
 * 功能: 剧本 CRUD / 参数化执行 / 执行历史 / 凭据管理
 * API 前缀: /api/playbooks
 */

import { useState, useMemo } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import client from '@/api/client'
import toast from 'react-hot-toast'
import { cn, formatDate, getErrorMessage } from '@/lib/utils'
import { renderMarkdown } from '@/lib/markdown'

/* ─── 类型定义 ─── */

interface PlaybookParameter {
  name: string
  type: 'string' | 'string[]' | 'number' | 'boolean' | 'secret'
  required?: boolean
  default?: string | number | boolean | string[]
  description?: string
  validation?: string
  credential_ref?: string
}

interface Playbook {
  id: string
  name: string
  description: string
  category: string
  system_prompt: string
  parameters: string // JSON string of PlaybookParameter[]
  tools_required: string
  validation_rules: string
  trigger_config: string
  safety_mode: string | null
  steps_visual: string | null
  is_builtin: number
  tags: string
  created_by: string
  created_at: string
  updated_at: string
}

interface PlaybookExecution {
  id: string
  playbook_id: string
  parameters_json: string
  status: 'pending' | 'running' | 'success' | 'failed' | 'cancelled'
  report: string | null
  triggered_by: string
  trigger_type: string
  started_at: string
  completed_at: string | null
  duration_seconds: number | null
  thread_id: string | null
  tool_calls_count: number
}

interface Credential {
  id: string
  name: string
  description: string
  credential_type: string
  created_by: string
  created_at: string
}

/* ─── 辅助函数 ─── */

function parseParams(raw: string): PlaybookParameter[] {
  try { return JSON.parse(raw) } catch { return [] }
}

function parseJson(raw: string): Record<string, unknown> {
  try { return JSON.parse(raw) } catch { return {} }
}

const CATEGORY_COLORS: Record<string, string> = {
  network: 'bg-purple/20 text-purple',
  system: 'bg-accent-dim text-accent',
  security: 'bg-red/20 text-red',
  general: 'bg-bg2 text-text3',
}

const STATUS_COLORS: Record<string, string> = {
  pending: 'bg-yellow/20 text-yellow',
  running: 'bg-accent-dim text-accent',
  success: 'bg-green/20 text-green',
  failed: 'bg-red/20 text-red',
  cancelled: 'bg-bg2 text-text3',
}

/* ─── 主页面 ─── */

export default function PlaybooksPage() {
  const [tab, setTab] = useState<'playbooks' | 'executions' | 'credentials'>('playbooks')

  return (
    <div>
      {/* Tab 栏 */}
      <div className="flex gap-1 mb-4 border-b border-border">
        {(['playbooks', 'executions', 'credentials'] as const).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={cn(
              'px-4 py-2 text-sm border-b-2 transition-colors',
              tab === t ? 'border-accent text-accent' : 'border-transparent text-text3 hover:text-text'
            )}
          >
            {t === 'playbooks' ? '剧本库' : t === 'executions' ? '执行记录' : '凭据管理'}
          </button>
        ))}
      </div>

      {tab === 'playbooks' && <PlaybooksTab />}
      {tab === 'executions' && <ExecutionsTab />}
      {tab === 'credentials' && <CredentialsTab />}
    </div>
  )
}

/* ─── 剧本库 Tab ─── */

function PlaybooksTab() {
  const queryClient = useQueryClient()
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [filterCategory, setFilterCategory] = useState('')
  const [showRunModal, setShowRunModal] = useState(false)
  const [showCreateForm, setShowCreateForm] = useState(false)

  const { data: playbooks = [], isLoading } = useQuery<Playbook[]>({
    queryKey: ['playbooks', filterCategory],
    queryFn: async () => {
      const res = await client.get('/api/playbooks', { params: filterCategory ? { category: filterCategory } : {} })
      return Array.isArray(res.data) ? res.data : res.data?.playbooks ?? []
    },
  })

  const deleteMut = useMutation({
    mutationFn: (id: string) => client.delete(`/api/playbooks/${id}`),
    onSuccess: () => { toast.success('已删除'); queryClient.invalidateQueries({ queryKey: ['playbooks'] }) },
    onError: (err: unknown) => toast.error(getErrorMessage(err, '删除失败')),
  })

  const selected = playbooks.find((p) => p.id === selectedId) ?? null
  const categories = useMemo(() => [...new Set(playbooks.map((p) => p.category))], [playbooks])

  if (isLoading) return <div className="text-text3 text-sm">加载中...</div>

  return (
    <div className="grid grid-cols-12 gap-4" style={{ height: 'calc(100vh - 200px)' }}>
      {/* 左侧: 剧本列表 */}
      <div className="col-span-4 border-r border-border pr-4 overflow-y-auto">
        <div className="flex items-center justify-between mb-3">
          <select
            value={filterCategory}
            onChange={(e) => setFilterCategory(e.target.value)}
            className="bg-bg border border-border rounded-md px-2 py-1 text-xs text-text"
          >
            <option value="">全部类别</option>
            {categories.map((c) => <option key={c} value={c}>{c}</option>)}
          </select>
          <button
            onClick={() => setShowCreateForm(true)}
            className="bg-accent text-[#0f172a] px-3 py-1 rounded-md text-xs font-medium"
          >
            + 新建剧本
          </button>
        </div>

        {playbooks.map((pb) => (
          <div
            key={pb.id}
            onClick={() => setSelectedId(pb.id)}
            className={cn(
              'p-3 rounded-lg cursor-pointer mb-2 transition-colors border',
              selectedId === pb.id ? 'bg-accent-dim border-accent/30' : 'bg-card border-border hover:border-border-light'
            )}
          >
            <div className="flex items-center justify-between">
              <span className="text-sm font-medium text-text">{pb.name}</span>
              <span className={cn('px-2 py-0.5 rounded text-[10px] font-medium', CATEGORY_COLORS[pb.category] ?? CATEGORY_COLORS.general)}>
                {pb.category}
              </span>
            </div>
            <div className="text-xs text-text3 mt-1 line-clamp-2">{pb.description}</div>
            <div className="flex gap-1 mt-2">
              {pb.is_builtin ? <span className="text-[10px] text-text3 bg-bg2 px-1.5 py-0.5 rounded">内置</span> : null}
              {pb.tags && pb.tags.split(',').filter(Boolean).map((t) => (
                <span key={t} className="text-[10px] text-text3 bg-bg2 px-1.5 py-0.5 rounded">{t.trim()}</span>
              ))}
            </div>
          </div>
        ))}
      </div>

      {/* 右侧: 剧本详情 */}
      <div className="col-span-8 overflow-y-auto">
        {!selected ? (
          <div className="flex items-center justify-center h-full text-text3 text-sm">选择一个剧本查看详情</div>
        ) : (
          <div>
            {/* 标题 + 操作 */}
            <div className="flex items-center justify-between mb-4">
              <div>
                <h3 className="text-lg font-semibold text-text">{selected.name}</h3>
                <p className="text-xs text-text3 mt-0.5">{selected.description}</p>
              </div>
              <div className="flex gap-2">
                <button
                  onClick={() => setShowRunModal(true)}
                  className="bg-green/20 text-green px-3 py-1.5 rounded-md text-sm font-medium hover:bg-green/30"
                >
                  执行
                </button>
                {!selected.is_builtin && (
                  <button
                    onClick={() => { if (confirm('确认删除？')) deleteMut.mutate(selected.id) }}
                    className="bg-red/20 text-red px-3 py-1.5 rounded-md text-sm hover:bg-red/30"
                  >
                    删除
                  </button>
                )}
              </div>
            </div>

            {/* 信息卡片 */}
            <div className="grid grid-cols-3 gap-3 mb-4">
              <InfoCard label="类别" value={selected.category} />
              <InfoCard label="所需工具" value={selected.tools_required || '无'} />
              <InfoCard label="创建者" value={selected.created_by} />
            </div>

            {/* 参数表 */}
            <Section title="参数定义">
              <ParamTable params={parseParams(selected.parameters)} />
            </Section>

            {/* 系统提示词 */}
            <Section title="系统提示词">
              <div className="bg-bg rounded-lg p-3 border border-border max-h-60 overflow-y-auto">
                <pre className="text-xs text-text2 whitespace-pre-wrap font-mono">{selected.system_prompt}</pre>
              </div>
            </Section>

            {/* 验证规则 */}
            <Section title="执行约束">
              {(() => {
                const rules = parseJson(selected.validation_rules)
                return (
                  <div className="flex gap-3 text-xs">
                    {rules.timeout_seconds != null && <span className="bg-bg2 px-2 py-1 rounded text-text2">超时: {String(rules.timeout_seconds)}s</span>}
                    {rules.max_tool_calls != null && <span className="bg-bg2 px-2 py-1 rounded text-text2">工具调用上限: {String(rules.max_tool_calls)}</span>}
                  </div>
                )
              })()}
            </Section>

            {/* 执行历史 */}
            <Section title="执行历史">
              <ExecutionHistory playbookId={selected.id} />
            </Section>
          </div>
        )}
      </div>

      {/* 执行 Modal */}
      {showRunModal && selected && (
        <RunPlaybookModal
          playbook={selected}
          onClose={() => setShowRunModal(false)}
        />
      )}

      {/* 创建 Modal */}
      {showCreateForm && (
        <CreatePlaybookModal onClose={() => setShowCreateForm(false)} />
      )}
    </div>
  )
}

/* ─── 参数表 ─── */

function ParamTable({ params }: { params: PlaybookParameter[] }) {
  if (params.length === 0) return <span className="text-xs text-text3">无参数</span>

  return (
    <table className="w-full text-xs">
      <thead>
        <tr className="text-text3 text-left border-b border-border">
          <th className="pb-1.5 font-medium">参数名</th>
          <th className="pb-1.5 font-medium">类型</th>
          <th className="pb-1.5 font-medium">必填</th>
          <th className="pb-1.5 font-medium">默认值</th>
          <th className="pb-1.5 font-medium">说明</th>
        </tr>
      </thead>
      <tbody>
        {params.map((p) => (
          <tr key={p.name} className="border-b border-border/50">
            <td className="py-1.5 font-mono text-accent">{p.name}</td>
            <td className="py-1.5">
              <span className={cn('px-1.5 py-0.5 rounded text-[10px]',
                p.type === 'secret' ? 'bg-red/20 text-red' : 'bg-bg2 text-text2'
              )}>{p.type}</span>
            </td>
            <td className="py-1.5">{p.required ? '是' : '否'}</td>
            <td className="py-1.5 text-text3">{p.default != null ? String(p.default) : '-'}</td>
            <td className="py-1.5 text-text3">{p.description ?? '-'}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

/* ─── 执行剧本 Modal ─── */

function RunPlaybookModal({ playbook, onClose }: { playbook: Playbook; onClose: () => void }) {
  const queryClient = useQueryClient()
  const params = parseParams(playbook.parameters)
  const [values, setValues] = useState<Record<string, unknown>>(() => {
    const init: Record<string, unknown> = {}
    for (const p of params) {
      if (p.default != null) init[p.name] = p.default
      else init[p.name] = p.type === 'boolean' ? false : p.type === 'number' ? 0 : ''
    }
    return init
  })

  const { data: credentials = [] } = useQuery<Credential[]>({
    queryKey: ['playbook-credentials'],
    queryFn: async () => {
      const res = await client.get('/api/playbooks/credentials')
      return Array.isArray(res.data) ? res.data : res.data?.credentials ?? []
    },
  })

  const runMut = useMutation({
    mutationFn: () => client.post(`/api/playbooks/${playbook.id}/run-async`, { parameters: values }),
    onSuccess: () => {
      toast.success('剧本已开始执行')
      queryClient.invalidateQueries({ queryKey: ['playbook-executions'] })
      onClose()
    },
    onError: (err: unknown) => toast.error(getErrorMessage(err, '执行失败')),
  })

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50" onClick={onClose}>
      <div className="bg-card border border-border rounded-xl p-6 w-[520px] max-h-[80vh] overflow-y-auto" onClick={(e) => e.stopPropagation()}>
        <h3 className="text-lg font-semibold mb-1">执行: {playbook.name}</h3>
        <p className="text-xs text-text3 mb-4">{playbook.description}</p>

        {params.length === 0 ? (
          <p className="text-sm text-text3 mb-4">此剧本无需参数</p>
        ) : (
          <div className="space-y-3 mb-4">
            {params.map((p) => (
              <div key={p.name}>
                <label className="text-xs text-text2 mb-1 block">
                  {p.name} {p.required && <span className="text-red">*</span>}
                  {p.description && <span className="text-text3 ml-1">— {p.description}</span>}
                </label>

                {/* 根据 type 渲染不同输入控件 */}
                {p.type === 'boolean' ? (
                  <label className="flex items-center gap-2 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={!!values[p.name]}
                      onChange={(e) => setValues({ ...values, [p.name]: e.target.checked })}
                      className="w-4 h-4 accent-accent"
                    />
                    <span className="text-sm text-text">{values[p.name] ? '是' : '否'}</span>
                  </label>
                ) : p.type === 'number' ? (
                  <input
                    type="number"
                    value={Number(values[p.name]) || 0}
                    onChange={(e) => setValues({ ...values, [p.name]: Number(e.target.value) })}
                    className="w-full bg-bg border border-border rounded-md px-3 py-2 text-sm text-text focus:border-accent focus:outline-none"
                  />
                ) : p.type === 'secret' ? (
                  <div className="flex gap-2">
                    <input
                      type="password"
                      value={String(values[p.name] ?? '')}
                      onChange={(e) => setValues({ ...values, [p.name]: e.target.value })}
                      placeholder="手动输入密码..."
                      className="flex-1 bg-bg border border-border rounded-md px-3 py-2 text-sm text-text focus:border-accent focus:outline-none"
                    />
                    {credentials.length > 0 && (
                      <select
                        value=""
                        onChange={(e) => {
                          if (e.target.value) setValues({ ...values, [p.name]: `__credential__:${e.target.value}` })
                        }}
                        className="bg-bg border border-border rounded-md px-2 py-1 text-xs text-text"
                      >
                        <option value="">引用凭据...</option>
                        {credentials.filter((c) => c.credential_type === 'ssh_password' || c.credential_type === 'generic').map((c) => (
                          <option key={c.name} value={c.name}>{c.name}</option>
                        ))}
                      </select>
                    )}
                  </div>
                ) : p.type === 'string[]' ? (
                  <textarea
                    value={Array.isArray(values[p.name]) ? (values[p.name] as string[]).join('\n') : String(values[p.name] ?? '')}
                    onChange={(e) => setValues({ ...values, [p.name]: e.target.value.split('\n').filter(Boolean) })}
                    rows={3}
                    placeholder="每行一个值..."
                    className="w-full bg-bg border border-border rounded-md px-3 py-2 text-sm text-text focus:border-accent focus:outline-none font-mono"
                  />
                ) : (
                  <input
                    type="text"
                    value={String(values[p.name] ?? '')}
                    onChange={(e) => setValues({ ...values, [p.name]: e.target.value })}
                    className="w-full bg-bg border border-border rounded-md px-3 py-2 text-sm text-text focus:border-accent focus:outline-none"
                  />
                )}
              </div>
            ))}
          </div>
        )}

        <div className="flex justify-end gap-2">
          <button onClick={onClose} className="px-4 py-2 text-sm text-text3 hover:text-text">取消</button>
          <button
            onClick={() => runMut.mutate()}
            disabled={runMut.isPending}
            className="bg-green/90 text-white px-4 py-2 rounded-md text-sm font-medium hover:bg-green disabled:opacity-50"
          >
            {runMut.isPending ? '启动中...' : '开始执行'}
          </button>
        </div>
      </div>
    </div>
  )
}

/* ─── 创建剧本 Modal ─── */

function CreatePlaybookModal({ onClose }: { onClose: () => void }) {
  const queryClient = useQueryClient()
  const [form, setForm] = useState({
    id: '', name: '', description: '', category: 'general',
    system_prompt: '', parameters: '[]', tools_required: '', tags: '',
  })

  const createMut = useMutation({
    mutationFn: () => client.post('/api/playbooks', form),
    onSuccess: () => {
      toast.success('剧本已创建')
      queryClient.invalidateQueries({ queryKey: ['playbooks'] })
      onClose()
    },
    onError: (err: unknown) => toast.error(getErrorMessage(err, '创建失败')),
  })

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50" onClick={onClose}>
      <div className="bg-card border border-border rounded-xl p-6 w-[600px] max-h-[80vh] overflow-y-auto" onClick={(e) => e.stopPropagation()}>
        <h3 className="text-lg font-semibold mb-4">新建运维剧本</h3>

        <div className="space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-xs text-text2 mb-1 block">剧本 ID</label>
              <input value={form.id} onChange={(e) => setForm({ ...form, id: e.target.value })}
                placeholder="snake_case 标识符"
                className="w-full bg-bg border border-border rounded-md px-3 py-2 text-sm text-text focus:border-accent focus:outline-none font-mono" />
            </div>
            <div>
              <label className="text-xs text-text2 mb-1 block">名称</label>
              <input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })}
                className="w-full bg-bg border border-border rounded-md px-3 py-2 text-sm text-text focus:border-accent focus:outline-none" />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-xs text-text2 mb-1 block">类别</label>
              <select value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })}
                className="w-full bg-bg border border-border rounded-md px-3 py-2 text-sm text-text focus:border-accent focus:outline-none">
                <option value="general">general</option>
                <option value="network">network</option>
                <option value="system">system</option>
                <option value="security">security</option>
              </select>
            </div>
            <div>
              <label className="text-xs text-text2 mb-1 block">标签 (逗号分隔)</label>
              <input value={form.tags} onChange={(e) => setForm({ ...form, tags: e.target.value })}
                className="w-full bg-bg border border-border rounded-md px-3 py-2 text-sm text-text focus:border-accent focus:outline-none" />
            </div>
          </div>

          <div>
            <label className="text-xs text-text2 mb-1 block">描述</label>
            <textarea value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} rows={2}
              className="w-full bg-bg border border-border rounded-md px-3 py-2 text-sm text-text focus:border-accent focus:outline-none" />
          </div>

          <div>
            <label className="text-xs text-text2 mb-1 block">系统提示词</label>
            <textarea value={form.system_prompt} onChange={(e) => setForm({ ...form, system_prompt: e.target.value })} rows={6}
              className="w-full bg-bg border border-border rounded-md px-3 py-2 text-sm text-text focus:border-accent focus:outline-none font-mono" />
          </div>

          <div>
            <label className="text-xs text-text2 mb-1 block">参数定义 (JSON)</label>
            <textarea value={form.parameters} onChange={(e) => setForm({ ...form, parameters: e.target.value })} rows={3}
              placeholder='[{"name":"ip","type":"string","required":true}]'
              className="w-full bg-bg border border-border rounded-md px-3 py-2 text-sm text-text focus:border-accent focus:outline-none font-mono" />
          </div>

          <div>
            <label className="text-xs text-text2 mb-1 block">所需工具 (逗号分隔)</label>
            <input value={form.tools_required} onChange={(e) => setForm({ ...form, tools_required: e.target.value })}
              placeholder="ssh_execute_command,think"
              className="w-full bg-bg border border-border rounded-md px-3 py-2 text-sm text-text focus:border-accent focus:outline-none font-mono" />
          </div>
        </div>

        <div className="flex justify-end gap-2 mt-4">
          <button onClick={onClose} className="px-4 py-2 text-sm text-text3 hover:text-text">取消</button>
          <button
            onClick={() => createMut.mutate()}
            disabled={!form.id || !form.name || !form.system_prompt || createMut.isPending}
            className="bg-accent text-[#0f172a] px-4 py-2 rounded-md text-sm font-medium disabled:opacity-50"
          >
            创建
          </button>
        </div>
      </div>
    </div>
  )
}

/* ─── 执行历史（嵌入剧本详情或独立 Tab） ─── */

function ExecutionHistory({ playbookId }: { playbookId?: string }) {
  const [selectedExec, setSelectedExec] = useState<string | null>(null)

  const { data: executions = [] } = useQuery<PlaybookExecution[]>({
    queryKey: ['playbook-executions', playbookId],
    queryFn: async () => {
      const url = playbookId ? `/api/playbooks/${playbookId}/executions` : '/api/playbooks/executions'
      const res = await client.get(url, { params: { limit: 20 } })
      return Array.isArray(res.data) ? res.data : res.data?.executions ?? []
    },
    refetchInterval: 5000,
  })

  const { data: execDetail } = useQuery({
    queryKey: ['playbook-execution-detail', selectedExec],
    queryFn: () => client.get(`/api/playbooks/executions/${selectedExec}`).then((r) => r.data),
    enabled: !!selectedExec,
  })

  const cancelMut = useMutation({
    mutationFn: (id: string) => client.post(`/api/playbooks/executions/${id}/cancel`),
    onSuccess: () => toast.success('已取消'),
  })

  if (executions.length === 0) return <span className="text-xs text-text3">暂无执行记录</span>

  return (
    <div>
      <table className="w-full text-xs">
        <thead>
          <tr className="text-text3 text-left border-b border-border">
            <th className="pb-1.5 font-medium">时间</th>
            <th className="pb-1.5 font-medium">状态</th>
            <th className="pb-1.5 font-medium">耗时</th>
            <th className="pb-1.5 font-medium">工具调用</th>
            <th className="pb-1.5 font-medium">触发</th>
            <th className="pb-1.5 font-medium">操作</th>
          </tr>
        </thead>
        <tbody>
          {executions.map((exec) => (
            <tr key={exec.id} className="border-b border-border/50 hover:bg-bg2/50">
              <td className="py-1.5">{formatDate(exec.started_at)}</td>
              <td className="py-1.5">
                <span className={cn('px-2 py-0.5 rounded text-[10px] font-medium', STATUS_COLORS[exec.status] ?? '')}>
                  {exec.status}
                </span>
              </td>
              <td className="py-1.5 text-text3">{exec.duration_seconds ? `${exec.duration_seconds.toFixed(1)}s` : '-'}</td>
              <td className="py-1.5 text-text3">{exec.tool_calls_count}</td>
              <td className="py-1.5 text-text3">{exec.triggered_by}</td>
              <td className="py-1.5 flex gap-2">
                <button onClick={() => setSelectedExec(exec.id)} className="text-accent hover:underline">报告</button>
                {(exec.status === 'pending' || exec.status === 'running') && (
                  <button onClick={() => cancelMut.mutate(exec.id)} className="text-red hover:underline">取消</button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      {/* 执行报告弹窗 */}
      {selectedExec && execDetail && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50" onClick={() => setSelectedExec(null)}>
          <div className="bg-card border border-border rounded-xl p-6 w-[700px] max-h-[80vh] overflow-y-auto" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-semibold">执行报告</h3>
              <span className={cn('px-2 py-0.5 rounded text-xs font-medium', STATUS_COLORS[execDetail.status] ?? '')}>
                {execDetail.status}
              </span>
            </div>
            {execDetail.report ? (
              <div
                className="prose prose-invert prose-sm max-w-none"
                dangerouslySetInnerHTML={{ __html: renderMarkdown(execDetail.report) }}
              />
            ) : (
              <p className="text-sm text-text3">{execDetail.status === 'running' ? '执行中...' : '暂无报告'}</p>
            )}
            <div className="flex justify-end mt-4">
              <button onClick={() => setSelectedExec(null)} className="px-4 py-2 text-sm text-text3 hover:text-text">关闭</button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

/* ─── 执行记录 Tab（全局） ─── */

function ExecutionsTab() {
  return (
    <div>
      <h3 className="text-sm font-semibold text-text mb-3">全部执行记录</h3>
      <ExecutionHistory />
    </div>
  )
}

/* ─── 凭据管理 Tab ─── */

function CredentialsTab() {
  const queryClient = useQueryClient()
  const [showAdd, setShowAdd] = useState(false)
  const [addForm, setAddForm] = useState({ name: '', value: '', description: '', credential_type: 'generic' })

  const { data: credentials = [] } = useQuery<Credential[]>({
    queryKey: ['playbook-credentials'],
    queryFn: async () => {
      const res = await client.get('/api/playbooks/credentials')
      return Array.isArray(res.data) ? res.data : res.data?.credentials ?? []
    },
  })

  const addMut = useMutation({
    mutationFn: () => client.post('/api/playbooks/credentials', addForm),
    onSuccess: () => {
      toast.success('凭据已保存')
      queryClient.invalidateQueries({ queryKey: ['playbook-credentials'] })
      setShowAdd(false)
      setAddForm({ name: '', value: '', description: '', credential_type: 'generic' })
    },
    onError: (err: unknown) => toast.error(getErrorMessage(err, '保存失败')),
  })

  const deleteMut = useMutation({
    mutationFn: (name: string) => client.delete(`/api/playbooks/credentials/${name}`),
    onSuccess: () => { toast.success('已删除'); queryClient.invalidateQueries({ queryKey: ['playbook-credentials'] }) },
  })

  return (
    <div>
      <div className="flex items-center justify-between mb-3">
        <p className="text-xs text-text3">凭据通过 Fernet 对称加密存储，值不可查看。</p>
        <button onClick={() => setShowAdd(!showAdd)} className="bg-accent text-[#0f172a] px-3 py-1 rounded-md text-xs font-medium">
          + 添加凭据
        </button>
      </div>

      {showAdd && (
        <div className="bg-card border border-border rounded-lg p-4 mb-4">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-xs text-text2 mb-1 block">名称</label>
              <input value={addForm.name} onChange={(e) => setAddForm({ ...addForm, name: e.target.value })}
                placeholder="switch_password"
                className="w-full bg-bg border border-border rounded-md px-3 py-2 text-sm text-text focus:border-accent focus:outline-none font-mono" />
            </div>
            <div>
              <label className="text-xs text-text2 mb-1 block">类型</label>
              <select value={addForm.credential_type} onChange={(e) => setAddForm({ ...addForm, credential_type: e.target.value })}
                className="w-full bg-bg border border-border rounded-md px-3 py-2 text-sm text-text">
                <option value="generic">通用</option>
                <option value="ssh_password">SSH 密码</option>
                <option value="api_key">API Key</option>
                <option value="token">Token</option>
              </select>
            </div>
          </div>
          <div className="mt-3">
            <label className="text-xs text-text2 mb-1 block">密钥值</label>
            <input type="password" value={addForm.value} onChange={(e) => setAddForm({ ...addForm, value: e.target.value })}
              className="w-full bg-bg border border-border rounded-md px-3 py-2 text-sm text-text focus:border-accent focus:outline-none" />
          </div>
          <div className="mt-3">
            <label className="text-xs text-text2 mb-1 block">描述</label>
            <input value={addForm.description} onChange={(e) => setAddForm({ ...addForm, description: e.target.value })}
              className="w-full bg-bg border border-border rounded-md px-3 py-2 text-sm text-text focus:border-accent focus:outline-none" />
          </div>
          <div className="flex justify-end gap-2 mt-3">
            <button onClick={() => setShowAdd(false)} className="text-xs text-text3 hover:text-text">取消</button>
            <button onClick={() => addMut.mutate()} disabled={!addForm.name || !addForm.value}
              className="bg-accent text-[#0f172a] px-3 py-1.5 rounded-md text-xs font-medium disabled:opacity-50">保存</button>
          </div>
        </div>
      )}

      {credentials.length === 0 ? (
        <p className="text-sm text-text3">暂无凭据</p>
      ) : (
        <table className="w-full text-sm">
          <thead>
            <tr className="text-text3 text-left text-xs border-b border-border">
              <th className="pb-2 font-medium">名称</th>
              <th className="pb-2 font-medium">类型</th>
              <th className="pb-2 font-medium">描述</th>
              <th className="pb-2 font-medium">创建者</th>
              <th className="pb-2 font-medium">创建时间</th>
              <th className="pb-2 font-medium">操作</th>
            </tr>
          </thead>
          <tbody>
            {credentials.map((c) => (
              <tr key={c.id} className="border-b border-border/50">
                <td className="py-2 font-mono text-accent text-xs">{c.name}</td>
                <td className="py-2"><span className="bg-bg2 px-2 py-0.5 rounded text-xs text-text3">{c.credential_type}</span></td>
                <td className="py-2 text-xs text-text3">{c.description || '-'}</td>
                <td className="py-2 text-xs text-text3">{c.created_by}</td>
                <td className="py-2 text-xs text-text3">{formatDate(c.created_at)}</td>
                <td className="py-2">
                  <button onClick={() => { if (confirm('确认删除凭据？')) deleteMut.mutate(c.name) }}
                    className="text-red text-xs hover:underline">删除</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}

/* ─── 通用组件 ─── */

function InfoCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="bg-bg2 rounded-lg p-3">
      <div className="text-[10px] text-text3 uppercase">{label}</div>
      <div className="text-sm text-text mt-0.5 font-mono break-all">{value}</div>
    </div>
  )
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="mb-4">
      <h4 className="text-xs font-semibold text-text2 mb-2 uppercase tracking-wider">{title}</h4>
      {children}
    </div>
  )
}
