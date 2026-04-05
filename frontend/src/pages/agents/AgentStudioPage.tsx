import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import client from '@/api/client'
import type { AgentRun, InstalledSkill } from '@/types/agent'
import { ensureArray, ensureRecord } from '@/lib/utils'
import TabErrorBoundary from '@/components/TabErrorBoundary'

interface DiscoveredSkill {
  path: string
  installed: boolean
  manifest: {
    name: string
    summary: string
  }
}

interface ToolInfo {
  name: string
}

interface SubagentItem {
  name: string
  description: string
  system_prompt: string
  tools: string[]
  model: string | null
  model_purpose: string
  middleware_profile: string
}

interface ApprovalItem {
  id: string
  description: string
  tool_name: string
  created_at: string
}

type StudioTab = 'overview' | 'skills' | 'install' | 'subagents' | 'memory' | 'runs' | 'async-tasks'

const TABS: Array<{ id: StudioTab; label: string }> = [
  { id: 'overview', label: 'Overview' },
  { id: 'skills', label: 'Skills' },
  { id: 'install', label: 'Install' },
  { id: 'subagents', label: 'SubAgents' },
  { id: 'memory', label: 'Memory & Prompts' },
  { id: 'runs', label: 'Runs & Approvals' },
  { id: 'async-tasks', label: 'Async Tasks' },
]

function TabButton({
  active,
  onClick,
  label,
}: {
  active: boolean
  onClick: () => void
  label: string
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={
        active
          ? 'rounded-lg bg-accent-dim px-3 py-2 text-sm text-accent'
          : 'rounded-lg px-3 py-2 text-sm text-text2 transition-colors hover:bg-bg2 hover:text-text'
      }
    >
      {label}
    </button>
  )
}

export default function AgentStudioPage() {
  const [tab, setTab] = useState<StudioTab>('overview')

  return (
    <div className="space-y-4">
      <div>
        <div className="text-2xl font-semibold text-text">Agent Studio</div>
        <p className="mt-1 text-sm text-text3">管理运行时、技能安装、提示词、子智能体和审批恢复。</p>
      </div>

      <div className="flex flex-wrap gap-2 rounded-xl border border-border bg-bg p-2">
        {TABS.map((item) => (
          <TabButton key={item.id} active={tab === item.id} onClick={() => setTab(item.id)} label={item.label} />
        ))}
      </div>

      {tab === 'overview' && (
        <TabErrorBoundary tabName="Overview">
          <OverviewTab />
        </TabErrorBoundary>
      )}
      {tab === 'skills' && (
        <TabErrorBoundary tabName="Skills">
          <SkillsTab />
        </TabErrorBoundary>
      )}
      {tab === 'install' && (
        <TabErrorBoundary tabName="Install">
          <InstallTab />
        </TabErrorBoundary>
      )}
      {tab === 'subagents' && (
        <TabErrorBoundary tabName="SubAgents">
          <SubagentsTab />
        </TabErrorBoundary>
      )}
      {tab === 'memory' && (
        <TabErrorBoundary tabName="Memory & Prompts">
          <MemoryAndPromptsTab />
        </TabErrorBoundary>
      )}
      {tab === 'runs' && (
        <TabErrorBoundary tabName="Runs & Approvals">
          <RunsAndApprovalsTab />
        </TabErrorBoundary>
      )}
      {tab === 'async-tasks' && (
        <TabErrorBoundary tabName="Async Tasks">
          <AsyncTasksTab />
        </TabErrorBoundary>
      )}
    </div>
  )
}

function OverviewTab() {
  const { data: skills } = useQuery({
    queryKey: ['studio-skills'],
    queryFn: () => client.get('/api/agents/admin/skills').then((r) => ensureArray<InstalledSkill>(ensureRecord(r.data).skills)),
  })
  const { data: runs } = useQuery({
    queryKey: ['agent-runs'],
    queryFn: () => client.get('/api/agents/runs').then((r) => ensureArray<AgentRun>(r.data)),
  })
  const { data: approvals } = useQuery({
    queryKey: ['agent-approvals'],
    queryFn: () => client.get('/api/agents/approvals').then((r) => ensureArray<ApprovalItem>(r.data)),
  })

  const enabledSkills = useMemo(() => skills?.filter((item) => item.enabled).length ?? 0, [skills])
  const failedRuns = useMemo(() => runs?.filter((item) => item.status === 'error').length ?? 0, [runs])
  const waitingApproval = approvals?.length ?? 0

  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
      <MetricCard title="启用技能" value={enabledSkills} subtitle={`${skills?.length ?? 0} 个已安装`} />
      <MetricCard title="失败运行" value={failedRuns} subtitle="最近运行状态" />
      <MetricCard title="待处理审批" value={waitingApproval} subtitle="危险操作需要人工确认" />
    </div>
  )
}

