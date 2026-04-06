/**
 * 用户权限 Tab — 为面板用户分配/移除 RBAC 角色
 * 展示用户列表，点击用户可展开分配面板
 * API 前缀: /api/rbac/users, /api/panel-users, /api/rbac/roles
 */

import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import client from '@/api/client'
import toast from 'react-hot-toast'
import { cn, ensureArray, ensureRecord, toString, toNumber } from '@/lib/utils'

/* ---------- types ---------- */

interface PanelUser {
  id: number
  username: string
  display_name: string
  role: string
}

interface RbacRole {
  id: string
  name: string
  display_name: string
  builtin: boolean
}

interface UserRolesResponse {
  user_id: string
  roles: string[]
}

/* ---------- normalizers ---------- */

function normalizePanelUsers(value: unknown): PanelUser[] {
  const record = ensureRecord(value)
  return ensureArray<Record<string, unknown>>(record.users).map((item) => ({
    id: toNumber(item.id),
    username: toString(item.username),
    display_name: toString(item.display_name),
    role: toString(item.role, 'user'),
  }))
}

function normalizeRoles(value: unknown): RbacRole[] {
  const record = ensureRecord(value)
  const items = Array.isArray(value) ? value : (record.roles ?? record.items ?? [])
  return ensureArray<Record<string, unknown>>(items).map((item) => ({
    id: toString(item.id),
    name: toString(item.name),
    display_name: toString(item.display_name),
    builtin: Boolean(item.builtin),
  }))
}

function normalizeUserRoles(value: unknown): string[] {
  const record = ensureRecord(value)
  return ensureArray<unknown>(record.roles).map((r) => toString(r))
}

/* ---------- RoleTag — single assigned role with remove button ---------- */

interface RoleTagProps {
  roleId: string
  roles: RbacRole[]
  onRemove: () => void
  isRemoving: boolean
}

function RoleTag({ roleId, roles, onRemove, isRemoving }: RoleTagProps) {
  const role = roles.find((r) => r.id === roleId || r.name === roleId)
  const label = role ? (role.display_name || role.name) : roleId

  return (
    <span
      className={cn(
        'inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium',
        role?.builtin
          ? 'bg-purple-500/20 text-purple-400 border border-purple-500/30'
          : 'bg-accent-dim text-accent border border-accent/30',
      )}
    >
      {label}
      <button
        onClick={onRemove}
        disabled={isRemoving}
        title="移除角色"
        className="ml-0.5 text-current opacity-60 hover:opacity-100 disabled:opacity-30 leading-none"
      >
        <i className="ti ti-x text-[10px]" />
      </button>
    </span>
  )
}

/* ---------- UserRolePanel — expanded panel for a single user ---------- */

interface UserRolePanelProps {
  user: PanelUser
  allRoles: RbacRole[]
  onClose: () => void
}

function UserRolePanel({ user, allRoles, onClose }: UserRolePanelProps) {
  const qc = useQueryClient()
  const [selectedRoleId, setSelectedRoleId] = useState('')

  const userId = String(user.id)

  const { data: assignedRoleIds = [], isLoading } = useQuery<string[]>({
    queryKey: ['rbac-user-roles', userId],
    queryFn: () =>
      client
        .get<UserRolesResponse>(`/api/rbac/users/${userId}/roles`)
        .then((r) => normalizeUserRoles(r.data)),
  })

  const assignMut = useMutation({
    mutationFn: (roleId: string) =>
      client.put(`/api/rbac/users/${userId}/roles`, { role_id: roleId }).then((r) => r.data),
    onSuccess: () => {
      toast.success('角色已分配')
      setSelectedRoleId('')
      qc.invalidateQueries({ queryKey: ['rbac-user-roles', userId] })
      qc.invalidateQueries({ queryKey: ['rbac-roles'] })
    },
    onError: () => toast.error('分配失败'),
  })

  const removeMut = useMutation({
    mutationFn: (roleId: string) =>
      client.delete(`/api/rbac/users/${userId}/roles/${roleId}`).then((r) => r.data),
    onSuccess: () => {
      toast.success('角色已移除')
      qc.invalidateQueries({ queryKey: ['rbac-user-roles', userId] })
      qc.invalidateQueries({ queryKey: ['rbac-roles'] })
    },
    onError: () => toast.error('移除失败'),
  })

  // roles not yet assigned to this user
  const unassignedRoles = allRoles.filter(
    (r) => !assignedRoleIds.includes(r.id) && !assignedRoleIds.includes(r.name),
  )

  function handleAdd() {
    if (!selectedRoleId) return
    assignMut.mutate(selectedRoleId)
  }

  return (
    <div className="bg-card border border-border rounded-lg p-4 mt-1">
      <div className="flex items-start justify-between mb-3">
        <div>
          <p className="font-medium text-text text-sm">
            {user.display_name || user.username}
          </p>
          <p className="text-xs text-text3 font-mono">{user.username}</p>
        </div>
        <button
          onClick={onClose}
          className="text-text3 hover:text-text leading-none mt-0.5"
          title="收起"
        >
          <i className="ti ti-chevron-up text-base" />
        </button>
      </div>

      {/* Assigned roles */}
      <div className="mb-3">
        <p className="text-xs text-text3 mb-1.5">已分配角色</p>
        {isLoading ? (
          <span className="text-xs text-text3">加载中...</span>
        ) : assignedRoleIds.length === 0 ? (
          <span className="text-xs text-text3 italic">暂未分配任何 RBAC 角色</span>
        ) : (
          <div className="flex flex-wrap gap-1.5">
            {assignedRoleIds.map((rid) => (
              <RoleTag
                key={rid}
                roleId={rid}
                roles={allRoles}
                onRemove={() => removeMut.mutate(rid)}
                isRemoving={removeMut.isPending}
              />
            ))}
          </div>
        )}
      </div>

      {/* Add role */}
      <div className="flex items-center gap-2">
        <select
          value={selectedRoleId}
          onChange={(e) => setSelectedRoleId(e.target.value)}
          className="flex-1 bg-bg border border-border rounded-md px-2 py-1.5 text-sm text-text focus:border-accent focus:outline-none"
        >
          <option value="">选择要添加的角色...</option>
          {unassignedRoles.map((r) => (
            <option key={r.id} value={r.id}>
              {r.display_name || r.name}
              {r.builtin ? ' (内置)' : ''}
            </option>
          ))}
        </select>
        <button
          onClick={handleAdd}
          disabled={!selectedRoleId || assignMut.isPending}
          className="bg-accent text-[#0f172a] px-3 py-1.5 rounded-md text-sm font-medium disabled:opacity-50 whitespace-nowrap"
        >
          {assignMut.isPending ? '添加中...' : '添加'}
        </button>
      </div>
    </div>
  )
}

