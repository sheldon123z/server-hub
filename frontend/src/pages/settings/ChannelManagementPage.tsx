import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import client from '@/api/client'
import toast from 'react-hot-toast'
import { cn, formatDate } from '@/lib/utils'

/* ---------- types ---------- */

interface ChannelType {
  id: string
  name: string
  config_schema: Record<string, { type: string; label: string; required?: boolean; placeholder?: string; sensitive?: boolean }>
}

interface Channel {
  id: string
  channel_type: string
  display_name: string
  config: Record<string, string>
  enabled: boolean
  priority: number
  last_test_at: string | null
  last_test_ok: boolean | null
  created_at: string
}

/* ---------- helpers ---------- */

function ChannelConfigForm({
  schema,
  config,
  onChange,
}: {
  schema: Record<string, { type: string; label: string; required?: boolean; placeholder?: string; sensitive?: boolean }>
  config: Record<string, string>
  onChange: (cfg: Record<string, string>) => void
}) {
  if (Object.keys(schema).length === 0) return null
  return (
    <div className="space-y-2">
      {Object.entries(schema).map(([key, field]) => (
        <div key={key}>
          <label className="text-text3 text-xs block mb-0.5">
            {field.label} {field.required && <span className="text-red">*</span>}
          </label>
          <input
            type={field.sensitive ? 'password' : 'text'}
            value={config[key] || ''}
            onChange={(e) => onChange({ ...config, [key]: e.target.value })}
            placeholder={field.placeholder || ''}
            className="bg-bg border border-border rounded-md px-3 py-1.5 text-sm text-text focus:border-accent focus:outline-none w-full"
          />
        </div>
      ))}
    </div>
  )
}

/* ---------- main page ---------- */

/**
 * 通知渠道管理页
 * 提供渠道 CRUD、连通性测试和发送历史查看
 * 路由: /settings/channels
 */