function MetricCard({ title, value, subtitle }: { title: string; value: number; subtitle: string }) {
  return (
    <div className="rounded-xl border border-border bg-bg2 p-4">
      <div className="text-xs text-text3">{title}</div>
      <div className="mt-2 text-3xl font-semibold text-text">{value}</div>
      <div className="mt-2 text-xs text-text3">{subtitle}</div>
    </div>
  )
}

function SkillsTab() {
  const qc = useQueryClient()
  const [selectedSkillId, setSelectedSkillId] = useState<string | null>(null)

  const { data: skills = [] } = useQuery({
    queryKey: ['studio-skills'],
    queryFn: () => client.get('/api/agents/admin/skills').then((r) => ensureArray<InstalledSkill>(ensureRecord(r.data).skills)),
  })

  const { data: skillDetail } = useQuery({
    queryKey: ['skill-detail', selectedSkillId],
    queryFn: () => client.get(`/api/agents/skills/${selectedSkillId}`).then((r) => r.data),
    enabled: !!selectedSkillId,
  })

  const toggleMut = useMutation({
    mutationFn: async (skill: InstalledSkill) => {
      const path = skill.enabled ? 'disable' : 'enable'
      await client.post(`/api/agents/admin/skills/${skill.id}/${path}`)
    },
    onSuccess: (_data, skill) => {
      qc.invalidateQueries({ queryKey: ['studio-skills'] })
      qc.invalidateQueries({ queryKey: ['skill-detail', skill.id] })
    },
  })

  const deleteMut = useMutation({
    mutationFn: async (skillId: string) => client.delete(`/api/agents/admin/skills/${skillId}`),
    onSuccess: (_data, skillId) => {
      qc.invalidateQueries({ queryKey: ['studio-skills'] })
      if (selectedSkillId === skillId) {
        setSelectedSkillId(null)
      }
    },
  })

  return (
    <div className="relative flex flex-col gap-4 lg:flex-row">
      <div className="flex-1 space-y-3">
        {skills.map((skill) => (
          <div
            key={skill.id}
            className={`rounded-xl border bg-bg p-4 transition-colors ${selectedSkillId === skill.id ? 'border-accent/50' : 'border-border'}`}
          >
            <div className="flex items-start justify-between gap-4">
              <div>
                <div className="text-sm font-medium text-text">{skill.name}</div>
                <div className="mt-1 text-xs text-text3">{skill.summary}</div>
                <div className="mt-2 text-xs text-text3">
                  {skill.id} · v{skill.version} · {skill.source_type}
                </div>
              </div>
              <div className="flex gap-2">
                <button
                  type="button"
                  onClick={() => setSelectedSkillId(selectedSkillId === skill.id ? null : skill.id)}
                  className="rounded-lg border border-border px-3 py-1.5 text-xs text-text transition-colors hover:border-accent/40"
                >
                  {selectedSkillId === skill.id ? '收起' : '详情'}
                </button>
                <button
                  type="button"
                  onClick={() => toggleMut.mutate(skill)}
                  className="rounded-lg border border-border px-3 py-1.5 text-xs text-text transition-colors hover:border-accent/40"
                >
                  {skill.enabled ? '禁用' : '启用'}
                </button>
                <button
                  type="button"
                  onClick={() => deleteMut.mutate(skill.id)}
                  className="rounded-lg border border-red/30 px-3 py-1.5 text-xs text-red transition-colors hover:bg-red/10"
                >
                  卸载
                </button>
              </div>
            </div>
          </div>
        ))}
        {skills.length === 0 && <EmptyState text="暂无已安装技能。到 Install 标签页扫描或上传 skill 包。" />}
      </div>

      {selectedSkillId && skillDetail && (
        <div className="w-full shrink-0 rounded-xl border border-border bg-bg p-5 lg:w-[420px]">
          <div className="mb-4 flex items-center justify-between">
            <h3 className="text-sm font-semibold text-text">{skillDetail.name}</h3>
            <button
              type="button"
              onClick={() => setSelectedSkillId(null)}
              className="text-text3 transition-colors hover:text-text"
            >
              &times;
            </button>
          </div>

          {skillDetail.summary && (
            <div className="mb-3 text-xs text-text2">{skillDetail.summary}</div>
          )}

          <div className="mb-3 flex flex-wrap gap-2 text-xs text-text3">
            <span>v{skillDetail.version}</span>
            <span>&middot;</span>
            <span>{skillDetail.source_type}</span>
            {skillDetail.enabled ? (
              <span className="rounded bg-green/10 px-1.5 py-0.5 text-green">已启用</span>
            ) : (
              <span className="rounded bg-red/10 px-1.5 py-0.5 text-red">已禁用</span>
            )}
          </div>

          {skillDetail.manifest?.required_tools?.length > 0 && (
            <div className="mb-3">
              <div className="mb-1 text-xs font-medium text-text3">工具</div>
              <div className="flex flex-wrap gap-1">
                {(skillDetail.manifest.required_tools as string[]).map((t: string) => (
                  <span key={t} className="rounded bg-bg2 px-2 py-0.5 text-xs text-text3">
                    {t}
                  </span>
                ))}
              </div>
            </div>
          )}

          {skillDetail.manifest?.triggers && Object.keys(skillDetail.manifest.triggers).length > 0 && (
            <div className="mb-3">
              <div className="mb-1 text-xs font-medium text-text3">触发条件</div>
              <pre className="max-h-24 overflow-y-auto whitespace-pre-wrap rounded-lg bg-bg2 p-2 text-xs text-text2">
                {JSON.stringify(skillDetail.manifest.triggers, null, 2)}
              </pre>
            </div>
          )}

          {skillDetail.manifest?.capabilities?.length > 0 && (
            <div className="mb-3">
              <div className="mb-1 text-xs font-medium text-text3">能力</div>
              <div className="flex flex-wrap gap-1">
                {(skillDetail.manifest.capabilities as string[]).map((c: string) => (
                  <span key={c} className="rounded bg-accent-dim px-2 py-0.5 text-xs text-accent">
                    {c}
                  </span>
                ))}
              </div>
            </div>
          )}

          {skillDetail.manifest?.entrypoints && (
            <div className="mb-3">
              <div className="mb-1 text-xs font-medium text-text3">入口</div>
              <div className="text-xs text-text2">
                类型: {(skillDetail.manifest.entrypoints as Record<string, string>).type ?? '未知'}
              </div>
            </div>
          )}

          {skillDetail.skill_markdown && (
            <div className="mb-3">
              <div className="mb-1 text-xs font-medium text-text3">SKILL.md</div>
              <pre className="max-h-60 overflow-y-auto whitespace-pre-wrap rounded-lg bg-bg2 p-3 text-xs text-text2">
                {skillDetail.skill_markdown}
              </pre>
            </div>
          )}

          <div className="text-xs text-text3">
            安装路径: <code className="text-text2">{skillDetail.install_path}</code>
          </div>
        </div>
      )}
    </div>
  )
}