/* ---------- main component ---------- */

export default function UserRolesTab() {
  const [expandedUserId, setExpandedUserId] = useState<number | null>(null)

  const { data: users = [], isLoading: usersLoading } = useQuery<PanelUser[]>({
    queryKey: ['panel-users-rbac'],
    queryFn: () => client.get('/api/panel-users/').then((r) => normalizePanelUsers(r.data)),
  })

  const { data: allRoles = [], isLoading: rolesLoading } = useQuery<RbacRole[]>({
    queryKey: ['rbac-roles'],
    queryFn: () => client.get('/api/rbac/roles').then((r) => normalizeRoles(r.data)),
  })

  const isLoading = usersLoading || rolesLoading

  function toggleUser(userId: number) {
    setExpandedUserId((prev) => (prev === userId ? null : userId))
  }

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold text-text">用户权限</h2>
        <p className="text-xs text-text3">点击用户行展开角色分配面板</p>
      </div>

      {/* User list */}
      <div className="bg-card border border-border rounded-lg overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border text-text3 text-left">
              <th className="px-4 py-3 font-medium">用户名</th>
              <th className="px-4 py-3 font-medium hidden sm:table-cell">显示名称</th>
              <th className="px-4 py-3 font-medium">系统角色</th>
              <th className="px-4 py-3 font-medium text-center w-20">RBAC 角色</th>
              <th className="px-4 py-3 font-medium text-right w-16">操作</th>
            </tr>
          </thead>
          <tbody>
            {isLoading ? (
              <tr>
                <td colSpan={5} className="px-4 py-8 text-center text-text3">
                  加载中...
                </td>
              </tr>
            ) : users.length === 0 ? (
              <tr>
                <td colSpan={5} className="px-4 py-8 text-center text-text3">
                  暂无用户
                </td>
              </tr>
            ) : (
              users.map((user) => {
                const isExpanded = expandedUserId === user.id
                return (
                  <>
                    <tr
                      key={user.id}
                      onClick={() => toggleUser(user.id)}
                      className={cn(
                        'border-b border-border cursor-pointer transition-colors',
                        isExpanded ? 'bg-accent-dim' : 'hover:bg-bg2/50',
                      )}
                    >
                      <td className="px-4 py-2.5 font-medium text-text">{user.username}</td>
                      <td className="px-4 py-2.5 text-text2 hidden sm:table-cell">
                        {user.display_name || '-'}
                      </td>
                      <td className="px-4 py-2.5">
                        <span
                          className={cn(
                            'inline-block px-2 py-0.5 rounded text-xs font-medium',
                            user.role === 'admin'
                              ? 'bg-accent-dim text-accent'
                              : 'bg-bg2 text-text3',
                          )}
                        >
                          {user.role}
                        </span>
                      </td>
                      <td className="px-4 py-2.5 text-center">
                        <UserRoleCountBadge userId={user.id} />
                      </td>
                      <td className="px-4 py-2.5 text-right">
                        <button
                          onClick={(e) => {
                            e.stopPropagation()
                            toggleUser(user.id)
                          }}
                          className="text-text3 hover:text-text"
                          title={isExpanded ? '收起' : '分配角色'}
                        >
                          <i
                            className={cn(
                              'ti text-base transition-transform',
                              isExpanded ? 'ti-chevron-up' : 'ti-chevron-down',
                            )}
                          />
                        </button>
                      </td>
                    </tr>
                    {isExpanded && (
                      <tr key={`${user.id}-panel`} className="border-b border-border">
                        <td colSpan={5} className="px-4 pb-4 pt-1">
                          <UserRolePanel
                            user={user}
                            allRoles={allRoles}
                            onClose={() => setExpandedUserId(null)}
                          />
                        </td>
                      </tr>
                    )}
                  </>
                )
              })
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}

/* ---------- UserRoleCountBadge — lazy-loads role count for a user ---------- */

function UserRoleCountBadge({ userId }: { userId: number }) {
  const { data: roleIds } = useQuery<string[]>({
    queryKey: ['rbac-user-roles', String(userId)],
    queryFn: () =>
      client
        .get<UserRolesResponse>(`/api/rbac/users/${userId}/roles`)
        .then((r) => normalizeUserRoles(r.data)),
    staleTime: 30_000,
  })

  if (roleIds === undefined) {
    return <span className="text-text3 text-xs">—</span>
  }

  return (
    <span
      className={cn(
        'inline-block px-2 py-0.5 rounded text-xs font-medium',
        roleIds.length > 0 ? 'bg-green/20 text-green' : 'bg-bg2 text-text3',
      )}
    >
      {roleIds.length}
    </span>
  )
}
