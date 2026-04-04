/**
 * 团队详情面板
 */

import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import client from '@/api/client'
import toast from 'react-hot-toast'
import { cn, getErrorMessage } from '@/lib/utils'
import { useAuthStore } from '@/stores/authStore'
import type { Team } from '@/types/team'
import { TOPOLOGY_LABELS } from './constants'
import { TabBar } from './TabBar'
import { MembersTab } from './MembersTab'
import { ExecuteTab } from './ExecuteTab'
import { ExecutionsTab } from './ExecutionsTab'

export function TeamDetail({ team, onBack }: { team: Team; onBack: () => void }) {
  const qc = useQueryClient()
  const role = useAuthStore((s) => s.user?.role)
  const isAdmin = role === 'admin'
  const [activeTab, setActiveTab] = useState('members')

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