function InstallTab() {
  const qc = useQueryClient()
  const [repoPath, setRepoPath] = useState('')
  const [sourceRootsDraft, setSourceRootsDraft] = useState('')

  const { data: sources } = useQuery({
    queryKey: ['skill-sources'],
    queryFn: () => client.get<{ roots: string[] }>('/api/agents/admin/skill-sources').then((r) => r.data),
  })

  const { data: discovered } = useQuery({
    queryKey: ['skill-discovery'],
    queryFn: () =>
      client.post('/api/agents/admin/skills/discover').then((r) => ensureArray(ensureRecord(r.data).items) as DiscoveredSkill[]),
  })

  const saveSourcesMut = useMutation({
    mutationFn: async (roots: string[]) => client.put('/api/agents/admin/skill-sources', { roots }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['skill-sources'] })
      qc.invalidateQueries({ queryKey: ['skill-discovery'] })
    },
  })

  const installRepoMut = useMutation({
    mutationFn: async (path: string) => client.post('/api/agents/admin/skills/install-from-repo', { repo_path: path }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['studio-skills'] })
      qc.invalidateQueries({ queryKey: ['skill-discovery'] })
      setRepoPath('')
    },
  })

  const uploadMut = useMutation({
    mutationFn: async (file: File) => {
      const form = new FormData()
      form.append('file', file)
      await client.post('/api/agents/admin/skills/install-upload', form, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['studio-skills'] })
      qc.invalidateQueries({ queryKey: ['skill-discovery'] })
    },
  })

  return (
    <div className="space-y-4">
      <section className="rounded-xl border border-border bg-bg p-4">
        <div className="text-sm font-medium text-text">Repo 路径安装</div>
        <div className="mt-3 flex gap-2">
          <input
            value={repoPath}
            onChange={(e) => setRepoPath(e.target.value)}
            placeholder="/path/to/skill"
            className="flex-1 rounded-lg border border-border bg-bg2 px-3 py-2 text-sm text-text"
          />
          <button
            type="button"
            onClick={() => repoPath && installRepoMut.mutate(repoPath)}
            className="rounded-lg bg-accent px-3 py-2 text-sm font-medium text-[#0f172a]"
          >
            安装
          </button>
        </div>
      </section>

      <section className="rounded-xl border border-border bg-bg p-4">
        <div className="text-sm font-medium text-text">管理扫描源</div>
        <textarea
          value={sourceRootsDraft || (sources?.roots ?? []).join('\n')}
          onChange={(e) => setSourceRootsDraft(e.target.value)}
          className="mt-3 h-28 w-full rounded-lg border border-border bg-bg2 px-3 py-2 text-sm text-text"
        />
        <button
          type="button"
          onClick={() =>
            saveSourcesMut.mutate(
              (sourceRootsDraft || (sources?.roots ?? []).join('\n'))
                .split('\n')
                .map((item) => item.trim())
                .filter(Boolean),
            )
          }
          className="mt-3 rounded-lg border border-border px-3 py-2 text-sm text-text"
        >
          保存扫描源
        </button>
      </section>

      <section className="rounded-xl border border-border bg-bg p-4">
        <div className="text-sm font-medium text-text">文件上传安装</div>
        <input
          type="file"
          accept=".zip,.tar,.tgz,.gz"
          className="mt-3 block text-sm text-text"
          onChange={(e) => {
            const file = e.target.files?.[0]
            if (file) uploadMut.mutate(file)
          }}
        />
      </section>

      <section className="rounded-xl border border-border bg-bg p-4">
        <div className="text-sm font-medium text-text">发现结果</div>
        <div className="mt-3 space-y-2">
          {(discovered ?? []).map((item) => (
            <div key={item.path} className="rounded-lg border border-border bg-bg2 p-3">
              <div className="flex items-start justify-between gap-4">
                <div>
                  <div className="text-sm font-medium text-text">{item.manifest.name}</div>
                  <div className="mt-1 text-xs text-text3">{item.manifest.summary}</div>
                  <div className="mt-1 text-xs text-text3">{item.path}</div>
                </div>
                <button
                  type="button"
                  disabled={item.installed}
                  onClick={() => installRepoMut.mutate(item.path)}
                  className="rounded-lg border border-border px-3 py-1.5 text-xs text-text disabled:opacity-50"
                >
                  {item.installed ? '已安装' : '从发现结果安装'}
                </button>
              </div>
            </div>
          ))}
        </div>
      </section>
    </div>
  )
}

