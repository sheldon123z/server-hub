/**
 * 团队成员管理标签页
 */

import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import client from '@/api/client'
import toast from 'react-hot-toast'
import { cn, ensureArray, getErrorMessage } from '@/lib/utils'
import { useAuthStore } from '@/stores/authStore'
import type { AgentType, TeamMember, MemberCreateRequest } from '@/types/team'
import { AGENT_TYPE_COLORS } from './constants'
import { normalizeMembers } from './normalizers'

export function MembersTab({ teamId }: { teamId: string }) {
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
