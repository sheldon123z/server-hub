/**
 * 角色管理页 /settings/roles
 * Tab 1: 角色列表 + 创建/编辑 modal + 删除 + 权限矩阵编辑器
 * Tab 2: 用户权限 — 为面板用户分配/移除 RBAC 角色
 * API 前缀: /api/rbac
 */

import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import client from '@/api/client'
import toast from 'react-hot-toast'
import { cn, ensureArray, ensureRecord, toString, toNumber } from '@/lib/utils'
import PermissionMatrix, { type PermEntry } from './PermissionMatrix'
import UserRolesTab from './UserRolesTab'

/* ---------- types ---------- */

interface Role {
  id: string
  name: string
  display_name: string
  description: string
  builtin: boolean
  user_count?: number
  permissions: PermEntry[]
}

interface RoleForm {
  name: string
  display_name: string
  description: string
}

const emptyForm: RoleForm = { name: '', display_name: '', description: '' }

/* ---------- normalizers ---------- */

function normalizePermission(p: Record<string, unknown>): PermEntry {
  return {
    id: typeof p.id === 'number' ? p.id : undefined,
    role_id: toString(p.role_id),
    resource: toString(p.resource),
    action: toString(p.action),
    scope: toString(p.scope, '*'),
  }
}

function normalizeRole(item: Record<string, unknown>): Role {
  return {
    id: toString(item.id),
    name: toString(item.name),
    display_name: toString(item.display_name),
    description: toString(item.description),
    builtin: Boolean(item.builtin),
    user_count: toNumber(item.user_count, 0),
    permissions: ensureArray<Record<string, unknown>>(item.permissions).map(normalizePermission),
  }
}

function normalizeRolesResponse(value: unknown): Role[] {
  const record = ensureRecord(value)
  const items = Array.isArray(value) ? value : (record.roles ?? record.items ?? [])
  return ensureArray<Record<string, unknown>>(items).map(normalizeRole)
}

/* ---------- role form modal ---------- */

interface RoleModalProps {
  initial: RoleForm
  editingId: string | null
  onClose: () => void
  onSave: (form: RoleForm) => void
  isPending: boolean
}

