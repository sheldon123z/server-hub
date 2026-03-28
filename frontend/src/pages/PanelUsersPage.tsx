import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import client from '@/api/client'
import toast from 'react-hot-toast'
import { formatDate } from '@/lib/utils'

interface PanelUser {
  id: number
  username: string
  display_name: string
  role: string
  created_at: string
}

interface UserForm {
  username: string
  password: string
  display_name: string
  role: string
}

const emptyForm: UserForm = { username: '', password: '', display_name: '', role: 'user' }

export default function PanelUsersPage() {
  const queryClient = useQueryClient()
  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState<UserForm>(emptyForm)
  const [editingId, setEditingId] = useState<number | null>(null)

  const { data, isLoading } = useQuery<{ users: PanelUser[]; count: number }>({
    queryKey: ['panel-users'],
    queryFn: () => client.get('/api/panel-users/').then((r) => r.data),
  })

  const createMutation = useMutation({
    mutationFn: (body: UserForm) => client.post('/api/panel-users/', body),
    onSuccess: () => {
      toast.success('用户创建成功')
      queryClient.invalidateQueries({ queryKey: ['panel-users'] })
      resetForm()
    },
    onError: () => toast.error('创建失败'),
  })

  const updateMutation = useMutation({
    mutationFn: ({ id, body }: { id: number; body: { display_name: string; role: string } }) =>
      client.put(`/api/panel-users/${id}`, body),
    onSuccess: () => {
      toast.success('用户更新成功')
      queryClient.invalidateQueries({ queryKey: ['panel-users'] })
      resetForm()
    },
    onError: () => toast.error('更新失败'),
  })

  const deleteMutation = useMutation({
    mutationFn: (id: number) => client.delete(`/api/panel-users/${id}`),
    onSuccess: () => {
      toast.success('用户已删除')
      queryClient.invalidateQueries({ queryKey: ['panel-users'] })
    },
    onError: () => toast.error('删除失败'),
  })

  function resetForm() {
    setForm(emptyForm)
    setShowForm(false)
    setEditingId(null)
  }

  function startEdit(user: PanelUser) {
    setForm({ username: user.username, password: '', display_name: user.display_name, role: user.role })
    setEditingId(user.id)
    setShowForm(true)
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (editingId) {
      updateMutation.mutate({ id: editingId, body: { display_name: form.display_name, role: form.role } })
    } else {
      if (!form.username || !form.password) {
        toast.error('用户名和密码不能为空')
        return
      }
      createMutation.mutate(form)
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold text-text">面板用户</h2>
        <button
          onClick={() => {
            resetForm()
            setShowForm(!showForm)
          }}
          className="bg-accent text-[#0f172a] px-3 py-1.5 rounded-md text-sm font-medium"
        >
          {showForm ? '取消' : '新增用户'}
        </button>
      </div>

      {showForm && (
        <form onSubmit={handleSubmit} className="bg-card border border-border rounded-lg p-4 space-y-3">
          <div className="grid grid-cols-2 gap-3">
            {!editingId && (
              <>
                <div>
                  <label className="block text-xs text-text3 mb-1">用户名</label>
                  <input
                    value={form.username}
                    onChange={(e) => setForm({ ...form, username: e.target.value })}
                    className="w-full bg-bg border border-border rounded-md px-3 py-2 text-sm text-text focus:border-accent focus:outline-none"
                  />
                </div>
                <div>
                  <label className="block text-xs text-text3 mb-1">密码</label>
                  <input
                    type="password"
                    value={form.password}
                    onChange={(e) => setForm({ ...form, password: e.target.value })}
                    className="w-full bg-bg border border-border rounded-md px-3 py-2 text-sm text-text focus:border-accent focus:outline-none"
                  />
                </div>
              </>
            )}
            <div>
              <label className="block text-xs text-text3 mb-1">显示名称</label>
              <input
                value={form.display_name}
                onChange={(e) => setForm({ ...form, display_name: e.target.value })}
                className="w-full bg-bg border border-border rounded-md px-3 py-2 text-sm text-text focus:border-accent focus:outline-none"
              />
            </div>
            <div>
              <label className="block text-xs text-text3 mb-1">角色</label>
              <select
                value={form.role}
                onChange={(e) => setForm({ ...form, role: e.target.value })}
                className="w-full bg-bg border border-border rounded-md px-3 py-2 text-sm text-text focus:border-accent focus:outline-none"
              >
                <option value="user">user</option>
                <option value="admin">admin</option>
              </select>
            </div>
          </div>
          <div className="flex justify-end">
            <button
              type="submit"
              disabled={createMutation.isPending || updateMutation.isPending}
              className="bg-accent text-[#0f172a] px-4 py-1.5 rounded-md text-sm font-medium disabled:opacity-50"
            >
              {editingId ? '保存修改' : '创建'}
            </button>
          </div>
        </form>
      )}

      <div className="bg-card border border-border rounded-lg overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border text-text3 text-left">
              <th className="px-4 py-3 font-medium">ID</th>
              <th className="px-4 py-3 font-medium">用户名</th>
              <th className="px-4 py-3 font-medium">显示名称</th>
              <th className="px-4 py-3 font-medium">角色</th>
              <th className="px-4 py-3 font-medium">创建时间</th>
              <th className="px-4 py-3 font-medium text-right">操作</th>
            </tr>
          </thead>
          <tbody>
            {isLoading ? (
              <tr>
                <td colSpan={6} className="px-4 py-8 text-center text-text3">
                  加载中...
                </td>
              </tr>
            ) : !data?.users.length ? (
              <tr>
                <td colSpan={6} className="px-4 py-8 text-center text-text3">
                  暂无用户
                </td>
              </tr>
            ) : (
              data.users.map((user) => (
                <tr key={user.id} className="border-b border-border hover:bg-bg2/50">
                  <td className="px-4 py-2.5 text-text3">{user.id}</td>
                  <td className="px-4 py-2.5 text-text font-medium">{user.username}</td>
                  <td className="px-4 py-2.5 text-text2">{user.display_name || '-'}</td>
                  <td className="px-4 py-2.5">
                    <span
                      className={`inline-block px-2 py-0.5 rounded text-xs font-medium ${
                        user.role === 'admin'
                          ? 'bg-accent-dim text-accent'
                          : 'bg-bg2 text-text3'
                      }`}
                    >
                      {user.role}
                    </span>
                  </td>
                  <td className="px-4 py-2.5 text-text3">{formatDate(user.created_at)}</td>
                  <td className="px-4 py-2.5 text-right">
                    <div className="flex justify-end gap-2">
                      <button
                        onClick={() => startEdit(user)}
                        className="px-2 py-1 rounded text-xs border border-border text-text2 hover:bg-bg2"
                      >
                        编辑
                      </button>
                      <button
                        onClick={() => {
                          if (confirm(`确认删除用户 ${user.username}？`)) {
                            deleteMutation.mutate(user.id)
                          }
                        }}
                        className="px-2 py-1 rounded text-xs border border-red/30 text-red hover:bg-red/10"
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

      {data && (
        <p className="text-xs text-text3">共 {data.count} 个面板用户</p>
      )}
    </div>
  )
}
