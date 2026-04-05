/**
 * SkillsTab - Skill management tab for the Agent admin panel.
 * Two sub-views: installed skills list + market view.
 */

import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import { cn } from '@/lib/utils'
import {
  listSkills,
  enableSkill,
  disableSkill,
  deleteSkill,
  exportSkill,
  type SkillMeta,
} from '@/api/skills'
import { SkillEditor } from './SkillEditor'
import { SkillMarketView } from './SkillMarketView'

type SubView = 'installed' | 'market'

const OWNER_LABELS: Record<string, string> = {
  system: '\uD83D\uDDA5\uFE0F \u7CFB\u7EDF',
  shared: '\uD83C\uDFE2 \u5171\u4EAB',
}

function ownerLabel(owner: string): string {
  return OWNER_LABELS[owner] ?? `\uD83D\uDC64 ${owner}`
}

export function SkillsTab() {
  const qc = useQueryClient()
  const [view, setView] = useState<SubView>('installed')
  const [editingSkillId, setEditingSkillId] = useState<string | null>(null)
  const [creating, setCreating] = useState(false)

  const { data, isLoading } = useQuery({
    queryKey: ['admin-skills'],
    queryFn: listSkills,
  })

  const skills: SkillMeta[] = data?.skills ?? []

  const toggleMut = useMutation({
    mutationFn: async (skill: SkillMeta) => {
      if (skill.enabled) {
        await disableSkill(skill.id)
      } else {
        await enableSkill(skill.id)
      }
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['admin-skills'] })
      toast.success('状态已更新')
    },
    onError: () => toast.error('操作失败'),
  })

  const deleteMut = useMutation({
    mutationFn: deleteSkill,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['admin-skills'] })
      toast.success('技能已删除')
      if (editingSkillId) setEditingSkillId(null)
    },
    onError: () => toast.error('删除失败'),
  })

  const handleExport = async (id: string, name: string) => {
    try {
      const blob = await exportSkill(id)
      const url = URL.createObjectURL(blob as Blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `${name}.zip`
      a.click()
      URL.revokeObjectURL(url)
      toast.success('导出成功')
    } catch {
      toast.error('导出失败')
    }
  }

  // Show editor if editing or creating
  if (editingSkillId) {
    return (
      <SkillEditor
        skillId={editingSkillId}
        onClose={() => setEditingSkillId(null)}
        onSaved={() => {
          qc.invalidateQueries({ queryKey: ['admin-skills'] })
          setEditingSkillId(null)
        }}
      />
    )
  }

  if (creating) {
    return (
      <SkillEditor
        skillId={null}
        onClose={() => setCreating(false)}
        onSaved={() => {
          qc.invalidateQueries({ queryKey: ['admin-skills'] })
          setCreating(false)
        }}
      />
    )
  }

  return (
    <div className="flex h-full flex-col">
      {/* Sub-view tabs + action bar */}
      <div className="flex items-center justify-between border-b border-border px-4 py-2 shrink-0">
        <div className="flex items-center gap-1">
          {(['installed', 'market'] as const).map((v) => (
            <button
              key={v}
              className={cn(
                'px-3 py-1.5 text-xs rounded-lg transition-colors',
                view === v
                  ? 'bg-accent-dim text-accent'
                  : 'text-text3 hover:text-text hover:bg-bg2',
              )}
              onClick={() => setView(v)}
            >
              {v === 'installed' ? '已安装' : '市场'}
            </button>
          ))}
        </div>

        {view === 'installed' && (
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => setCreating(true)}
              className="rounded-lg bg-accent px-3 py-1.5 text-xs font-medium text-[#0f172a] transition-colors hover:bg-accent/80"
            >
              + 创建技能
            </button>
          </div>
        )}
      </div>

      {/* Content */}
      <div className="flex-1 min-h-0 overflow-y-auto p-4">
        {view === 'market' ? (
          <SkillMarketView />
        ) : (
          <InstalledList
            skills={skills}
            isLoading={isLoading}
            onEdit={setEditingSkillId}
            onToggle={(s) => toggleMut.mutate(s)}
            onDelete={(id) => {
              if (window.confirm('确认删除该技能？')) deleteMut.mutate(id)
            }}
            onExport={handleExport}
          />
        )}
      </div>
    </div>
  )
}

// ── Installed skills list ───────────────────────────────

function InstalledList({
  skills,
  isLoading,
  onEdit,
  onToggle,
  onDelete,
  onExport,
}: {
  skills: SkillMeta[]
  isLoading: boolean
  onEdit: (id: string) => void
  onToggle: (s: SkillMeta) => void
  onDelete: (id: string) => void
  onExport: (id: string, name: string) => void
}) {
  if (isLoading) {
    return <div className="text-sm text-text3 text-center py-12">加载中...</div>
  }

  if (skills.length === 0) {
    return (
      <div className="text-center py-12">
        <div className="text-text3 text-sm">暂无已安装技能</div>
        <div className="text-text3 text-xs mt-2">点击「创建技能」或从市场安装</div>
      </div>
    )
  }

  return (
    <div className="space-y-3">
      {skills.map((skill) => (
        <div
          key={skill.id}
          className="rounded-xl border border-border bg-bg p-4 transition-colors hover:border-border/80"
        >
          <div className="flex items-start justify-between gap-4">
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2">
                <span className="text-sm font-medium text-text truncate">{skill.name}</span>
                <span className="shrink-0 text-[11px] text-text3">v{skill.version}</span>
                <span className="shrink-0 text-[11px] text-text3">{ownerLabel(skill.owner)}</span>
                {skill.enabled ? (
                  <span className="shrink-0 rounded bg-green/10 px-1.5 py-0.5 text-[11px] text-green">
                    启用
                  </span>
                ) : (
                  <span className="shrink-0 rounded bg-red/10 px-1.5 py-0.5 text-[11px] text-red">
                    禁用
                  </span>
                )}
              </div>
              <div className="mt-1 text-xs text-text3 line-clamp-2">{skill.description}</div>
              {skill.allowed_tools && skill.allowed_tools.length > 0 && (
                <div className="mt-2 flex flex-wrap gap-1">
                  {skill.allowed_tools.slice(0, 5).map((t) => (
                    <span key={t} className="rounded bg-bg2 px-1.5 py-0.5 text-[11px] text-text3">
                      {t}
                    </span>
                  ))}
                  {skill.allowed_tools.length > 5 && (
                    <span className="text-[11px] text-text3">+{skill.allowed_tools.length - 5}</span>
                  )}
                </div>
              )}
            </div>

            <div className="flex shrink-0 gap-1.5">
              <ActionBtn label="编辑" onClick={() => onEdit(skill.id)} />
              <ActionBtn label="导出" onClick={() => onExport(skill.id, skill.name)} />
              <ActionBtn
                label={skill.enabled ? '禁用' : '启用'}
                onClick={() => onToggle(skill)}
              />
              <ActionBtn label="删除" variant="danger" onClick={() => onDelete(skill.id)} />
            </div>
          </div>
        </div>
      ))}
    </div>
  )
}

function ActionBtn({
  label,
  onClick,
  variant = 'default',
}: {
  label: string
  onClick: () => void
  variant?: 'default' | 'danger'
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        'rounded-lg border px-2.5 py-1 text-xs transition-colors',
        variant === 'danger'
          ? 'border-red/30 text-red hover:bg-red/10'
          : 'border-border text-text2 hover:border-accent/40 hover:text-text',
      )}
    >
      {label}
    </button>
  )
}