function RoleModal({ initial, editingId, onClose, onSave, isPending }: RoleModalProps) {
  const [form, setForm] = useState<RoleForm>(initial)

  const f = <K extends keyof RoleForm>(key: K, val: RoleForm[K]) =>
    setForm((prev) => ({ ...prev, [key]: val }))

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!form.name.trim()) {
      toast.error('角色标识不能为空')
      return
    }
    onSave(form)
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60" onClick={onClose}>
      <div
        className="bg-card border border-border rounded-lg p-6 w-full max-w-md shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <h3 className="text-base font-semibold text-text mb-4">
          {editingId ? '编辑角色' : '新建角色'}
        </h3>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-xs text-text3 mb-1">
              角色标识 <span className="text-red-400">*</span>
            </label>
            <input
              value={form.name}
              onChange={(e) => f('name', e.target.value)}
              disabled={!!editingId} // 编辑时不允许改 name
              placeholder="如: docker-admin"
              className="w-full bg-bg border border-border rounded-md px-3 py-2 text-sm text-text focus:border-accent focus:outline-none disabled:opacity-50 disabled:cursor-not-allowed"
            />
            <p className="text-[11px] text-text3 mt-1">小写字母、数字、连字符，全局唯一</p>
          </div>

          <div>
            <label className="block text-xs text-text3 mb-1">显示名称</label>
            <input
              value={form.display_name}
              onChange={(e) => f('display_name', e.target.value)}
              placeholder="如: Docker 管理员"
              className="w-full bg-bg border border-border rounded-md px-3 py-2 text-sm text-text focus:border-accent focus:outline-none"
            />
          </div>

          <div>
            <label className="block text-xs text-text3 mb-1">描述</label>
            <textarea
              value={form.description}
              onChange={(e) => f('description', e.target.value)}
              rows={2}
              placeholder="可选说明..."
              className="w-full bg-bg border border-border rounded-md px-3 py-2 text-sm text-text focus:border-accent focus:outline-none resize-none"
            />
          </div>

          <div className="flex justify-end gap-2 pt-1">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-1.5 rounded-md text-sm border border-border text-text2 hover:bg-bg2"
            >
              取消
            </button>
            <button
              type="submit"
              disabled={isPending}
              className="bg-accent text-[#0f172a] px-4 py-1.5 rounded-md text-sm font-medium disabled:opacity-50"
            >
              {isPending ? '保存中...' : editingId ? '保存修改' : '创建角色'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

/* ---------- role detail panel ---------- */

interface RoleDetailProps {
  role: Role
  onClose: () => void
}

function RoleDetail({ role, onClose }: RoleDetailProps) {
  return (
    <div className="bg-card border border-border rounded-lg p-4">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h3 className="font-semibold text-text">{role.display_name || role.name}</h3>
          <p className="text-xs text-text3 font-mono">{role.name}</p>
        </div>
        <button onClick={onClose} className="text-text3 hover:text-text text-lg leading-none">
          ×
        </button>
      </div>

      {role.description && <p className="text-sm text-text2 mb-4">{role.description}</p>}

      {role.builtin && (
        <div className="mb-4 px-3 py-2 bg-yellow-500/10 border border-yellow-500/20 rounded-md text-xs text-yellow-400">
          内置角色权限由系统管理，不可修改
        </div>
      )}

      <h4 className="text-xs font-medium text-text3 uppercase tracking-wider mb-3">权限矩阵</h4>
      <PermissionMatrix
        roleId={role.id}
        permissions={role.permissions}
        readonly={role.builtin}
      />
    </div>
  )
}

/* ---------- tab bar ---------- */

type TabKey = 'roles' | 'user-roles'

const TABS: { key: TabKey; label: string; icon: string }[] = [
  { key: 'roles', label: '角色管理', icon: 'ti-shield-lock' },
  { key: 'user-roles', label: '用户权限', icon: 'ti-user-check' },
]

/* ---------- main page ---------- */

export default function RolesPage() {
  const qc = useQueryClient()
  const [activeTab, setActiveTab] = useState<TabKey>('roles')
  const [showModal, setShowModal] = useState(false)
  const [editingRole, setEditingRole] = useState<Role | null>(null)
  const [selectedRoleId, setSelectedRoleId] = useState<string | null>(null)

  const { data: roles = [], isLoading } = useQuery<Role[]>({
    queryKey: ['rbac-roles'],
    queryFn: () => client.get('/api/rbac/roles').then((r) => normalizeRolesResponse(r.data)),
  })

  const createMut = useMutation({
    mutationFn: (body: RoleForm) => client.post('/api/rbac/roles', body).then((r) => r.data),
    onSuccess: () => {
      toast.success('角色已创建')
      qc.invalidateQueries({ queryKey: ['rbac-roles'] })
      closeModal()
    },
    onError: () => toast.error('创建失败'),
  })

  const updateMut = useMutation({
    mutationFn: ({ id, body }: { id: string; body: Partial<RoleForm> }) =>
      client.put(`/api/rbac/roles/${id}`, body).then((r) => r.data),
    onSuccess: () => {
      toast.success('角色已更新')
      qc.invalidateQueries({ queryKey: ['rbac-roles'] })
      closeModal()
    },
    onError: () => toast.error('更新失败'),
  })

  const deleteMut = useMutation({
    mutationFn: (id: string) => client.delete(`/api/rbac/roles/${id}`).then((r) => r.data),
    onSuccess: () => {
      toast.success('角色已删除')
      qc.invalidateQueries({ queryKey: ['rbac-roles'] })
      setSelectedRoleId(null)
    },
    onError: () => toast.error('删除失败'),
  })

  function openCreate() {
    setEditingRole(null)
    setShowModal(true)
  }

  function openEdit(role: Role, e: React.MouseEvent) {
    e.stopPropagation()
    setEditingRole(role)
    setShowModal(true)
  }

  function closeModal() {
    setShowModal(false)
    setEditingRole(null)
  }

  function handleSave(form: RoleForm) {
    if (editingRole) {
      updateMut.mutate({ id: editingRole.id, body: { display_name: form.display_name, description: form.description } })
    } else {
      createMut.mutate(form)
    }
  }

  function handleDelete(role: Role, e: React.MouseEvent) {
    e.stopPropagation()
    if (!confirm(`确认删除角色「${role.display_name || role.name}」？此操作不可撤销。`)) return
    deleteMut.mutate(role.id)
  }

  const selectedRole = roles.find((r) => r.id === selectedRoleId) ?? null
  const isPending = createMut.isPending || updateMut.isPending

  return (
    <div className="space-y-4">
      {/* Tab bar */}
      <div className="flex items-center gap-1 border-b border-border">
        {TABS.map((tab) => (
          <button
            key={tab.key}
            onClick={() => setActiveTab(tab.key)}
            className={cn(
              'flex items-center gap-1.5 px-4 py-2.5 text-sm font-medium border-b-2 -mb-px transition-colors',
              activeTab === tab.key
                ? 'border-accent text-accent'
                : 'border-transparent text-text2 hover:text-text hover:border-border',
            )}
          >
            <i className={cn('ti text-base', tab.icon)} />
            {tab.label}
          </button>
        ))}
      </div>

      {/* Tab: 用户权限 */}
      {activeTab === 'user-roles' && <UserRolesTab />}

      {/* Tab: 角色管理 */}
      {activeTab === 'roles' && (
        <>
      {/* Header */}
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold text-text">角色管理</h2>
        <button
          onClick={openCreate}
          className="bg-accent text-[#0f172a] px-3 py-1.5 rounded-md text-sm font-medium hover:opacity-90"
        >
          新建角色
        </button>
      </div>

      <div className={cn('grid gap-4', selectedRole ? 'grid-cols-1 xl:grid-cols-2' : 'grid-cols-1')}>
        {/* Role list */}
        <div className="bg-card border border-border rounded-lg overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border text-text3 text-left">
                <th className="px-4 py-3 font-medium">标识</th>
                <th className="px-4 py-3 font-medium">显示名称</th>
                <th className="px-4 py-3 font-medium hidden md:table-cell">描述</th>
                <th className="px-4 py-3 font-medium text-center w-16">类型</th>
                <th className="px-4 py-3 font-medium text-center w-16">用户数</th>
                <th className="px-4 py-3 font-medium text-right w-28">操作</th>
              </tr>
            </thead>
            <tbody>
              {isLoading ? (
                <tr>
                  <td colSpan={6} className="px-4 py-8 text-center text-text3">
                    加载中...
                  </td>
                </tr>
              ) : roles.length === 0 ? (
                <tr>
                  <td colSpan={6} className="px-4 py-8 text-center text-text3">
                    暂无角色
                  </td>
                </tr>
              ) : (
                roles.map((role) => (
                  <tr
                    key={role.id}
                    onClick={() => setSelectedRoleId(selectedRoleId === role.id ? null : role.id)}
                    className={cn(
                      'border-b border-border cursor-pointer transition-colors',
                      selectedRoleId === role.id
                        ? 'bg-accent-dim'
                        : 'hover:bg-bg2/50',
                    )}
                  >
                    <td className="px-4 py-2.5 font-mono text-text text-xs">{role.name}</td>
                    <td className="px-4 py-2.5 text-text2">{role.display_name || '-'}</td>
                    <td className="px-4 py-2.5 text-text3 text-xs hidden md:table-cell truncate max-w-[200px]">
                      {role.description || '-'}
                    </td>
                    <td className="px-4 py-2.5 text-center">
                      {role.builtin ? (
                        <span className="px-2 py-0.5 rounded text-[10px] font-medium bg-purple-500/20 text-purple-400">
                          内置
                        </span>
                      ) : (
                        <span className="px-2 py-0.5 rounded text-[10px] font-medium bg-bg2 text-text3">
                          自定义
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-2.5 text-center text-text3">{role.user_count ?? 0}</td>
                    <td className="px-4 py-2.5 text-right">
                      <div className="flex justify-end gap-1.5">
                        <button
                          onClick={(e) => openEdit(role, e)}
                          className="px-2 py-1 rounded text-xs border border-border text-text2 hover:bg-bg2"
                        >
                          编辑
                        </button>
                        <button
                          onClick={(e) => handleDelete(role, e)}
                          disabled={role.builtin || deleteMut.isPending}
                          className="px-2 py-1 rounded text-xs border border-border text-red-400 hover:bg-red-500/10 disabled:opacity-30 disabled:cursor-not-allowed"
                        >
                          删除
                        </button>
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>

        {/* Role detail / permission matrix */}
        {selectedRole && (
          <RoleDetail
            role={selectedRole}
            onClose={() => setSelectedRoleId(null)}
          />
        )}
      </div>

      {/* Modal */}
      {showModal && (
        <RoleModal
          initial={
            editingRole
              ? { name: editingRole.name, display_name: editingRole.display_name, description: editingRole.description }
              : emptyForm
          }
          editingId={editingRole?.id ?? null}
          onClose={closeModal}
          onSave={handleSave}
          isPending={isPending}
        />
      )}
        </>
      )}
    </div>
  )
}
