import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import client from '@/api/client'
import type { AgentRun, InstalledSkill } from '@/types/agent'

type StudioTab = 'overview' | 'skills' | 'install' | 'subagents' | 'memory' | 'runs'

const TABS: Array<{ id: StudioTab; label: string }> = [
  { id: 'overview', label: 'Overview' },
  { id: 'skills', label: 'Skills' },
  { id: 'install', label: 'Install' },
  { id: 'subagents', label: 'SubAgents' },
  { id: 'memory', label: 'Memory & Prompts' },
  { id: 'runs', label: 'Runs & Approvals' },
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

      {tab === 'overview' && <OverviewTab />}
      {tab === 'skills' && <SkillsTab />}
      {tab === 'install' && <InstallTab />}
      {tab === 'subagents' && <SubagentsTab />}
      {tab === 'memory' && <MemoryAndPromptsTab />}
      {tab === 'runs' && <RunsAndApprovalsTab />}
    </div>
  )
}

function OverviewTab() {
  const { data: skills } = useQuery({
    queryKey: ['studio-skills'],
    queryFn: () => client.get<{ skills: InstalledSkill[] }>('/api/agents/admin/skills').then((r) => r.data.skills),
  })
  const { data: runs } = useQuery({
    queryKey: ['agent-runs'],
    queryFn: () => client.get<AgentRun[]>('/api/agents/runs').then((r) => r.data),
  })
  const { data: approvals } = useQuery({
    queryKey: ['agent-approvals'],
    queryFn: () => client.get('/api/agents/approvals').then((r) => r.data),
  })

  const enabledSkills = useMemo(() => skills?.filter((item) => item.enabled).length ?? 0, [skills])
  const failedRuns = useMemo(() => runs?.filter((item) => item.status === 'error').length ?? 0, [runs])
  const waitingApproval = Array.isArray(approvals) ? approvals.length : 0

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
  const { data: skills = [] } = useQuery({
    queryKey: ['studio-skills'],
    queryFn: () => client.get<{ skills: InstalledSkill[] }>('/api/agents/admin/skills').then((r) => r.data.skills),
  })

  const toggleMut = useMutation({
    mutationFn: async (skill: InstalledSkill) => {
      const path = skill.enabled ? 'disable' : 'enable'
      await client.post(`/api/agents/admin/skills/${skill.id}/${path}`)
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['studio-skills'] }),
  })

  const deleteMut = useMutation({
    mutationFn: async (skillId: string) => client.delete(`/api/agents/admin/skills/${skillId}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['studio-skills'] }),
  })

  return (
    <div className="space-y-3">
      {skills.map((skill) => (
        <div key={skill.id} className="rounded-xl border border-border bg-bg p-4">
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
    queryFn: () => client.post('/api/agents/admin/skills/discover').then((r) => r.data.items),
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
          {(discovered ?? []).map((item: any) => (
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

function SubagentsTab() {
  const { data } = useQuery({
    queryKey: ['admin-subagents'],
    queryFn: () => client.get('/api/agents/admin/subagents').then((r) => r.data),
  })

  return (
    <div className="space-y-3">
      {(data?.subagents ?? []).map((item: any) => (
        <div key={item.name} className="rounded-xl border border-border bg-bg p-4">
          <div className="text-sm font-medium text-text">{item.name}</div>
          <div className="mt-1 text-xs text-text3">{item.description}</div>
          <div className="mt-2 text-xs text-text3">工具: {(item.tools ?? []).join(', ') || '无'}</div>
          <div className="mt-1 text-xs text-text3">模型: {item.model ?? item.model_purpose ?? '默认'}</div>
        </div>
      ))}
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

  const currentPrompt = promptDraft || prompt?.content || ''
  const currentMemory = memoryDraft || memory?.content || ''

  return (
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
  )
}

function RunsAndApprovalsTab() {
  const { data: runs = [] } = useQuery({
    queryKey: ['agent-runs'],
    queryFn: () => client.get<AgentRun[]>('/api/agents/runs').then((r) => r.data),
  })
  const { data: approvals = [] } = useQuery({
    queryKey: ['agent-approvals'],
    queryFn: () => client.get('/api/agents/approvals').then((r) => r.data),
  })

  return (
    <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
      <section className="rounded-xl border border-border bg-bg p-4">
        <div className="text-sm font-medium text-text">最近运行</div>
        <div className="mt-3 space-y-2">
          {runs.map((run) => (
            <div key={run.id} className="rounded-lg border border-border bg-bg2 p-3">
              <div className="flex items-center justify-between gap-4">
                <div className="text-sm text-text">{run.user_message}</div>
                <div className="text-xs text-text3">{run.status}</div>
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
          {approvals.map((item: any) => (
            <div key={item.id} className="rounded-lg border border-border bg-bg2 p-3">
              <div className="text-sm text-text">{item.description || item.tool_name}</div>
              <div className="mt-1 text-xs text-text3">{item.created_at}</div>
            </div>
          ))}
          {approvals.length === 0 && <EmptyState text="当前没有待处理审批。" />}
        </div>
      </section>
    </div>
  )
}

function EmptyState({ text }: { text: string }) {
  return <div className="rounded-xl border border-dashed border-border bg-bg p-6 text-sm text-text3">{text}</div>
}
