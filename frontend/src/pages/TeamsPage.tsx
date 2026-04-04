/**
 * 团队管理页面 — 多 Agent 协作编排
 *
 * 功能: 团队 CRUD / 成员管理 / 任务执行(SSE) / 模板实例化
 * API 前缀: /api/agents/teams
 *
 * 组件已拆分至 ./teams/ 子目录，本文件仅为路由入口薄壳。
 */

import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import client from '@/api/client'
import { cn, ensureArray } from '@/lib/utils'
import type { Team, TeamMember } from '@/types/team'
import {
  TOPOLOGY_LABELS,
  normalizeTeams,
  normalizeMembers,
  TabBar,
  CreateTeamModal,
  TemplatesTab,
  TeamDetail,
} from './teams'

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
