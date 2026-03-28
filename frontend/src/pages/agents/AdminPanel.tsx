/**
 * AdminPanel - Agent configuration management.
 * Sections: System Prompt, SubAgents, Memory, RAG.
 */

import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import client from '@/api/client'
import toast from 'react-hot-toast'
import { cn } from '@/lib/utils'

type AdminSection = 'prompt' | 'subagents' | 'memory' | 'rag'

export function AdminPanel() {
  const [section, setSection] = useState<AdminSection>('prompt')

  const sections: { key: AdminSection; label: string }[] = [
    { key: 'prompt', label: '提示词' },
    { key: 'subagents', label: 'SubAgents' },
    { key: 'memory', label: '记忆' },
    { key: 'rag', label: 'RAG' },
  ]

  return (
    <div className="flex flex-col h-full">
      {/* Section tabs */}
      <div className="flex items-center gap-1 px-3 py-2 border-b border-border bg-bg2 shrink-0">
        {sections.map((s) => (
          <button
            key={s.key}
            className={cn(
              'px-2.5 py-1 text-xs rounded transition-colors',
              section === s.key
                ? 'bg-accent-dim text-accent'
                : 'text-text3 hover:text-text hover:bg-card',
            )}
            onClick={() => setSection(s.key)}
          >
            {s.label}
          </button>
        ))}
      </div>

      {/* Section content */}
      <div className="flex-1 min-h-0 overflow-y-auto p-4">
        {section === 'prompt' && <PromptSection />}
        {section === 'subagents' && <SubAgentsSection />}
        {section === 'memory' && <MemorySection />}
        {section === 'rag' && <RagSection />}
      </div>
    </div>
  )
}

/* ── System Prompt ──────────────────────────────────── */

function PromptSection() {
  const qc = useQueryClient()
  const [draft, setDraft] = useState<string | null>(null)

  const { data } = useQuery({
    queryKey: ['admin-prompt'],
    queryFn: () => client.get<{ prompt: string }>('/api/agents/admin/prompt').then((r) => r.data),
  })

  const saveMut = useMutation({
    mutationFn: (prompt: string) => client.put('/api/agents/admin/prompt', { prompt }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['admin-prompt'] })
      toast.success('提示词已保存')
      setDraft(null)
    },
    onError: () => toast.error('保存失败'),
  })

  const resetMut = useMutation({
    mutationFn: () => client.put('/api/agents/admin/prompt', { prompt: null }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['admin-prompt'] })
      toast.success('已恢复默认')
      setDraft(null)
    },
  })

  const currentPrompt = draft ?? data?.prompt ?? ''

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-medium text-text">系统提示词</h3>
        <div className="flex items-center gap-2">
          <button
            className="px-2 py-1 text-xs rounded text-text3 hover:text-text hover:bg-card transition-colors"
            onClick={() => resetMut.mutate()}
          >
            恢复默认
          </button>
          <button
            className="px-2 py-1 text-xs rounded bg-accent-dim text-accent hover:opacity-80 disabled:opacity-50"
            disabled={draft === null || saveMut.isPending}
            onClick={() => draft !== null && saveMut.mutate(draft)}
          >
            保存
          </button>
        </div>
      </div>
      <textarea
        className="w-full h-80 bg-bg border border-border rounded p-3 text-xs text-text font-mono resize-none focus:border-accent focus:outline-none"
        value={currentPrompt}
        onChange={(e) => setDraft(e.target.value)}
        placeholder="输入系统提示词..."
      />
    </div>
  )
}

/* ── SubAgents ──────────────────────────────────────── */

interface SubAgentConfig {
  name: string
  model: string | null
  description: string
  system_prompt: string
  tools: string[]
}

interface ToolInfo {
  name: string
  description: string
  risk_level: string
}

interface ProviderInfo {
  id: string
  name: string
  has_key?: boolean
  models: { id: string; name: string }[]
}

interface SubAgentsResponse {
  subagents: SubAgentConfig[]
  available_tools: ToolInfo[]
  providers: ProviderInfo[]
}

const RISK_BADGE_CLASSES: Record<string, string> = {
  safe: 'bg-green/15 text-green',
  moderate: 'bg-yellow/15 text-yellow',
  dangerous: 'bg-red/15 text-red',
  critical: 'bg-red/15 text-red',
}

