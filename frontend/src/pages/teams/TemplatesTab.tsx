/**
 * 团队模板标签页
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import client from '@/api/client'
import toast from 'react-hot-toast'
import { cn, ensureArray, getErrorMessage } from '@/lib/utils'
import { useAuthStore } from '@/stores/authStore'
import type { TeamTemplate } from '@/types/team'
import { TOPOLOGY_LABELS } from './constants'
import { normalizeTemplates } from './normalizers'

export function TemplatesTab() {
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
