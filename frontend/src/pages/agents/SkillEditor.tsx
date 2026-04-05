/**
 * SkillEditor - Left/right split editor for skill metadata + SKILL.md content.
 * Left: metadata form. Right: SKILL.md textarea.
 * Bottom: attached files list + eval panel.
 */

import { useState, useEffect, useCallback } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import {
  getSkill,
  createSkill,
  updateSkill,
  listSkillFiles,
  uploadSkillFile,
  deleteSkillFile,
  type SkillMeta,
  type SkillFile,
  type SkillCreate,
} from '@/api/skills'
import { SkillEvalPanel } from './SkillEvalPanel'

interface SkillEditorProps {
  /** null = create mode */
  skillId: string | null
  onClose: () => void
  onSaved: () => void
}

interface FormState {
  name: string
  description: string
  owner: string
  allowed_tools: string
  allowed_roles: string
  page_contexts: string
  capabilities: string
  compose: string
  skill_markdown: string
}

const EMPTY_FORM: FormState = {
  name: '',
  description: '',
  owner: 'shared',
  allowed_tools: '',
  allowed_roles: 'admin user',
  page_contexts: '',
  capabilities: '',
  compose: '',
  skill_markdown: '',
}

function skillToForm(skill: SkillMeta): FormState {
  return {
    name: skill.name,
    description: skill.description,
    owner: skill.owner ?? 'shared',
    allowed_tools: skill.allowed_tools?.join(' ') ?? '',
    allowed_roles: skill.allowed_roles?.join(' ') ?? 'admin user',
    page_contexts: skill.page_contexts?.join(' ') ?? '',
    capabilities: skill.capabilities?.join(' ') ?? '',
    compose: skill.compose?.join(' ') ?? '',
    skill_markdown: skill.skill_markdown ?? '',
  }
}

/** Build SKILL.md frontmatter from form state. */
function buildFrontmatter(form: FormState): string {
  const lines = ['---']
  lines.push(`name: ${form.name}`)
  lines.push(`description: >`)
  lines.push(`  ${form.description}`)
  if (form.allowed_tools.trim()) {
    lines.push(`allowed-tools: ${form.allowed_tools.trim()}`)
  }
  lines.push('metadata:')
  lines.push(`  version: "0.1.0"`)
  if (form.allowed_roles.trim()) {
    lines.push(`  allowed-roles: ${form.allowed_roles.trim()}`)
  }
  if (form.page_contexts.trim()) {
    lines.push(`  page-contexts: ${form.page_contexts.trim()}`)
  }
  if (form.capabilities.trim()) {
    lines.push(`  capabilities: ${form.capabilities.trim()}`)
  }
  if (form.compose.trim()) {
    lines.push(`  compose: ${form.compose.trim()}`)
  }
  lines.push(`  owner: ${form.owner}`)
  lines.push('---')
  return lines.join('\n')
}