function SubAgentsSection() {
  const qc = useQueryClient()
  const [editingIdx, setEditingIdx] = useState<number | null>(null)
  const [editDraft, setEditDraft] = useState<SubAgentConfig | null>(null)

  const { data } = useQuery({
    queryKey: ['admin-subagents'],
    queryFn: () =>
      client.get<SubAgentsResponse>('/api/agents/admin/subagents').then((r) => r.data),
  })

  const saveMut = useMutation({
    mutationFn: (subagents: SubAgentConfig[]) =>
      client.put('/api/agents/admin/subagents', { subagents }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['admin-subagents'] })
      toast.success('SubAgent 配置已保存')
      setEditingIdx(null)
      setEditDraft(null)
    },
    onError: () => toast.error('保存失败'),
  })

  const subagents = data?.subagents ?? []
  const availableTools = data?.available_tools ?? []
  const providers = data?.providers ?? []

  function handleEdit(idx: number) {
    setEditingIdx(idx)
    setEditDraft({ ...subagents[idx], tools: [...subagents[idx].tools] })
  }

  function handleSave() {
    if (editDraft === null || editingIdx === null) return
    const updated = [...subagents]
    updated[editingIdx] = editDraft
    saveMut.mutate(updated)
  }

  function handleAdd() {
    const newAgent: SubAgentConfig = {
      name: `subagent-${subagents.length + 1}`,
      model: null,
      description: '',
      system_prompt: '',
      tools: [],
    }
    const updated = [...subagents, newAgent]
    saveMut.mutate(updated)
  }

  function handleDelete(idx: number) {
    if (!confirm(`确定删除 SubAgent "${subagents[idx].name}" 吗？`)) return
    const updated = subagents.filter((_, i) => i !== idx)
    saveMut.mutate(updated)
  }

  function toggleTool(toolName: string, checked: boolean) {
    if (!editDraft) return
    const tools = checked
      ? [...editDraft.tools, toolName]
      : editDraft.tools.filter((t) => t !== toolName)
    setEditDraft({ ...editDraft, tools })
  }

  // Derive provider/model from editDraft.model ("provider:model" format)
  const selectedProvider = editDraft?.model?.split(':')[0] ?? ''
  const selectedModel = editDraft?.model?.split(':').slice(1).join(':') ?? ''
  const providerModels = providers.find((p) => p.id === selectedProvider)?.models ?? []

  function pickProvider(providerId: string) {
    if (!editDraft) return
    if (!providerId) {
      setEditDraft({ ...editDraft, model: null })
      return
    }
    const prov = providers.find((p) => p.id === providerId)
    const firstModel = prov?.models?.[0]?.id ?? ''
    setEditDraft({ ...editDraft, model: `${providerId}:${firstModel}` })
  }

  function pickModel(modelId: string) {
    if (!editDraft) return
    setEditDraft({ ...editDraft, model: `${selectedProvider}:${modelId}` })
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-medium text-text">SubAgent 配置</h3>
        <button
          className="px-2 py-1 text-xs rounded bg-accent-dim text-accent hover:opacity-80"
          onClick={handleAdd}
        >
          + 新增 SubAgent
        </button>
      </div>

      {/* SubAgent card grid */}
      <div className="grid grid-cols-[repeat(auto-fill,minmax(240px,1fr))] gap-2.5">
        {subagents.map((agent, idx) => (
          <div
            key={`${agent.name}-${idx}`}
            className={cn(
              'bg-bg2 rounded-lg p-3 text-xs space-y-1.5 cursor-pointer border transition-colors',
              editingIdx === idx ? 'border-accent' : 'border-transparent hover:border-border',
            )}
            onClick={() =>
              editingIdx === idx
                ? (setEditingIdx(null), setEditDraft(null))
                : handleEdit(idx)
            }
          >
            <div className="text-text font-medium">{agent.name}</div>
            <div className="text-text3 truncate">
              {agent.description.length > 60
                ? agent.description.slice(0, 60) + '...'
                : agent.description}
            </div>
            <div className="flex flex-wrap gap-1">
              {(agent.tools.length ? agent.tools : ['继承全部']).map((t) => (
                <span key={t} className="bg-bg rounded px-1.5 py-0.5 text-text3">
                  {t}
                </span>
              ))}
            </div>
          </div>
        ))}
      </div>

      {subagents.length === 0 && (
        <div className="text-text3 text-xs text-center py-8">暂无 SubAgent 配置</div>
      )}

      {/* Edit panel */}
      {editingIdx !== null && editDraft && (
        <div
          className="bg-bg2 rounded-lg p-3 text-xs space-y-2 border border-border"
          onClick={(e) => e.stopPropagation()}
        >
          <div className="grid grid-cols-2 gap-2">
            {/* Name */}
            <div>
              <label className="text-text3 block mb-0.5">名称</label>
              <input
                className="w-full bg-bg border border-border rounded px-2 py-1 text-text text-xs focus:border-accent focus:outline-none"
                value={editDraft.name}
                onChange={(e) => setEditDraft({ ...editDraft, name: e.target.value })}
              />
            </div>

            {/* Provider + Model two-level selector */}
            <div>
              <label className="text-text3 block mb-0.5">模型覆盖</label>
              <div className="flex gap-1">
                <select
                  className="flex-1 bg-bg border border-border rounded px-2 py-1 text-text text-xs focus:border-accent focus:outline-none"
                  value={selectedProvider}
                  onChange={(e) => pickProvider(e.target.value)}
                >
                  <option value="">继承主模型</option>
                  {providers.map((prov) => (
                    <option
                      key={prov.id}
                      value={prov.id}
                      disabled={!prov.has_key && prov.id !== 'ollama'}
                    >
                      {prov.name}
                    </option>
                  ))}
                </select>
                {selectedProvider && (
                  <select
                    className="flex-1 bg-bg border border-border rounded px-2 py-1 text-text text-xs focus:border-accent focus:outline-none"
                    value={selectedModel}
                    onChange={(e) => pickModel(e.target.value)}
                  >
                    {providerModels.map((m) => (
                      <option key={m.id} value={m.id}>
                        {m.name}
                      </option>
                    ))}
                  </select>
                )}
              </div>
            </div>
          </div>

          {/* Description */}
          <div>
            <label className="text-text3 block mb-0.5">描述</label>
            <textarea
              className="w-full bg-bg border border-border rounded px-2 py-1 text-text text-xs resize-none focus:border-accent focus:outline-none"
              rows={2}
              value={editDraft.description}
              onChange={(e) => setEditDraft({ ...editDraft, description: e.target.value })}
            />
          </div>

          {/* System prompt */}
          <div>
            <label className="text-text3 block mb-0.5">系统提示词</label>
            <textarea
              className="w-full bg-bg border border-border rounded px-2 py-1 text-text text-xs font-mono resize-none focus:border-accent focus:outline-none"
              rows={4}
              value={editDraft.system_prompt ?? ''}
              onChange={(e) => setEditDraft({ ...editDraft, system_prompt: e.target.value })}
            />
          </div>

          {/* Tool picker with checkbox grid + risk badges */}
          <div>
            <label className="text-text3 block mb-1">
              工具绑定 (不选则继承主 agent 全部工具)
            </label>
            <div className="grid grid-cols-2 lg:grid-cols-3 gap-1.5 max-h-48 overflow-y-auto">
              {availableTools.map((tool) => (
                <label
                  key={tool.name}
                  className="flex items-center gap-1.5 px-1.5 py-1 rounded hover:bg-bg cursor-pointer"
                >
                  <input
                    type="checkbox"
                    className="accent-accent"
                    checked={editDraft.tools.includes(tool.name)}
                    onChange={(e) => toggleTool(tool.name, e.target.checked)}
                  />
                  <span
                    className={cn(
                      'px-1 py-0.5 rounded text-[9px] leading-none',
                      RISK_BADGE_CLASSES[tool.risk_level] ?? 'bg-card text-text3',
                    )}
                  >
                    {tool.risk_level}
                  </span>
                  <span className="text-[11px] text-text truncate" title={tool.description}>
                    {tool.name}
                  </span>
                </label>
              ))}
            </div>
          </div>

          {/* Actions */}
          <div className="flex justify-between pt-1">
            <button
              className="px-2 py-1 rounded text-red hover:bg-red/10 transition-colors"
              onClick={() => handleDelete(editingIdx)}
            >
              删除
            </button>
            <div className="flex gap-2">
              <button
                className="px-2 py-1 rounded text-text3 hover:text-text hover:bg-card"
                onClick={() => {
                  setEditingIdx(null)
                  setEditDraft(null)
                }}
              >
                取消
              </button>
              <button
                className="px-2 py-1 rounded bg-accent-dim text-accent hover:opacity-80"
                onClick={handleSave}
              >
                保存
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

/* ── Memory ─────────────────────────────────────────── */

function MemorySection() {
  const qc = useQueryClient()
  const [draft, setDraft] = useState<string | null>(null)

  const { data } = useQuery({
    queryKey: ['admin-memory'],
    queryFn: () => client.get<{ memory: string }>('/api/agents/admin/memory').then((r) => r.data),
  })

  const saveMut = useMutation({
    mutationFn: (memory: string) => client.put('/api/agents/admin/memory', { memory }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['admin-memory'] })
      toast.success('记忆已保存')
      setDraft(null)
    },
    onError: () => toast.error('保存失败'),
  })

  const currentMemory = draft ?? data?.memory ?? ''

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-medium text-text">Agent 长期记忆</h3>
        <button
          className="px-2 py-1 text-xs rounded bg-accent-dim text-accent hover:opacity-80 disabled:opacity-50"
          disabled={draft === null || saveMut.isPending}
          onClick={() => draft !== null && saveMut.mutate(draft)}
        >
          保存
        </button>
      </div>
      <p className="text-xs text-text3">
        Agent 运行时长期记忆，由 MemoryMiddleware 加载到系统提示词中。
      </p>
      <textarea
        className="w-full h-80 bg-bg border border-border rounded p-3 text-xs text-text font-mono resize-none focus:border-accent focus:outline-none"
        value={currentMemory}
        onChange={(e) => setDraft(e.target.value)}
        placeholder="Agent 长期记忆..."
      />
    </div>
  )
}