export default function ChannelManagementPage() {
  const qc = useQueryClient()
  const [editingId, setEditingId] = useState<string | null>(null)
  const [showAdd, setShowAdd] = useState(false)
  const [addForm, setAddForm] = useState({ display_name: '', channel_type: '', config: {} as Record<string, string>, enabled: true })
  const [editForm, setEditForm] = useState({ display_name: '', config: {} as Record<string, string>, enabled: true })

  const { data: typesData } = useQuery<ChannelType[]>({
    queryKey: ['channel-types'],
    queryFn: async () => {
      const raw = (await client.get('/api/notifications/channel-types')).data
      if (Array.isArray(raw)) return raw
      return Object.entries(raw).map(([id, v]: [string, any]) => ({
        id,
        name: v.display_name ?? id,
        config_schema: v.config_schema ?? {},
      }))
    },
  })

  const { data: channelsData, isLoading } = useQuery<{ channels: Channel[] }>({
    queryKey: ['channels'],
    queryFn: () => client.get('/api/notifications/channels').then((r) => r.data),
  })

  const createMut = useMutation({
    mutationFn: () =>
      client.post('/api/notifications/channels', {
        channel_type: addForm.channel_type,
        display_name: addForm.display_name,
        config: addForm.config,
        enabled: addForm.enabled,
      }).then((r) => r.data),
    onSuccess: () => {
      toast.success('渠道已创建')
      setShowAdd(false)
      setAddForm({ display_name: '', channel_type: '', config: {}, enabled: true })
      qc.invalidateQueries({ queryKey: ['channels'] })
    },
    onError: () => toast.error('创建失败'),
  })

  const updateMut = useMutation({
    mutationFn: () =>
      client.put(`/api/notifications/channels/${editingId}`, {
        display_name: editForm.display_name,
        config: editForm.config,
        enabled: editForm.enabled,
      }).then((r) => r.data),
    onSuccess: () => { toast.success('已更新'); setEditingId(null); qc.invalidateQueries({ queryKey: ['channels'] }) },
    onError: () => toast.error('更新失败'),
  })

  const deleteMut = useMutation({
    mutationFn: (id: string) => client.delete(`/api/notifications/channels/${id}`).then((r) => r.data),
    onSuccess: () => { toast.success('渠道已删除'); qc.invalidateQueries({ queryKey: ['channels'] }) },
    onError: () => toast.error('删除失败'),
  })

  const testMut = useMutation({
    mutationFn: (id: string) => client.post(`/api/notifications/channels/${id}/test`).then((r) => r.data),
    onSuccess: (d: { success: boolean; error?: string }) => {
      if (d.success) toast.success('测试消息发送成功')
      else toast.error(`测试失败: ${d.error ?? '未知错误'}`)
      qc.invalidateQueries({ queryKey: ['channels'] })
    },
    onError: () => toast.error('测试请求失败'),
  })

  const types = typesData ?? []
  const channels = channelsData?.channels ?? []
  const getSchema = (typeId: string) => types.find((t) => t.id === typeId)?.config_schema ?? {}

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-semibold">通知渠道</h2>
        {!showAdd && (
          <button
            onClick={() => setShowAdd(true)}
            className="bg-accent text-[#0f172a] px-3 py-1.5 rounded-md text-sm font-medium hover:opacity-90"
          >
            + 添加渠道
          </button>
        )}
      </div>

      {/* 新增表单 */}
      {showAdd && (
        <div className="bg-card border border-border rounded-lg p-4 mb-4">
          <h3 className="text-sm font-medium mb-3">新增通知渠道</h3>
          <div className="space-y-3">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <input
                value={addForm.display_name}
                onChange={(e) => setAddForm({ ...addForm, display_name: e.target.value })}
                placeholder="渠道名称"
                className="bg-bg border border-border rounded-md px-3 py-2 text-sm text-text focus:border-accent focus:outline-none"
              />
              <select
                value={addForm.channel_type}
                onChange={(e) => setAddForm({ ...addForm, channel_type: e.target.value, config: {} })}
                className="bg-bg border border-border rounded-md px-3 py-2 text-sm text-text focus:border-accent focus:outline-none"
              >
                <option value="">选择渠道类型</option>
                {types.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
              </select>
            </div>
            {addForm.channel_type && (
              <ChannelConfigForm
                schema={getSchema(addForm.channel_type)}
                config={addForm.config}
                onChange={(cfg) => setAddForm({ ...addForm, config: cfg })}
              />
            )}
            <div className="flex gap-2">
              <button
                onClick={() => createMut.mutate()}
                disabled={!addForm.display_name || !addForm.channel_type || createMut.isPending}
                className="bg-accent text-[#0f172a] px-3 py-1.5 rounded-md text-sm font-medium hover:opacity-90 disabled:opacity-50"
              >
                创建
              </button>
              <button onClick={() => setShowAdd(false)} className="text-text3 px-3 py-1.5 text-sm hover:text-text">
                取消
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 渠道列表 */}
      {isLoading ? (
        <p className="text-text3 text-sm">加载中...</p>
      ) : channels.length === 0 ? (
        <p className="text-text3 text-sm mt-2">暂无通知渠道</p>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {channels.map((ch) => {
            const isEditing = editingId === ch.id
            const typeName = types.find((t) => t.id === ch.channel_type)?.name ?? ch.channel_type

            return (
              <div key={ch.id} className="bg-card border border-border rounded-lg p-4">
                {isEditing ? (
                  <div className="space-y-3">
                    <input
                      value={editForm.display_name}
                      onChange={(e) => setEditForm({ ...editForm, display_name: e.target.value })}
                      className="bg-bg border border-border rounded-md px-3 py-2 text-sm text-text focus:border-accent focus:outline-none w-full"
                    />
                    <ChannelConfigForm
                      schema={getSchema(ch.channel_type)}
                      config={editForm.config}
                      onChange={(cfg) => setEditForm({ ...editForm, config: cfg })}
                    />
                    <label className="flex items-center gap-2 text-sm cursor-pointer">
                      <input
                        type="checkbox"
                        checked={editForm.enabled}
                        onChange={() => setEditForm({ ...editForm, enabled: !editForm.enabled })}
                        className="rounded border-border"
                      />
                      <span className="text-text2">启用</span>
                    </label>
                    <div className="flex gap-2">
                      <button onClick={() => updateMut.mutate()} className="bg-accent text-[#0f172a] px-3 py-1 rounded-md text-xs font-medium hover:opacity-90">
                        保存
                      </button>
                      <button onClick={() => setEditingId(null)} className="text-text3 text-xs hover:text-text">
                        取消
                      </button>
                    </div>
                  </div>
                ) : (
                  <>
                    <div className="flex items-center justify-between mb-2">
                      <span className="font-medium text-text">{ch.display_name}</span>
                      <span className={cn('px-2 py-0.5 rounded text-xs font-medium', ch.enabled ? 'bg-green/20 text-green' : 'bg-text3/20 text-text3')}>
                        {ch.enabled ? '启用' : '禁用'}
                      </span>
                    </div>
                    <div className="flex items-center gap-2 mb-1">
                      <span className="px-2 py-0.5 rounded text-xs font-medium bg-accent-dim text-accent">{typeName}</span>
                      <span className="text-text3 text-xs">{formatDate(ch.created_at)}</span>
                    </div>
                    {ch.last_test_at && (
                      <div className="text-[10px] text-text3 mb-2">
                        上次测试: {formatDate(ch.last_test_at)}
                        <span className={cn('ml-1', ch.last_test_ok ? 'text-green' : 'text-red')}>
                          {ch.last_test_ok ? '成功' : '失败'}
                        </span>
                      </div>
                    )}
                    <div className="flex gap-2">
                      <button
                        onClick={() => testMut.mutate(ch.id)}
                        disabled={testMut.isPending}
                        className="text-accent text-xs hover:underline"
                      >
                        测试
                      </button>
                      <button
                        onClick={() => {
                          setEditingId(ch.id)
                          setEditForm({ display_name: ch.display_name, config: { ...ch.config }, enabled: ch.enabled })
                        }}
                        className="text-yellow text-xs hover:underline"
                      >
                        编辑
                      </button>
                      <button
                        onClick={() => { if (confirm(`删除渠道 ${ch.display_name}?`)) deleteMut.mutate(ch.id) }}
                        className="text-red text-xs hover:underline"
                      >
                        删除
                      </button>
                    </div>
                  </>
                )}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
