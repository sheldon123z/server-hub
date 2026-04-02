/**
 * 团队管理页面 — 多 Agent 协作编排
 *
 * 功能: 团队 CRUD / 成员管理 / 任务执行(SSE) / 模板实例化
 * API 前缀: /api/agents/teams
 */

import { useState, useRef, useCallback } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import client from '@/api/client'
import toast from 'react-hot-toast'
import { cn, ensureArray, formatDate, getErrorMessage } from '@/lib/utils'
import { useAuthStore } from '@/stores/authStore'
import type {
  Team,
  TeamTopology,
  SafetyMode,
  AgentType,
  TeamMember,
  TeamExecution,
  ExecutionStatus,
  TeamTemplate,
  TeamCreateRequest,
  MemberCreateRequest,
} from '@/types/team'

/* ─── constants ─── */

const TOPOLOGY_LABELS: Record<TeamTopology, { label: string; color: string; desc: string }> = {
  supervisor: { label: '组长调度', color: 'bg-accent-dim text-accent', desc: 'Leader 分配任务给 Workers' },
  swarm: { label: '自主协作', color: 'bg-green/20 text-green', desc: 'Agent 间自主移交任务' },
  pipeline: { label: '流水线', color: 'bg-blue/20 text-blue', desc: '按 position 顺序执行' },
}

const AGENT_TYPE_COLORS: Record<AgentType, string> = {
  leader: 'bg-accent-dim text-accent',
  worker: 'bg-blue/20 text-blue',
  reviewer: 'bg-purple/20 text-purple',
}

const STATUS_BADGES: Record<string, string> = {
  pending: 'bg-text3/20 text-text3',
  running: 'bg-blue/20 text-blue',
  success: 'bg-green/20 text-green',
  failed: 'bg-red/20 text-red',
  timeout: 'bg-yellow/20 text-yellow',
  cancelled: 'bg-text3/20 text-text3',
}

/* ─── helpers ─── */

function normalizeTeams(value: unknown): Team[] {
  const arr = Array.isArray(value) ? value : (value as Record<string, unknown>)?.teams ?? []
  return ensureArray<Record<string, unknown>>(arr).map((item) => ({
    id: String(item.id ?? ''),
    name: String(item.name ?? ''),
    description: String(item.description ?? ''),
    topology: (['supervisor','swarm','pipeline'].includes(item.topology as string) ? item.topology : 'supervisor') as TeamTopology,
    config_json: String(item.config_json ?? '{}'),
    default_model: item.default_model ? String(item.default_model) : null,
    safety_mode: (['supervised','autonomous'].includes(item.safety_mode as string) ? item.safety_mode : 'supervised') as SafetyMode,
    max_steps: Number(item.max_steps ?? 50),
    timeout_seconds: Number(item.timeout_seconds ?? 300),
    enabled: Number(item.enabled ?? 1),
    is_builtin: Number(item.is_builtin ?? 0),
    created_by: String(item.created_by ?? ''),
    created_at: String(item.created_at ?? ''),
    updated_at: String(item.updated_at ?? ''),
    member_count: item.member_count != null ? Number(item.member_count) : undefined,
  }))
}

function normalizeMembers(value: unknown): TeamMember[] {
  const arr = Array.isArray(value) ? value : (value as Record<string, unknown>)?.members ?? []
  return ensureArray<Record<string, unknown>>(arr).map((item) => ({
    id: String(item.id ?? ''),
    team_id: String(item.team_id ?? ''),
    name: String(item.name ?? ''),
    agent_type: (item.agent_type as AgentType) ?? 'worker',
    description: String(item.description ?? ''),
    system_prompt: String(item.system_prompt ?? ''),
    tools_json: String(item.tools_json ?? '[]'),
    model_id: item.model_id ? String(item.model_id) : null,
    max_calls: Number(item.max_calls ?? 15),
    handoff_targets: String(item.handoff_targets ?? '[]'),
    position: Number(item.position ?? 0),
    config_json: String(item.config_json ?? '{}'),
  }))
}