export function SkillEditor({ skillId, onClose, onSaved }: SkillEditorProps) {
  const qc = useQueryClient()
  const isCreate = skillId === null
  const [form, setForm] = useState<FormState>(EMPTY_FORM)
  const [showEval, setShowEval] = useState(false)

  // Load existing skill data
  const { data: skill } = useQuery({
    queryKey: ['skill-edit', skillId],
    queryFn: () => getSkill(skillId!, true),
    enabled: !isCreate,
  })

  // Load attached files
  const { data: files = [], refetch: refetchFiles } = useQuery({
    queryKey: ['skill-files', skillId],
    queryFn: () => listSkillFiles(skillId!),
    enabled: !isCreate,
  })

  // Populate form when skill data arrives
  useEffect(() => {
    if (skill) setForm(skillToForm(skill))
  }, [skill])

  const setField = useCallback(
    <K extends keyof FormState>(key: K, value: FormState[K]) => {
      setForm((prev) => ({ ...prev, [key]: value }))
    },
    [],
  )

  // Sync form changes to SKILL.md frontmatter
  const syncFrontmatter = useCallback(() => {
    setForm((prev) => {
      const fm = buildFrontmatter(prev)
      // Preserve body content after frontmatter
      const bodyMatch = prev.skill_markdown.match(/^---[\s\S]*?---\n?([\s\S]*)$/)
      const body = bodyMatch?.[1] ?? prev.skill_markdown
      return { ...prev, skill_markdown: fm + '\n' + body }
    })
  }, [])

  // Save mutation
  const saveMut = useMutation({
    mutationFn: async () => {
      const payload = {
        name: form.name,
        description: form.description,
        owner: form.owner,
        allowed_tools: form.allowed_tools.split(/\s+/).filter(Boolean),
        allowed_roles: form.allowed_roles.split(/\s+/).filter(Boolean),
        page_contexts: form.page_contexts.split(/\s+/).filter(Boolean),
        capabilities: form.capabilities.split(/\s+/).filter(Boolean),
        compose: form.compose.split(/\s+/).filter(Boolean),
        skill_markdown: form.skill_markdown,
      }
      if (isCreate) {
        await createSkill(payload as SkillCreate)
      } else {
        await updateSkill(skillId!, payload)
      }
    },
    onSuccess: () => {
      toast.success(isCreate ? '技能已创建' : '技能已保存')
      onSaved()
    },
    onError: () => toast.error('保存失败'),
  })

  // File upload
  const uploadMut = useMutation({
    mutationFn: async ({ path, content }: { path: string; content: string }) => {
      await uploadSkillFile(skillId!, path, content)
    },
    onSuccess: () => {
      refetchFiles()
      toast.success('文件已上传')
    },
    onError: () => toast.error('上传失败'),
  })

  const deleteFileMut = useMutation({
    mutationFn: async (path: string) => {
      await deleteSkillFile(skillId!, path)
    },
    onSuccess: () => {
      refetchFiles()
      toast.success('文件已删除')
    },
    onError: () => toast.error('删除失败'),
  })

  const handleFileUpload = () => {
    const path = window.prompt('输入文件路径 (例如 references/guide.md):')
    if (!path) return
    const content = window.prompt('输入文件内容:')
    if (content === null) return
    uploadMut.mutate({ path, content })
  }

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-border px-4 py-2 shrink-0">
        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={onClose}
            className="text-text3 hover:text-text text-sm transition-colors"
          >
            &larr; 返回
          </button>
          <span className="text-sm font-medium text-text">
            {isCreate ? '创建技能' : `编辑: ${form.name}`}
          </span>
        </div>
        <div className="flex items-center gap-2">
          {!isCreate && (
            <button
              type="button"
              onClick={() => setShowEval(!showEval)}
              className="rounded-lg border border-border px-3 py-1.5 text-xs text-text2 transition-colors hover:border-accent/40"
            >
              {showEval ? '隐藏评测' : '评测'}
            </button>
          )}
          <button
            type="button"
            onClick={syncFrontmatter}
            className="rounded-lg border border-border px-3 py-1.5 text-xs text-text2 transition-colors hover:border-accent/40"
          >
            同步 Frontmatter
          </button>
          <button
            type="button"
            onClick={() => saveMut.mutate()}
            disabled={saveMut.isPending || !form.name.trim()}
            className="rounded-lg bg-accent px-4 py-1.5 text-xs font-medium text-[#0f172a] transition-colors hover:bg-accent/80 disabled:opacity-50"
          >
            {saveMut.isPending ? '保存中...' : '保存'}
          </button>
        </div>
      </div>

      {/* Main: left form + right editor */}
      <div className="flex flex-1 min-h-0 overflow-hidden">
        {/* Left: metadata form */}
        <div className="w-80 shrink-0 border-r border-border overflow-y-auto p-4 space-y-4">
          <FieldGroup label="名称">
            <input
              type="text"
              value={form.name}
              onChange={(e) => setField('name', e.target.value)}
              placeholder="kebab-case, e.g. incident-commander"
              className="w-full rounded-lg border border-border bg-bg px-3 py-2 text-sm text-text placeholder:text-text3 focus:border-accent/50 focus:outline-none"
            />
          </FieldGroup>

          <FieldGroup label="描述">
            <textarea
              rows={3}
              value={form.description}
              onChange={(e) => setField('description', e.target.value)}
              placeholder="做什么 + 何时触发"
              className="w-full rounded-lg border border-border bg-bg px-3 py-2 text-sm text-text placeholder:text-text3 focus:border-accent/50 focus:outline-none resize-none"
            />
          </FieldGroup>

          <FieldGroup label="所有者">
            <select
              value={form.owner}
              onChange={(e) => setField('owner', e.target.value)}
              className="w-full rounded-lg border border-border bg-bg px-3 py-2 text-sm text-text focus:border-accent/50 focus:outline-none"
            >
              <option value="system">系统</option>
              <option value="shared">共享</option>
            </select>
          </FieldGroup>

          <FieldGroup label="允许工具 (空格分隔)">
            <input
              type="text"
              value={form.allowed_tools}
              onChange={(e) => setField('allowed_tools', e.target.value)}
              placeholder="get_system_overview analyze_resource_trend"
              className="w-full rounded-lg border border-border bg-bg px-3 py-2 text-sm text-text placeholder:text-text3 focus:border-accent/50 focus:outline-none"
            />
          </FieldGroup>

          <FieldGroup label="允许角色 (空格分隔)">
            <input
              type="text"
              value={form.allowed_roles}
              onChange={(e) => setField('allowed_roles', e.target.value)}
              placeholder="admin user"
              className="w-full rounded-lg border border-border bg-bg px-3 py-2 text-sm text-text placeholder:text-text3 focus:border-accent/50 focus:outline-none"
            />
          </FieldGroup>

          <FieldGroup label="页面上下文 (空格分隔)">
            <input
              type="text"
              value={form.page_contexts}
              onChange={(e) => setField('page_contexts', e.target.value)}
              placeholder="dashboard monitoring notifications"
              className="w-full rounded-lg border border-border bg-bg px-3 py-2 text-sm text-text placeholder:text-text3 focus:border-accent/50 focus:outline-none"
            />
          </FieldGroup>

          <FieldGroup label="能力标签 (空格分隔)">
            <input
              type="text"
              value={form.capabilities}
              onChange={(e) => setField('capabilities', e.target.value)}
              placeholder="diagnosis triage incident-command"
              className="w-full rounded-lg border border-border bg-bg px-3 py-2 text-sm text-text placeholder:text-text3 focus:border-accent/50 focus:outline-none"
            />
          </FieldGroup>

          <FieldGroup label="依赖技能 (空格分隔)">
            <input
              type="text"
              value={form.compose}
              onChange={(e) => setField('compose', e.target.value)}
              placeholder="security-audit diagnosis"
              className="w-full rounded-lg border border-border bg-bg px-3 py-2 text-sm text-text placeholder:text-text3 focus:border-accent/50 focus:outline-none"
            />
          </FieldGroup>
        </div>

        {/* Right: SKILL.md editor */}
        <div className="flex-1 flex flex-col min-w-0">
          <div className="shrink-0 px-4 py-2 border-b border-border">
            <span className="text-xs font-medium text-text3">SKILL.md</span>
          </div>
          <textarea
            value={form.skill_markdown}
            onChange={(e) => setField('skill_markdown', e.target.value)}
            spellCheck={false}
            className="flex-1 w-full resize-none bg-bg p-4 font-mono text-sm text-text placeholder:text-text3 focus:outline-none"
            placeholder="---\nname: my-skill\ndescription: ...\n---\n\n# My Skill\n\n## 工作流\n1. ..."
          />
        </div>
      </div>

      {/* Bottom: attached files */}
      {!isCreate && (
        <div className="shrink-0 border-t border-border p-4">
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs font-medium text-text3">附属文件</span>
            <button
              type="button"
              onClick={handleFileUpload}
              className="rounded-lg border border-border px-2.5 py-1 text-xs text-text2 transition-colors hover:border-accent/40"
            >
              + 上传文件
            </button>
          </div>
          {files.length === 0 ? (
            <div className="text-xs text-text3">暂无附属文件</div>
          ) : (
            <div className="flex flex-wrap gap-2">
              {files.map((f: SkillFile) => (
                <div
                  key={f.path}
                  className="flex items-center gap-2 rounded-lg bg-bg2 px-2.5 py-1.5 text-xs text-text2"
                >
                  <span className="truncate max-w-[200px]">{f.path}</span>
                  {f.size != null && (
                    <span className="text-text3">{(f.size / 1024).toFixed(1)}KB</span>
                  )}
                  <button
                    type="button"
                    onClick={() => {
                      if (window.confirm(`删除文件 ${f.path}？`)) {
                        deleteFileMut.mutate(f.path)
                      }
                    }}
                    className="text-red hover:text-red/80 transition-colors"
                  >
                    &times;
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Eval panel */}
      {showEval && skillId && (
        <div className="shrink-0 border-t border-border max-h-[400px] overflow-y-auto">
          <SkillEvalPanel skillId={skillId} />
        </div>
      )}
    </div>
  )
}

function FieldGroup({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <label className="block text-xs font-medium text-text3 mb-1">{label}</label>
      {children}
    </div>
  )
}