/* ── RAG ────────────────────────────────────────────── */

interface RagStatus {
  enabled: boolean
  status: string
  document_count: number
  storage_mb: number
  sources: Record<string, number>
  embedding_model: string | null
  last_indexed: string | null
  error: string | null
}

const RAG_STATUS_CLASSES: Record<string, string> = {
  ready: 'bg-green/15 text-green',
  building: 'bg-yellow/15 text-yellow',
  error: 'bg-red/15 text-red',
}

const RAG_STATUS_LABELS: Record<string, string> = {
  ready: '正常',
  building: '构建中',
  error: '错误',
}

function RagSection() {
  const qc = useQueryClient()

  const { data: rag } = useQuery({
    queryKey: ['admin-rag'],
    queryFn: () => client.get<RagStatus>('/api/agents/admin/rag').then((r) => r.data),
  })

  const reindexMut = useMutation({
    mutationFn: () => client.post('/api/agents/admin/rag/reindex'),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['admin-rag'] })
      toast.success('重新索引已触发')
    },
    onError: () => toast.error('索引失败'),
  })

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <h3 className="text-sm font-medium text-text">RAG 知识库</h3>
          {rag && (
            <span
              className={cn(
                'px-1.5 py-0.5 rounded text-[10px] leading-none',
                RAG_STATUS_CLASSES[rag.status] ?? 'bg-card text-text3',
              )}
            >
              {RAG_STATUS_LABELS[rag.status] ?? rag.status}
            </span>
          )}
        </div>
        <button
          className="px-2 py-1 text-xs rounded bg-accent-dim text-accent hover:opacity-80 disabled:opacity-50"
          disabled={reindexMut.isPending}
          onClick={() => reindexMut.mutate()}
        >
          {reindexMut.isPending ? '重建中...' : '重建索引'}
        </button>
      </div>

      {rag ? (
        <div className="space-y-3 text-xs">
          {/* Error display */}
          {rag.error && (
            <div className="text-red text-xs">错误: {rag.error}</div>
          )}

          {/* Stats grid */}
          <div className="grid grid-cols-2 gap-3">
            <div className="bg-bg2 rounded-lg p-3">
              <div className="text-text3 text-[10px] mb-1">总文档数</div>
              <div className="text-lg font-semibold text-accent">
                {rag.document_count ?? 0}
              </div>
            </div>
            <div className="bg-bg2 rounded-lg p-3">
              <div className="text-text3 text-[10px] mb-1">存储大小</div>
              <div className="text-lg font-semibold text-accent">
                {(rag.storage_mb ?? 0).toFixed(1)} MB
              </div>
            </div>
          </div>

          {/* Sources breakdown */}
          {rag.sources && Object.keys(rag.sources).length > 0 && (
            <div>
              <div className="text-text3 text-[10px] mb-1">各数据源文档数</div>
              <div className="flex flex-wrap gap-1.5">
                {Object.entries(rag.sources).map(([src, cnt]) => (
                  <span
                    key={src}
                    className="bg-accent-dim text-accent px-1.5 py-0.5 rounded text-[10px]"
                  >
                    {src}: {cnt}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Metadata row */}
          <div className="text-[11px] text-text3 flex flex-wrap gap-3">
            {rag.embedding_model && <span>模型: {rag.embedding_model}</span>}
            {rag.last_indexed && (
              <span>
                上次索引:{' '}
                {new Date(rag.last_indexed).toLocaleString('zh-CN', { hour12: false })}
              </span>
            )}
          </div>
        </div>
      ) : (
        <div className="text-text3 text-xs text-center py-8">加载中...</div>
      )}
    </div>
  )
}