function normalizeExecutions(value: unknown): TeamExecution[] {
  const arr = Array.isArray(value) ? value : (value as Record<string, unknown>)?.executions ?? []
  return ensureArray<Record<string, unknown>>(arr).map((item) => ({
    id: String(item.id ?? ''),
    team_id: String(item.team_id ?? ''),
    instruction: String(item.instruction ?? ''),
    status: (['pending','running','success','failed','timeout','cancelled'].includes(String(item.status)) ? String(item.status) : 'pending') as ExecutionStatus,
    topology: String(item.topology ?? 'supervisor') as TeamTopology,
    result: item.result ? String(item.result) : null,
    agent_outputs: String(item.agent_outputs ?? '{}'),
    started_by: String(item.started_by ?? ''),
    started_at: String(item.started_at ?? ''),
    completed_at: item.completed_at ? String(item.completed_at) : null,
    duration_seconds: item.duration_seconds != null ? Number(item.duration_seconds) : null,
    total_steps: item.total_steps != null ? Number(item.total_steps) : null,
    error: item.error ? String(item.error) : null,
  }))
}

function normalizeTemplates(value: unknown): TeamTemplate[] {
  const arr = Array.isArray(value) ? value : (value as Record<string, unknown>)?.templates ?? []
  return ensureArray<Record<string, unknown>>(arr).map((item) => ({
    id: String(item.id ?? ''),
    name: String(item.name ?? ''),
    description: String(item.description ?? ''),
    topology: String(item.topology ?? 'supervisor') as TeamTopology,
    member_defs: Array.isArray(item.member_defs) ? item.member_defs : Array.isArray(item.members) ? item.members : [],
    member_count: item.member_count != null ? Number(item.member_count) : Array.isArray(item.members) ? item.members.length : Array.isArray(item.member_defs) ? item.member_defs.length : 0,
    safety_mode: String(item.safety_mode ?? 'supervised') as SafetyMode,
    max_steps: Number(item.max_steps ?? 50),
    timeout_seconds: Number(item.timeout_seconds ?? 300),
  }))
}

/* ─── tab bar ─── */

function TabBar({ tabs, active, onChange }: { tabs: { key: string; label: string }[]; active: string; onChange: (k: string) => void }) {
  return (
    <div className="flex gap-4 border-b border-border mb-4">
      {tabs.map((t) => (
        <button
          key={t.key}
          onClick={() => onChange(t.key)}
          className={cn(
            'pb-2 px-1 text-sm font-medium transition-colors',
            active === t.key ? 'border-b-2 border-accent text-accent' : 'border-b-2 border-transparent text-text3 hover:text-text',
          )}
        >
          {t.label}
        </button>
      ))}
    </div>
  )
}

/* ─── Create team modal ─── */

function CreateTeamModal({ onDone }: { onDone: () => void }) {
  const qc = useQueryClient()
  const [form, setForm] = useState<TeamCreateRequest>({
    name: '',
    description: '',
    topology: 'supervisor',
    safety_mode: 'supervised',
    max_steps: 50,
    timeout_seconds: 300,
  })

  const createMut = useMutation({
    mutationFn: () => client.post('/api/agents/teams', form).then((r) => r.data),
    onSuccess: () => { toast.success('团队已创建'); qc.invalidateQueries({ queryKey: ['teams'] }); onDone() },
    onError: (err: unknown) => toast.error(getErrorMessage(err, '创建失败')),
  })

  return (
    <div className="bg-card border border-border rounded-lg p-4 mb-4">
      <h3 className="text-sm font-medium mb-3">创建团队</h3>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mb-3">
        <input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="团队名称" className="bg-bg border border-border rounded-md px-3 py-2 text-sm text-text focus:border-accent focus:outline-none" />
        <select value={form.topology} onChange={(e) => setForm({ ...form, topology: e.target.value as TeamTopology })} className="bg-bg border border-border rounded-md px-3 py-2 text-sm text-text focus:border-accent focus:outline-none">
          <option value="supervisor">组长调度</option>
          <option value="swarm">自主协作</option>
          <option value="pipeline">流水线</option>
        </select>
        <input value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} placeholder="描述" className="bg-bg border border-border rounded-md px-3 py-2 text-sm text-text focus:border-accent focus:outline-none" />
        <select value={form.safety_mode} onChange={(e) => setForm({ ...form, safety_mode: e.target.value as SafetyMode })} className="bg-bg border border-border rounded-md px-3 py-2 text-sm text-text focus:border-accent focus:outline-none">
          <option value="supervised">受监督 (需审批)</option>
          <option value="autonomous">自主模式</option>
        </select>
        <input type="number" value={form.max_steps} onChange={(e) => setForm({ ...form, max_steps: +e.target.value })} placeholder="最大步数" className="bg-bg border border-border rounded-md px-3 py-2 text-sm text-text focus:border-accent focus:outline-none" />
        <input type="number" value={form.timeout_seconds} onChange={(e) => setForm({ ...form, timeout_seconds: +e.target.value })} placeholder="超时(秒)" className="bg-bg border border-border rounded-md px-3 py-2 text-sm text-text focus:border-accent focus:outline-none" />
      </div>
      <div className="flex gap-2">
        <button onClick={() => createMut.mutate()} disabled={!form.name || createMut.isPending} className="bg-accent text-[#0f172a] px-3 py-1.5 rounded-md text-sm font-medium hover:opacity-90 disabled:opacity-50">创建</button>
        <button onClick={onDone} className="text-text3 px-3 py-1.5 rounded-md text-sm hover:text-text">取消</button>
      </div>
    </div>
  )
}