const MW_PROFILE_STYLES: Record<string, { label: string; cls: string }> = {
  light: { label: 'Light', cls: 'bg-green/10 text-green' },
  heavy: { label: 'Heavy', cls: 'bg-orange/10 text-orange' },
  ops: { label: 'Ops', cls: 'bg-accent-dim text-accent' },
}

function SubagentsTab() {
  const qc = useQueryClient()
  const [editingSubagent, setEditingSubagent] = useState<string | null>(null)
  const [expandedPrompt, setExpandedPrompt] = useState<string | null>(null)
  const [editForm, setEditForm] = useState({
    description: '',
    system_prompt: '',
    tools: [] as string[],
    model: '' as string | null,
    model_purpose: 'chat',
    middleware_profile: 'light',
  })

  const { data } = useQuery({
    queryKey: ['admin-subagents'],
    queryFn: () =>
      client.get('/api/agents/admin/subagents').then((r) => {
        const raw = ensureRecord(r.data)
        return {
          ...raw,
          subagents: ensureArray(raw.subagents) as SubagentItem[],
          available_tools: ensureArray(raw.available_tools) as ToolInfo[],
        }
      }),
  })

  const availableToolNames = useMemo(
    () => (data?.available_tools ?? []).map((t: ToolInfo) => String(t?.name ?? '')).filter(Boolean),
    [data?.available_tools],
  )

  const saveMut = useMutation({
    mutationFn: async () => {
      const currentSubagents = data?.subagents ?? []
      const updated = currentSubagents.map((s: SubagentItem) =>
        s.name === editingSubagent ? { ...s, ...editForm } : s,
      )
      await client.put('/api/agents/admin/subagents', { subagents: updated })
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['admin-subagents'] })
      setEditingSubagent(null)
    },
  })

  const startEditing = (item: SubagentItem) => {
    const name = String(item.name ?? '')
    setEditForm({
      description: String(item.description ?? ''),
      system_prompt: String(item.system_prompt ?? ''),
      tools: Array.isArray(item.tools) ? item.tools : [],
      model: item.model ? String(item.model) : null,
      model_purpose: String(item.model_purpose ?? 'chat'),
      middleware_profile: String(item.middleware_profile ?? 'light'),
    })
    setEditingSubagent(name)
  }

  return (
    <div className="space-y-3">
      {(data?.subagents ?? []).map((item: SubagentItem) => {
        const name = String(item.name ?? '')
        const tools = Array.isArray(item.tools) ? item.tools : []
        const mwProfile = String(item.middleware_profile ?? '')
        const mwStyle = MW_PROFILE_STYLES[mwProfile]
        const isEditing = editingSubagent === name

        return (
          <div key={name} className="rounded-xl border border-border bg-bg p-4">
            <div className="flex items-start justify-between gap-4">
              <div className="flex-1">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-medium text-text">{name}</span>
                  {mwStyle && (
                    <span className={`rounded px-1.5 py-0.5 text-xs ${mwStyle.cls}`}>{mwStyle.label}</span>
                  )}
                  <span className="text-xs text-text3">
                    {tools.length} 个工具
                  </span>
                </div>
                <div className="mt-1 text-xs text-text3">{String(item.description ?? '')}</div>
                <div className="mt-2 flex flex-wrap gap-1">
                  {tools.slice(0, 6).map((t) => (
                    <span key={t} className="rounded bg-bg2 px-1.5 py-0.5 text-xs text-text3">{t}</span>
                  ))}
                  {tools.length > 6 && (
                    <span className="text-xs text-text3">+{tools.length - 6}</span>
                  )}
                </div>
                <div className="mt-1 text-xs text-text3">
                  模型: {String(item.model ?? item.model_purpose ?? '默认')}
                </div>

                {/* system_prompt preview */}
                {item.system_prompt && !isEditing && (
                  <div className="mt-2">
                    <button
                      type="button"
                      onClick={() => setExpandedPrompt(expandedPrompt === name ? null : name)}
                      className="text-xs text-accent hover:underline"
                    >
                      {expandedPrompt === name ? '收起 Prompt' : '展开 Prompt'}
                    </button>
                    {expandedPrompt === name && (
                      <pre className="mt-1 max-h-40 overflow-y-auto whitespace-pre-wrap rounded-lg bg-bg2 p-2 text-xs text-text2">
                        {String(item.system_prompt)}
                      </pre>
                    )}
                  </div>
                )}
              </div>
              <button
                type="button"
                onClick={() => (isEditing ? setEditingSubagent(null) : startEditing(item))}
                className="rounded-lg border border-border px-3 py-1.5 text-xs text-text transition-colors hover:border-accent/40"
              >
                {isEditing ? '取消' : '编辑'}
              </button>
            </div>

            {isEditing && (
              <div className="mt-3 space-y-3 border-t border-border pt-3">
                <div>
                  <label className="text-xs text-text3">描述</label>
                  <input
                    value={editForm.description}
                    onChange={(e) => setEditForm((p) => ({ ...p, description: e.target.value }))}
                    className="mt-1 w-full rounded-lg border border-border bg-bg2 px-3 py-2 text-sm text-text"
                  />
                </div>
                <div>
                  <label className="text-xs text-text3">系统 Prompt</label>
                  <textarea
                    value={editForm.system_prompt}
                    onChange={(e) => setEditForm((p) => ({ ...p, system_prompt: e.target.value }))}
                    rows={6}
                    className="mt-1 h-40 w-full rounded-lg border border-border bg-bg2 px-3 py-2 font-mono text-sm text-text"
                  />
                </div>
                <div>
                  <label className="text-xs text-text3">模型覆盖</label>
                  <input
                    value={editForm.model ?? ''}
                    onChange={(e) => setEditForm((p) => ({ ...p, model: e.target.value || null }))}
                    placeholder="留空则按模型用途自动选择"
                    className="mt-1 w-full rounded-lg border border-border bg-bg2 px-3 py-2 text-sm text-text"
                  />
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="text-xs text-text3">模型用途</label>
                    <select
                      value={editForm.model_purpose}
                      onChange={(e) => setEditForm((p) => ({ ...p, model_purpose: e.target.value }))}
                      className="mt-1 w-full rounded-lg border border-border bg-bg2 px-3 py-2 text-sm text-text"
                    >
                      <option value="chat">Chat (默认模型)</option>
                      <option value="patrol">Patrol (巡检模型)</option>
                    </select>
                  </div>
                  <div>
                    <label className="text-xs text-text3">Middleware</label>
                    <select
                      value={editForm.middleware_profile}
                      onChange={(e) => setEditForm((p) => ({ ...p, middleware_profile: e.target.value }))}
                      className="mt-1 w-full rounded-lg border border-border bg-bg2 px-3 py-2 text-sm text-text"
                    >
                      <option value="light">Light (快速任务)</option>
                      <option value="heavy">Heavy (复杂分析)</option>
                      <option value="ops">Ops (运维操作)</option>
                    </select>
                  </div>
                </div>
                <div>
                  <label className="text-xs text-text3">工具 ({editForm.tools.length} 个已选)</label>
                  <div className="mt-1 max-h-48 space-y-1 overflow-y-auto rounded-lg border border-border bg-bg2 p-2">
                    {availableToolNames.map((tool: string) => (
                      <label key={tool} className="flex items-center gap-2 text-xs text-text2">
                        <input
                          type="checkbox"
                          checked={editForm.tools.includes(tool)}
                          onChange={(e) => {
                            setEditForm((p) => ({
                              ...p,
                              tools: e.target.checked
                                ? [...p.tools, tool]
                                : p.tools.filter((t) => t !== tool),
                            }))
                          }}
                          className="accent-accent"
                        />
                        {tool}
                      </label>
                    ))}
                  </div>
                </div>
                <div className="flex gap-2 pt-1">
                  <button
                    type="button"
                    onClick={() => saveMut.mutate()}
                    disabled={saveMut.isPending}
                    className="rounded-lg bg-accent px-4 py-1.5 text-xs font-medium text-[#0f172a] transition-colors hover:bg-accent/90 disabled:opacity-50"
                  >
                    {saveMut.isPending ? '保存中...' : '保存'}
                  </button>
                  <button
                    type="button"
                    onClick={() => setEditingSubagent(null)}
                    className="rounded-lg border border-border px-4 py-1.5 text-xs text-text transition-colors hover:bg-bg2"
                  >
                    取消
                  </button>
                </div>
              </div>
            )}
          </div>
        )
      })}
      {!(data?.subagents ?? []).length && <EmptyState text="暂无子智能体配置。" />}
    </div>
  )
}