/* ─── Team detail: members ─── */

function MembersTab({ teamId }: { teamId: string }) {
  const qc = useQueryClient()
  const role = useAuthStore((s) => s.user?.role)
  const isAdmin = role === 'admin'
  const [showAdd, setShowAdd] = useState(false)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [editForm, setEditForm] = useState<MemberCreateRequest>({ name: '', system_prompt: '', agent_type: 'worker' })

  const { data, isLoading } = useQuery<TeamMember[]>({
    queryKey: ['team-members', teamId],
    queryFn: () => client.get(`/api/agents/teams/${teamId}`).then((r) => normalizeMembers((r.data as Record<string, unknown>)?.members ?? r.data)),
  })

  const addMut = useMutation({
    mutationFn: () => client.post(`/api/agents/teams/${teamId}/members`, editForm).then((r) => r.data),
    onSuccess: () => { toast.success('成员已添加'); setShowAdd(false); setEditForm({ name: '', system_prompt: '', agent_type: 'worker' }); qc.invalidateQueries({ queryKey: ['team-members', teamId] }) },
    onError: (err: unknown) => toast.error(getErrorMessage(err, '添加失败')),
  })

  const updateMut = useMutation({
    mutationFn: () => client.put(`/api/agents/teams/members/${editingId}`, editForm).then((r) => r.data),
    onSuccess: () => { toast.success('已更新'); setEditingId(null); qc.invalidateQueries({ queryKey: ['team-members', teamId] }) },
    onError: () => toast.error('更新失败'),
  })

  const deleteMut = useMutation({
    mutationFn: (memberId: string) => client.delete(`/api/agents/teams/members/${memberId}`).then((r) => r.data),
    onSuccess: () => { toast.success('已删除'); qc.invalidateQueries({ queryKey: ['team-members', teamId] }) },
    onError: () => toast.error('删除失败'),
  })

  if (isLoading) return <p className="text-text3 text-sm">加载中...</p>

  const members = ensureArray<TeamMember>(data)

  return (
    <>
      {isAdmin && !showAdd && (
        <button onClick={() => setShowAdd(true)} className="bg-accent text-[#0f172a] px-3 py-1.5 rounded-md text-sm font-medium hover:opacity-90 mb-4">+ 添加成员</button>
      )}

      {showAdd && (
        <div className="bg-card border border-border rounded-lg p-4 mb-4">
          <h3 className="text-sm font-medium mb-3">添加成员</h3>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mb-3">
            <input value={editForm.name} onChange={(e) => setEditForm({ ...editForm, name: e.target.value })} placeholder="成员名称" className="bg-bg border border-border rounded-md px-3 py-2 text-sm text-text focus:border-accent focus:outline-none" />
            <select value={editForm.agent_type} onChange={(e) => setEditForm({ ...editForm, agent_type: e.target.value as AgentType })} className="bg-bg border border-border rounded-md px-3 py-2 text-sm text-text focus:border-accent focus:outline-none">
              <option value="worker">Worker</option>
              <option value="leader">Leader</option>
              <option value="reviewer">Reviewer</option>
            </select>
            <textarea value={editForm.system_prompt} onChange={(e) => setEditForm({ ...editForm, system_prompt: e.target.value })} placeholder="系统提示词" rows={3} className="bg-bg border border-border rounded-md px-3 py-2 text-sm text-text focus:border-accent focus:outline-none col-span-full" />
          </div>
          <div className="flex gap-2">
            <button onClick={() => addMut.mutate()} disabled={!editForm.name || !editForm.system_prompt || addMut.isPending} className="bg-accent text-[#0f172a] px-3 py-1.5 rounded-md text-sm font-medium hover:opacity-90 disabled:opacity-50">添加</button>
            <button onClick={() => { setShowAdd(false); setEditForm({ name: '', system_prompt: '', agent_type: 'worker' }) }} className="text-text3 px-3 py-1.5 text-sm hover:text-text">取消</button>
          </div>
        </div>
      )}

      <div className="overflow-y-auto max-h-[480px]">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border">
              <th className="text-text3 text-left text-xs uppercase py-2 sticky top-0 z-10 bg-card">名称</th>
              <th className="text-text3 text-left text-xs uppercase py-2 sticky top-0 z-10 bg-card">类型</th>
              <th className="text-text3 text-left text-xs uppercase py-2 sticky top-0 z-10 bg-card">提示词</th>
              <th className="text-text3 text-left text-xs uppercase py-2 sticky top-0 z-10 bg-card">操作</th>
            </tr>
          </thead>
          <tbody>
            {members.map((m) => (
              <tr key={m.id} className="border-b border-border">
                <td className="py-2 text-text font-medium">{m.name}</td>
                <td className="py-2">
                  <span className={cn('px-2 py-0.5 rounded text-xs font-medium', AGENT_TYPE_COLORS[m.agent_type])}>{m.agent_type}</span>
                </td>
                <td className="py-2 text-text2 text-xs max-w-xs truncate" title={m.system_prompt}>{m.system_prompt.slice(0, 60)}...</td>
                <td className="py-2">
                  {isAdmin && (
                    <div className="flex gap-2">
                      <button onClick={() => { setEditingId(m.id); setEditForm({ name: m.name, system_prompt: m.system_prompt, agent_type: m.agent_type }) }} className="text-accent text-xs hover:underline">编辑</button>
                      <button onClick={() => { if (confirm(`删除成员 ${m.name}?`)) deleteMut.mutate(m.id) }} className="text-red text-xs hover:underline">删除</button>
                    </div>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {editingId && (
        <div className="bg-card border border-border rounded-lg p-4 mt-4">
          <h3 className="text-sm font-medium mb-2">编辑成员</h3>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-2 mb-2">
            <input value={editForm.name} onChange={(e) => setEditForm({ ...editForm, name: e.target.value })} className="bg-bg border border-border rounded px-2 py-1 text-xs text-text focus:border-accent focus:outline-none" />
            <textarea value={editForm.system_prompt} onChange={(e) => setEditForm({ ...editForm, system_prompt: e.target.value })} rows={2} className="bg-bg border border-border rounded px-2 py-1 text-xs text-text focus:border-accent focus:outline-none col-span-full" />
          </div>
          <div className="flex gap-2">
            <button onClick={() => updateMut.mutate()} className="text-green text-xs hover:underline">保存</button>
            <button onClick={() => setEditingId(null)} className="text-text3 text-xs hover:underline">取消</button>
          </div>
        </div>
      )}
    </>
  )
}

/* ─── Team detail: executions ─── */

function ExecutionsTab({ teamId }: { teamId: string }) {
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

function ExecutionDetail({ executionId }: { executionId: string }) {
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

/* ─── Team detail: execute (SSE) ─── */

function ExecuteTab({ team }: { team: Team }) {
  const role = useAuthStore((s) => s.user?.role)
  const isAdmin = role === 'admin'
  const [instruction, setInstruction] = useState('')
  const [messages, setMessages] = useState<Array<{ agent: string; content: string; type: string }>>([])
  const [isRunning, setIsRunning] = useState(false)
  const abortRef = useRef<AbortController | null>(null)

  const executeTeam = useCallback(async () => {
    if (!instruction.trim() || !isAdmin) return
    setIsRunning(true)
    setMessages([])
    const controller = new AbortController()
    abortRef.current = controller

    try {
      const response = await fetch(`/api/agents/teams/${team.id}/execute`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ instruction }),
        credentials: 'include',
        signal: controller.signal,
      })

      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      if (!response.body) throw new Error('No response body')

      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      let currentEvent = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })

        const lines = buffer.split('\n')
        buffer = lines.pop() ?? ''

        for (const line of lines) {
          if (line.startsWith('event: ')) {
            currentEvent = line.slice(7).trim()
          } else if (line.startsWith('data: ')) {
            try {
              const payload = JSON.parse(line.slice(6))
              const eventType = currentEvent || (payload.event ?? payload.type)
              const data = payload.data ?? payload
              currentEvent = ''

              if (eventType === 'agent_message' || eventType === 'message') {
                setMessages((prev) => [...prev, { agent: data.agent ?? data.from_agent ?? 'system', content: data.content ?? data.text ?? '', type: 'message' }])
              } else if (eventType === 'agent_tool_call' || eventType === 'tool_call') {
                setMessages((prev) => [...prev, { agent: data.agent ?? '', content: `调用工具: ${data.tool ?? ''}`, type: 'tool' }])
              } else if (eventType === 'agent_tool_result' || eventType === 'tool_result') {
                setMessages((prev) => [...prev, { agent: data.agent ?? '', content: `工具结果: ${(data.output ?? '').toString().slice(0, 200)}`, type: 'result' }])
              } else if (eventType === 'team_error' || eventType === 'error') {
                setMessages((prev) => [...prev, { agent: 'system', content: `错误: ${data.error ?? data.message ?? ''}`, type: 'error' }])
              } else if (eventType === 'team_complete') {
                const status = String(data.status ?? 'done')
                const failStatuses = ['failed', 'timeout', 'cancelled']
                const msgType = status === 'success' ? 'complete' : failStatuses.includes(status) ? 'error' : 'complete'
                const label = status === 'success' ? '完成' : failStatuses.includes(status) ? `${status} — 执行未成功` : `完成 (${status})`
                setMessages((prev) => [...prev, { agent: 'system', content: `${label} — 耗时: ${data.duration ?? '-'}s, 步数: ${data.steps ?? '-'}`, type: msgType }])
              }
              // 'done' is stream-end marker only, no UI message needed
            } catch { /* ignore parse errors */ }
          }
        }
      }
    } catch (err: unknown) {
      if ((err as Error).name !== 'AbortError') {
        toast.error(getErrorMessage(err, '执行失败'))
      }
    } finally {
      setIsRunning(false)
      abortRef.current = null
    }
  }, [instruction, team.id, isAdmin])

  if (!isAdmin) return <p className="text-text3 text-sm">需要管理员权限才能执行任务</p>

  return (
    <div>
      <div className="flex gap-2 mb-4">
        <textarea
          value={instruction}
          onChange={(e) => setInstruction(e.target.value)}
          placeholder="输入执行指令..."
          rows={3}
          disabled={isRunning}
          className="bg-bg border border-border rounded-md px-3 py-2 text-sm text-text focus:border-accent focus:outline-none flex-1 resize-none"
        />
        <div className="flex flex-col gap-2">
          {isRunning ? (
            <button onClick={() => abortRef.current?.abort()} className="bg-red/20 text-red px-3 py-1.5 rounded-md text-sm font-medium hover:bg-red/30">停止</button>
          ) : (
            <button onClick={executeTeam} disabled={!instruction.trim()} className="bg-accent text-[#0f172a] px-3 py-1.5 rounded-md text-sm font-medium hover:opacity-90 disabled:opacity-50">执行</button>
          )}
        </div>
      </div>

      {messages.length > 0 && (
        <div className="bg-bg border border-border rounded-lg p-3 max-h-[400px] overflow-y-auto space-y-2">
          {messages.map((msg, i) => (
            <div key={i} className={cn('text-xs p-2 rounded', msg.type === 'error' ? 'bg-red/10 text-red' : msg.type === 'complete' ? 'bg-green/10 text-green' : msg.type === 'tool' ? 'bg-blue/10 text-blue' : msg.type === 'result' ? 'bg-purple/10 text-purple' : 'bg-bg2 text-text2')}>
              <span className="font-medium text-accent">[{msg.agent}]</span> {msg.content}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

/* ─── Templates tab ─── */

function TemplatesTab() {
  const qc = useQueryClient()
  const role = useAuthStore((s) => s.user?.role)
  const isAdmin = role === 'admin'

  const { data, isLoading } = useQuery<TeamTemplate[]>({
    queryKey: ['team-templates'],
    queryFn: () => client.get('/api/agents/teams/templates').then((r) => normalizeTemplates(r.data)),
  })

  const instantiateMut = useMutation({
    mutationFn: (templateId: string) => client.post(`/api/agents/teams/templates/${templateId}/instantiate`).then((r) => r.data),
    onSuccess: () => { toast.success('团队已从模板创建'); qc.invalidateQueries({ queryKey: ['teams'] }) },
    onError: (err: unknown) => toast.error(getErrorMessage(err, '实例化失败')),
  })

  if (isLoading) return <p className="text-text3 text-sm">加载中...</p>

  const templates = ensureArray<TeamTemplate>(data)

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
      {templates.map((tpl) => (
        <div key={tpl.id} className="bg-card border border-border rounded-lg p-4">
          <div className="flex items-center justify-between mb-2">
            <span className="font-medium text-text">{tpl.name}</span>
            <span className={cn('px-2 py-0.5 rounded text-xs font-medium', TOPOLOGY_LABELS[tpl.topology]?.color ?? 'bg-text3/20 text-text3')}>
              {TOPOLOGY_LABELS[tpl.topology]?.label ?? tpl.topology}
            </span>
          </div>
          <p className="text-text3 text-xs mb-3">{tpl.description}</p>
          <div className="text-text2 text-xs mb-3">
            <span>{tpl.member_count ?? tpl.member_defs.length} 个成员</span>
            <span className="mx-2">·</span>
            <span>{tpl.max_steps} 步</span>
            <span className="mx-2">·</span>
            <span>{tpl.timeout_seconds}s 超时</span>
          </div>
          {isAdmin && (
            <button onClick={() => instantiateMut.mutate(tpl.id)} disabled={instantiateMut.isPending} className="bg-accent text-[#0f172a] px-3 py-1 rounded-md text-xs font-medium hover:opacity-90 disabled:opacity-50">
              从模板创建
            </button>
          )}
        </div>
      ))}
    </div>
  )
}

/* ─── Team detail panel ─── */

function TeamDetail({ team, onBack }: { team: Team; onBack: () => void }) {
  const qc = useQueryClient()
  const role = useAuthStore((s) => s.user?.role)
  const isAdmin = role === 'admin'
  const [activeTab, setActiveTab] = useState('members')
  const [showEdit, setShowEdit] = useState(false)

  const deleteMut = useMutation({
    mutationFn: () => client.delete(`/api/agents/teams/${team.id}`).then((r) => r.data),
    onSuccess: () => { toast.success('团队已删除'); qc.invalidateQueries({ queryKey: ['teams'] }); onBack() },
    onError: (err: unknown) => toast.error(getErrorMessage(err, '删除失败')),
  })

  const toggleMut = useMutation({
    mutationFn: () => client.put(`/api/agents/teams/${team.id}`, { enabled: team.enabled ? 0 : 1 }).then((r) => r.data),
    onSuccess: () => { toast.success(team.enabled ? '已禁用' : '已启用'); qc.invalidateQueries({ queryKey: ['teams'] }) },
    onError: () => toast.error('操作失败'),
  })

  const topo = TOPOLOGY_LABELS[team.topology]

  return (
    <div>
      <button onClick={onBack} className="text-text3 text-xs hover:text-text mb-3">← 返回列表</button>

      <div className="bg-card border border-border rounded-lg p-4 mb-4">
        <div className="flex items-center justify-between mb-2">
          <h3 className="text-lg font-semibold text-text">{team.name}</h3>
          <div className="flex gap-2">
            {isAdmin && (
              <>
                <button onClick={() => toggleMut.mutate()} className={cn('px-3 py-1 rounded-md text-xs font-medium', team.enabled ? 'bg-green/20 text-green' : 'bg-text3/20 text-text3')}>
                  {team.enabled ? '已启用' : '已禁用'}
                </button>
                {!team.is_builtin && (
                  <button onClick={() => { if (confirm(`删除团队 ${team.name}?`)) deleteMut.mutate() }} className="bg-red/20 text-red px-3 py-1 rounded-md text-xs font-medium hover:bg-red/30">删除</button>
                )}
              </>
            )}
          </div>
        </div>
        <p className="text-text3 text-xs mb-2">{team.description || '无描述'}</p>
        <div className="flex gap-4 text-xs text-text2">
          <span className={cn('px-2 py-0.5 rounded font-medium', topo?.color)}>{topo?.label}</span>
          <span>{team.safety_mode === 'supervised' ? '受监督' : '自主'}</span>
          <span>{team.max_steps} 步</span>
          <span>{team.timeout_seconds}s</span>
          {team.member_count != null && <span>{team.member_count} 成员</span>}
        </div>
      </div>

      <TabBar
        tabs={[
          { key: 'members', label: '成员' },
          { key: 'execute', label: '执行' },
          { key: 'executions', label: '历史' },
        ]}
        active={activeTab}
        onChange={setActiveTab}
      />

      {activeTab === 'members' && <MembersTab teamId={team.id} />}
      {activeTab === 'execute' && <ExecuteTab team={team} />}
      {activeTab === 'executions' && <ExecutionsTab teamId={team.id} />}
    </div>
  )
}

/* ─── Main page ─── */

export default function TeamsPage() {
  const [activeTab, setActiveTab] = useState('teams')
  const [showCreate, setShowCreate] = useState(false)
  const [selectedTeamId, setSelectedTeamId] = useState<string | null>(null)

  const { data, isLoading } = useQuery<Team[]>({
    queryKey: ['teams'],
    queryFn: () => client.get('/api/agents/teams').then((r) => normalizeTeams(r.data)),
  })

  const { data: selectedTeam } = useQuery<Team & { members: TeamMember[] }>({
    queryKey: ['team-detail', selectedTeamId],
    queryFn: () => client.get(`/api/agents/teams/${selectedTeamId}`).then((r) => {
      const raw = r.data as Record<string, unknown>
      const team = normalizeTeams([raw.team])[0]
      return { ...team, members: normalizeMembers(raw.members) } as Team & { members: TeamMember[] }
    }),
    enabled: !!selectedTeamId,
  })

  if (isLoading) return <p className="text-text3 text-sm">加载中...</p>

  const teams = ensureArray<Team>(data)

  // Detail view
  if (selectedTeamId && selectedTeam) {
    return (
      <div>
        <h2 className="text-lg font-semibold mb-4">团队管理</h2>
        <TeamDetail team={selectedTeam} onBack={() => setSelectedTeamId(null)} />
      </div>
    )
  }

  return (
    <div>
      <h2 className="text-lg font-semibold mb-4">团队管理</h2>

      <TabBar
        tabs={[
          { key: 'teams', label: '团队列表' },
          { key: 'templates', label: '模板' },
        ]}
        active={activeTab}
        onChange={setActiveTab}
      />

      {activeTab === 'teams' && (
        <>
          {showCreate ? (
            <CreateTeamModal onDone={() => setShowCreate(false)} />
          ) : (
            <button onClick={() => setShowCreate(true)} className="bg-accent text-[#0f172a] px-3 py-1.5 rounded-md text-sm font-medium hover:opacity-90 mb-4">+ 创建团队</button>
          )}

          {teams.length === 0 ? (
            <p className="text-text3 text-sm">暂无团队</p>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
              {teams.map((team) => {
                const topo = TOPOLOGY_LABELS[team.topology]
                return (
                  <div
                    key={team.id}
                    onClick={() => setSelectedTeamId(team.id)}
                    className="bg-card border border-border rounded-lg p-4 cursor-pointer hover:border-accent/50 transition-colors"
                  >
                    <div className="flex items-center justify-between mb-2">
                      <span className="font-medium text-text">{team.name}</span>
                      <span className={cn('px-2 py-0.5 rounded text-xs font-medium', topo?.color ?? 'bg-text3/20 text-text3')}>
                        {topo?.label}
                      </span>
                    </div>
                    <p className="text-text3 text-xs mb-2">{team.description || '无描述'}</p>
                    <div className="flex gap-3 text-xs text-text2">
                      <span>{team.member_count ?? 0} 成员</span>
                      <span className={cn('px-1.5 py-0.5 rounded', team.enabled ? 'text-green' : 'text-text3')}>
                        {team.enabled ? '启用' : '禁用'}
                      </span>
                      {team.is_builtin ? <span className="text-text3">内置</span> : null}
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </>
      )}

      {activeTab === 'templates' && <TemplatesTab />}
    </div>
  )
}