function MemoryAndPromptsTab() {
  const qc = useQueryClient()
  const [promptDraft, setPromptDraft] = useState('')
  const [memoryDraft, setMemoryDraft] = useState('')

  const { data: prompt } = useQuery({
    queryKey: ['admin-prompt'],
    queryFn: () => client.get('/api/agents/admin/prompt').then((r) => r.data),
  })
  const { data: memory } = useQuery({
    queryKey: ['admin-memory'],
    queryFn: () => client.get('/api/agents/admin/memory').then((r) => r.data),
  })
  const { data: ragData, refetch: refetchRag } = useQuery({
    queryKey: ['rag-stats'],
    queryFn: () => client.get('/api/agents/admin/rag').then((r) => r.data as { ok: boolean; stats: Record<string, unknown> }),
    staleTime: 60_000,
  })

  const savePromptMut = useMutation({
    mutationFn: async (content: string) => client.put('/api/agents/admin/prompt', { content }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['admin-prompt'] }),
  })
  const resetPromptMut = useMutation({
    mutationFn: async () => client.put('/api/agents/admin/prompt', { prompt: null }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['admin-prompt'] }),
  })
  const saveMemoryMut = useMutation({
    mutationFn: async (content: string) => client.put('/api/agents/admin/memory', { content }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['admin-memory'] }),
  })
  const reindexMut = useMutation({
    mutationFn: () => client.post('/api/agents/admin/rag/reindex'),
    onSuccess: () => { toast.success('RAG 索引重建完成'); refetchRag() },
    onError: () => toast.error('重建失败'),
  })

  const currentPrompt = promptDraft || prompt?.content || ''
  const currentMemory = memoryDraft || memory?.content || ''

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
        <section className="rounded-xl border border-border bg-bg p-4">
          <div className="flex items-center justify-between">
            <div className="text-sm font-medium text-text">系统 Prompt</div>
            <div className="flex gap-2">
              <button
                type="button"
                onClick={() => resetPromptMut.mutate()}
                className="rounded-lg border border-border px-3 py-1.5 text-xs text-text"
              >
                恢复默认
              </button>
              <button
                type="button"
                onClick={() => savePromptMut.mutate(currentPrompt)}
                className="rounded-lg bg-accent px-3 py-1.5 text-xs font-medium text-[#0f172a]"
              >
                保存
              </button>
            </div>
          </div>
          <textarea
            value={currentPrompt}
            onChange={(e) => setPromptDraft(e.target.value)}
            className="mt-3 h-80 w-full rounded-lg border border-border bg-bg2 px-3 py-2 font-mono text-sm text-text"
          />
        </section>

        <section className="rounded-xl border border-border bg-bg p-4">
          <div className="flex items-center justify-between">
            <div className="text-sm font-medium text-text">长期记忆</div>
            <button
              type="button"
              onClick={() => saveMemoryMut.mutate(currentMemory)}
              className="rounded-lg bg-accent px-3 py-1.5 text-xs font-medium text-[#0f172a]"
            >
              保存
            </button>
          </div>
          <textarea
            value={currentMemory}
            onChange={(e) => setMemoryDraft(e.target.value)}
            className="mt-3 h-80 w-full rounded-lg border border-border bg-bg2 px-3 py-2 font-mono text-sm text-text"
          />
        </section>
      </div>

      <section className="rounded-xl border border-border bg-bg p-4">
        <div className="flex items-center justify-between">
          <div className="text-sm font-medium text-text">RAG 知识库</div>
          <button
            type="button"
            onClick={() => reindexMut.mutate()}
            disabled={reindexMut.isPending}
            className="rounded-lg border border-border px-3 py-1.5 text-xs text-text transition-colors hover:border-accent/40 disabled:opacity-50"
          >
            {reindexMut.isPending ? '重建中...' : '重建索引'}
          </button>
        </div>
        {ragData?.ok && ragData.stats ? (
          <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-4">
            {Object.entries(ragData.stats).map(([k, v]) => (
              <div key={k} className="rounded-lg bg-bg2 px-3 py-2 text-xs">
                <div className="text-text3 capitalize">{k.replace(/_/g, ' ')}</div>
                <div className="mt-1 font-mono text-text">{String(v)}</div>
              </div>
            ))}
          </div>
        ) : (
          <div className="mt-3 text-xs text-text3">
            {ragData?.ok === false ? '不可用' : '加载中...'}
          </div>
        )}
      </section>
    </div>
  )
}

interface AgentEvent {
  id: number
  timestamp: string
  event_type: string
  tool_name: string | null
  tool_input: string | null
  risk_level: string | null
  username: string | null
  details: string | null
}

function RunsAndApprovalsTab() {
  const qc = useQueryClient()

  const { data: runs = [] } = useQuery({
    queryKey: ['agent-runs'],
    queryFn: () => client.get('/api/agents/runs').then((r) => ensureArray<AgentRun>(r.data)),
    refetchInterval: 10_000,
  })
  const { data: approvals = [] } = useQuery({
    queryKey: ['agent-approvals'],
    queryFn: () => client.get('/api/agents/approvals').then((r) => ensureArray<ApprovalItem>(r.data)),
    refetchInterval: 10_000,
  })
  const { data: events = [] } = useQuery({
    queryKey: ['agent-events'],
    queryFn: () =>
      client.get('/api/agents/events', { params: { limit: 30 } }).then((r) => ensureArray<AgentEvent>(r.data)),
    refetchInterval: 20_000,
  })

  const [cancellingId, setCancellingId] = useState<string | null>(null)

  const cancelRunMut = useMutation({
    mutationFn: async (runId: string) => {
      setCancellingId(runId)
      return client.post(`/api/agents/runs/${runId}/cancel`)
    },
    onSuccess: () => {
      setCancellingId(null)
      qc.invalidateQueries({ queryKey: ['agent-runs'] })
    },
    onError: () => {
      setCancellingId(null)
    },
  })

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
        <section className="rounded-xl border border-border bg-bg p-4">
          <div className="text-sm font-medium text-text">最近运行</div>
          <div className="mt-3 space-y-2">
            {runs.map((run) => (
              <div key={run.id} className="rounded-lg border border-border bg-bg2 p-3">
                <div className="flex items-center justify-between gap-4">
                  <div className="min-w-0 flex-1 truncate text-sm text-text">{run.user_message}</div>
                  <div className="flex shrink-0 items-center gap-2">
                    <span className="text-xs text-text3">{run.status}</span>
                    {(run.status === 'running' || run.status === 'pending') && (
                      <button
                        onClick={() => cancelRunMut.mutate(run.id)}
                        disabled={cancellingId === run.id}
                        className="rounded px-2 py-0.5 text-xs text-red-400 hover:bg-red-500/10 disabled:opacity-50"
                      >
                        取消
                      </button>
                    )}
                  </div>
                </div>
                <div className="mt-1 text-xs text-text3">
                  {run.page_context || '无页面上下文'} · {run.skill_id || '未选技能'}
                </div>
              </div>
            ))}
            {runs.length === 0 && <EmptyState text="暂无运行记录。" />}
          </div>
        </section>

        <section className="rounded-xl border border-border bg-bg p-4">
          <div className="text-sm font-medium text-text">待处理审批</div>
          <div className="mt-3 space-y-2">
            {approvals.map((item: ApprovalItem) => (
              <div key={item.id} className="rounded-lg border border-border bg-bg2 p-3">
                <div className="text-sm text-text">{item.description || item.tool_name}</div>
                <div className="mt-1 text-xs text-text3">{item.created_at}</div>
              </div>
            ))}
            {approvals.length === 0 && <EmptyState text="当前没有待处理审批。" />}
          </div>
        </section>
      </div>

      <section className="rounded-xl border border-border bg-bg p-4">
        <div className="text-sm font-medium text-text">Agent 事件日志</div>
        <div className="mt-3 overflow-x-auto">
          <table className="w-full text-xs text-text3">
            <thead>
              <tr className="border-b border-border text-left">
                <th className="pb-2 pr-3 font-medium">时间</th>
                <th className="pb-2 pr-3 font-medium">类型</th>
                <th className="pb-2 pr-3 font-medium">工具</th>
                <th className="pb-2 pr-3 font-medium">风险</th>
                <th className="pb-2 pr-3 font-medium">用户</th>
                <th className="pb-2 font-medium">详情</th>
              </tr>
            </thead>
            <tbody>
              {events.map((ev) => (
                <tr key={ev.id} className="border-b border-border/50 last:border-0">
                  <td className="py-1.5 pr-3 tabular-nums">{ev.timestamp.slice(0, 19).replace('T', ' ')}</td>
                  <td className="py-1.5 pr-3">{ev.event_type}</td>
                  <td className="py-1.5 pr-3">{ev.tool_name ?? '—'}</td>
                  <td className="py-1.5 pr-3">
                    {ev.risk_level ? (
                      <span
                        className={
                          ev.risk_level === 'high'
                            ? 'text-red-400'
                            : ev.risk_level === 'medium'
                              ? 'text-yellow-400'
                              : 'text-text3'
                        }
                      >
                        {ev.risk_level}
                      </span>
                    ) : (
                      '—'
                    )}
                  </td>
                  <td className="py-1.5 pr-3">{ev.username ?? '—'}</td>
                  <td className="max-w-xs truncate py-1.5">{ev.details ?? '—'}</td>
                </tr>
              ))}
              {events.length === 0 && (
                <tr>
                  <td colSpan={6} className="py-4 text-center text-text3">
                    暂无事件记录。
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  )
}

interface AsyncTask {
  id: string
  task_type: string
  instruction: string
  status: 'pending' | 'running' | 'done' | 'failed' | 'cancelled'
  created_at: string
  completed_at: string | null
  result?: string
}

const ASYNC_TASK_STATUS_STYLES: Record<string, string> = {
  pending: 'bg-yellow/10 text-yellow',
  running: 'bg-accent/10 text-accent',
  done: 'bg-green/10 text-green',
  failed: 'bg-red/10 text-red',
  cancelled: 'bg-text3/10 text-text3',
}

function AsyncTasksTab() {
  const qc = useQueryClient()
  const [selectedId, setSelectedId] = useState<string | null>(null)

  const { data: tasks = [], isFetching } = useQuery({
    queryKey: ['async-tasks'],
    queryFn: () => client.get('/api/agents/async-tasks').then((r) => ensureArray<AsyncTask>(r.data)),
    refetchInterval: 10_000,
  })

  const { data: detail } = useQuery({
    queryKey: ['async-task-detail', selectedId],
    queryFn: () => client.get(`/api/agents/async-tasks/${selectedId}`).then((r) => r.data as AsyncTask),
    enabled: !!selectedId,
    refetchInterval: selectedId ? 5_000 : false,
  })

  const cancelMut = useMutation({
    mutationFn: (id: string) => client.delete(`/api/agents/async-tasks/${id}`),
    onSuccess: () => {
      toast.success('任务已取消')
      qc.invalidateQueries({ queryKey: ['async-tasks'] })
      qc.invalidateQueries({ queryKey: ['async-task-detail', selectedId] })
    },
    onError: () => toast.error('取消失败'),
  })

  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
      <section className="rounded-xl border border-border bg-bg p-4">
        <div className="mb-3 flex items-center justify-between">
          <div className="text-sm font-medium text-text">后台异步任务</div>
          {isFetching && <div className="animate-pulse text-[10px] text-text3">刷新中...</div>}
        </div>
        <div className="space-y-2">
          {tasks.map((t) => (
            <div
              key={t.id}
              onClick={() => setSelectedId(t.id === selectedId ? null : t.id)}
              className={`cursor-pointer rounded-lg border p-3 transition-colors ${
                selectedId === t.id ? 'border-accent/50 bg-bg2' : 'border-border hover:bg-bg2'
              }`}
            >
              <div className="flex items-center justify-between gap-2">
                <span
                  className={`rounded px-1.5 py-0.5 text-[10px] font-medium ${
                    ASYNC_TASK_STATUS_STYLES[t.status] ?? 'bg-text3/10 text-text3'
                  }`}
                >
                  {t.status}
                </span>
                <span className="font-mono text-[10px] text-text3">{t.task_type}</span>
              </div>
              <div className="mt-1 truncate text-xs text-text2" title={t.instruction}>
                {t.instruction}
              </div>
              <div className="mt-1 text-[10px] text-text3">{t.created_at}</div>
            </div>
          ))}
          {tasks.length === 0 && <EmptyState text="暂无异步任务。" />}
        </div>
      </section>

      <section className="rounded-xl border border-border bg-bg p-4">
        <div className="mb-3 text-sm font-medium text-text">任务详情</div>
        {detail ? (
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <span
                className={`rounded px-2 py-0.5 text-xs font-medium ${
                  ASYNC_TASK_STATUS_STYLES[detail.status] ?? ''
                }`}
              >
                {detail.status}
              </span>
              {(detail.status === 'pending' || detail.status === 'running') && (
                <button
                  type="button"
                  onClick={() => cancelMut.mutate(detail.id)}
                  disabled={cancelMut.isPending}
                  className="rounded bg-red/10 px-2 py-1 text-xs text-red transition-colors hover:bg-red/20 disabled:opacity-50"
                >
                  取消任务
                </button>
              )}
            </div>
            <div className="space-y-1 text-xs text-text3">
              <div>
                <span className="text-text2">类型:</span> {detail.task_type}
              </div>
              <div>
                <span className="text-text2">创建:</span> {detail.created_at}
              </div>
              {detail.completed_at && (
                <div>
                  <span className="text-text2">完成:</span> {detail.completed_at}
                </div>
              )}
            </div>
            <div>
              <div className="mb-1 text-xs text-text3">指令</div>
              <pre className="whitespace-pre-wrap break-all rounded bg-bg2 p-2 font-mono text-xs text-text2">
                {detail.instruction}
              </pre>
            </div>
            {detail.result && (
              <div>
                <div className="mb-1 text-xs text-text3">结果</div>
                <pre className="max-h-60 overflow-y-auto whitespace-pre-wrap break-all rounded bg-bg2 p-2 font-mono text-xs text-text2">
                  {detail.result}
                </pre>
              </div>
            )}
          </div>
        ) : (
          <EmptyState text="点击左侧任务查看详情。" />
        )}
      </section>
    </div>
  )
}

function EmptyState({ text }: { text: string }) {
  return <div className="rounded-xl border border-dashed border-border bg-bg p-6 text-sm text-text3">{text}</div>
}
