import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import client from '@/api/client'
import toast from 'react-hot-toast'
import { cn, formatDate } from '@/lib/utils'

/* ---------- types ---------- */

/** 通知渠道类型定义 (如 Telegram/Email) */
interface ChannelType {
  /** 类型唯一标识 */
  id: string
  /** 显示名称 */
  name: string
  /** 类型描述 */
  description: string
  /** 配置字段 schema */
  config_schema: Record<string, { type: string; label: string; required?: boolean; placeholder?: string }>
}

/** 通知渠道实例 */
interface Channel {
  /** 渠道 ID */
  id: number
  /** 渠道名称 */
  name: string
  /** 渠道类型标识 */
  channel_type: string
  /** 渠道配置 (如 bot_token, chat_id) */
  config: Record<string, string>
  /** 是否启用 */
  enabled: boolean
  /** 创建时间 */
  created_at: string
}

/** 通知发送历史记录 */
interface NotificationEntry {
  /** 记录 ID */
  id: number
  /** 通知标题 */
  title: string
  /** 通知内容 */
  message: string
  /** 级别: info/warning/critical */
  level: string
  /** 发送渠道名称 */
  channel_name: string
  /** 发送状态: success/failed */
  status: string
  /** 创建时间 */
  created_at: string
}

/* ---------- tab bar ---------- */

function TabBar({ tabs, active, onChange }: { tabs: { key: string; label: string }[]; active: string; onChange: (k: string) => void }) {
  return (
    <div className="flex gap-4 border-b border-border mb-4">
      {tabs.map((t) => (
        <button
          key={t.key}
          onClick={() => onChange(t.key)}
          className={cn(
            'pb-2 px-1 text-sm font-medium transition-colors',
            active === t.key ? 'border-b-2 border-accent text-accent' : 'border-b-2 border-transparent text-text3 hover:text-text',
          )}
        >
          {t.label}
        </button>
      ))}
    </div>
  )
}

/* ---------- Send Notification tab ---------- */

/** 发送通知标签页 — 选择渠道并发送通知 */
function SendNotificationTab() {
  const [form, setForm] = useState({ title: '', message: '', level: 'info', channels: [] as number[] })

  const { data: channelsData } = useQuery<{ channels: Channel[] }>({
    queryKey: ['channels'],
    queryFn: () => client.get('/api/notifications/channels').then((r) => r.data),
  })

  const sendMut = useMutation({
    mutationFn: () => client.post('/api/notifications/send', form).then((r) => r.data),
    onSuccess: (d: { summary: string }) => {
      toast.success(d.summary || '发送成功')
      setForm({ title: '', message: '', level: 'info', channels: [] })
    },
    onError: () => toast.error('发送失败'),
  })

  const channels = channelsData?.channels?.filter((c) => c.enabled) ?? []

  const toggleChannel = (id: number) => {
    setForm((f) => ({
      ...f,
      channels: f.channels.includes(id) ? f.channels.filter((c) => c !== id) : [...f.channels, id],
    }))
  }

  return (
    <div className="bg-card border border-border rounded-lg p-4 max-w-2xl">
      <div className="space-y-4">
        <div>
          <label className="text-text3 text-xs uppercase block mb-1">标题</label>
          <input
            value={form.title}
            onChange={(e) => setForm({ ...form, title: e.target.value })}
            placeholder="通知标题"
            className="bg-bg border border-border rounded-md px-3 py-2 text-sm text-text focus:border-accent focus:outline-none w-full"
          />
        </div>
        <div>
          <label className="text-text3 text-xs uppercase block mb-1">内容</label>
          <textarea
            value={form.message}
            onChange={(e) => setForm({ ...form, message: e.target.value })}
            placeholder="通知内容..."
            rows={4}
            className="bg-bg border border-border rounded-md px-3 py-2 text-sm text-text focus:border-accent focus:outline-none w-full resize-none"
          />
        </div>
        <div>
          <label className="text-text3 text-xs uppercase block mb-1">级别</label>
          <select
            value={form.level}
            onChange={(e) => setForm({ ...form, level: e.target.value })}
            className="bg-bg border border-border rounded-md px-3 py-2 text-sm text-text focus:border-accent focus:outline-none"
          >
            <option value="info">Info</option>
            <option value="warning">Warning</option>
            <option value="critical">Critical</option>
          </select>
        </div>
        <div>
          <label className="text-text3 text-xs uppercase block mb-1">发送渠道</label>
          <div className="flex flex-wrap gap-2">
            {channels.length === 0 ? (
              <p className="text-text3 text-sm">暂无可用渠道，请先在「通知渠道」中添加</p>
            ) : (
              channels.map((ch) => (
                <label key={ch.id} className="flex items-center gap-1.5 cursor-pointer text-sm">
                  <input
                    type="checkbox"
                    checked={form.channels.includes(ch.id)}
                    onChange={() => toggleChannel(ch.id)}
                    className="rounded border-border"
                  />
                  <span className="text-text2">{ch.name}</span>
                </label>
              ))
            )}
          </div>
        </div>
        <button
          onClick={() => sendMut.mutate()}
          disabled={!form.title || !form.message || form.channels.length === 0 || sendMut.isPending}
          className="bg-accent text-[#0f172a] px-4 py-2 rounded-md text-sm font-medium hover:opacity-90 disabled:opacity-50"
        >
          {sendMut.isPending ? '发送中...' : '发送通知'}
        </button>
      </div>
    </div>
  )
}

/* ---------- Channels tab ---------- */

/** 根据渠道类型的 schema 动态渲染配置字段表单 */
function ChannelConfigForm({
  schema,
  config,
  onChange,
}: {
  schema: Record<string, { type: string; label: string; required?: boolean; placeholder?: string }>
  config: Record<string, string>
  onChange: (cfg: Record<string, string>) => void
}) {
  return (
    <div className="space-y-2">
      {Object.entries(schema).map(([key, field]) => (
        <div key={key}>
          <label className="text-text3 text-xs block mb-0.5">
            {field.label} {field.required && <span className="text-red">*</span>}
          </label>
          <input
            type={field.type === 'password' ? 'password' : 'text'}
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

/** 通知渠道管理标签页 — 渠道 CRUD 和测试 */
function ChannelsTab() {
  const qc = useQueryClient()
  const [editingId, setEditingId] = useState<number | null>(null)
  const [showAdd, setShowAdd] = useState(false)
  const [addForm, setAddForm] = useState({ name: '', channel_type: '', config: {} as Record<string, string>, enabled: true })
  const [editForm, setEditForm] = useState({ name: '', config: {} as Record<string, string>, enabled: true })

  const { data: typesData } = useQuery<ChannelType[]>({
    queryKey: ['channel-types'],
    queryFn: async () => {
      const raw = (await client.get('/api/notifications/channel-types')).data
      // Backend returns {type_id: {display_name, config_schema}} object, transform to array
      if (Array.isArray(raw)) return raw
      return Object.entries(raw).map(([id, v]: [string, any]) => ({
        id,
        name: v.display_name ?? id,
        description: v.description ?? '',
        config_schema: v.config_schema ?? {},
      }))
    },
  })

  const { data: channelsData, isLoading } = useQuery<{ channels: Channel[] }>({
    queryKey: ['channels'],
    queryFn: () => client.get('/api/notifications/channels').then((r) => r.data),
  })

  const createMut = useMutation({
    mutationFn: () => client.post('/api/notifications/channels', addForm).then((r) => r.data),
    onSuccess: () => { toast.success('渠道已创建'); setShowAdd(false); setAddForm({ name: '', channel_type: '', config: {}, enabled: true }); qc.invalidateQueries({ queryKey: ['channels'] }) },
    onError: () => toast.error('创建失败'),
  })

  const updateMut = useMutation({
    mutationFn: () => client.put(`/api/notifications/channels/${editingId}`, editForm).then((r) => r.data),
    onSuccess: () => { toast.success('已更新'); setEditingId(null); qc.invalidateQueries({ queryKey: ['channels'] }) },
    onError: () => toast.error('更新失败'),
  })

  const deleteMut = useMutation({
    mutationFn: (id: number) => client.delete(`/api/notifications/channels/${id}`).then((r) => r.data),
    onSuccess: () => { toast.success('渠道已删除'); qc.invalidateQueries({ queryKey: ['channels'] }) },
    onError: () => toast.error('删除失败'),
  })

  const testMut = useMutation({
    mutationFn: (id: number) => client.post(`/api/notifications/channels/${id}/test`).then((r) => r.data),
    onSuccess: () => toast.success('测试消息已发送'),
    onError: () => toast.error('测试失败'),
  })

  const types = typesData ?? []
  const channels = channelsData?.channels ?? []

  const getSchema = (typeId: string) => types.find((t) => t.id === typeId)?.config_schema ?? {}

  if (isLoading) return <p className="text-text3 text-sm">加载中...</p>

  return (
    <>
      {!showAdd ? (
        <button onClick={() => setShowAdd(true)} className="bg-accent text-[#0f172a] px-3 py-1.5 rounded-md text-sm font-medium hover:opacity-90 mb-4">
          + 添加渠道
        </button>
      ) : (
        <div className="bg-card border border-border rounded-lg p-4 mb-4">
          <h3 className="text-sm font-medium mb-3">新增通知渠道</h3>
          <div className="space-y-3">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <input
                value={addForm.name}
                onChange={(e) => setAddForm({ ...addForm, name: e.target.value })}
                placeholder="渠道名称"
                className="bg-bg border border-border rounded-md px-3 py-2 text-sm text-text focus:border-accent focus:outline-none"
              />
              <select
                value={addForm.channel_type}
                onChange={(e) => setAddForm({ ...addForm, channel_type: e.target.value, config: {} })}
                className="bg-bg border border-border rounded-md px-3 py-2 text-sm text-text focus:border-accent focus:outline-none"
              >
                <option value="">选择渠道类型</option>
                {types.map((t) => (
                  <option key={t.id} value={t.id}>{t.name}</option>
                ))}
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
              <button onClick={() => createMut.mutate()} disabled={!addForm.name || !addForm.channel_type || createMut.isPending} className="bg-accent text-[#0f172a] px-3 py-1.5 rounded-md text-sm font-medium hover:opacity-90 disabled:opacity-50">
                创建
              </button>
              <button onClick={() => setShowAdd(false)} className="text-text3 px-3 py-1.5 text-sm hover:text-text">取消</button>
            </div>
          </div>
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        {channels.map((ch) => {
          const isEditing = editingId === ch.id
          const typeName = types.find((t) => t.id === ch.channel_type)?.name ?? ch.channel_type

          return (
            <div key={ch.id} className="bg-card border border-border rounded-lg p-4">
              {isEditing ? (
                <div className="space-y-3">
                  <input
                    value={editForm.name}
                    onChange={(e) => setEditForm({ ...editForm, name: e.target.value })}
                    className="bg-bg border border-border rounded-md px-3 py-2 text-sm text-text focus:border-accent focus:outline-none w-full"
                  />
                  <ChannelConfigForm
                    schema={getSchema(ch.channel_type)}
                    config={editForm.config}
                    onChange={(cfg) => setEditForm({ ...editForm, config: cfg })}
                  />
                  <label className="flex items-center gap-2 text-sm cursor-pointer">
                    <input type="checkbox" checked={editForm.enabled} onChange={() => setEditForm({ ...editForm, enabled: !editForm.enabled })} className="rounded border-border" />
                    <span className="text-text2">启用</span>
                  </label>
                  <div className="flex gap-2">
                    <button onClick={() => updateMut.mutate()} className="bg-accent text-[#0f172a] px-3 py-1 rounded-md text-xs font-medium hover:opacity-90">保存</button>
                    <button onClick={() => setEditingId(null)} className="text-text3 text-xs hover:text-text">取消</button>
                  </div>
                </div>
              ) : (
                <>
                  <div className="flex items-center justify-between mb-2">
                    <span className="font-medium text-text">{ch.name}</span>
                    <span className={cn('px-2 py-0.5 rounded text-xs font-medium', ch.enabled ? 'bg-green/20 text-green' : 'bg-text3/20 text-text3')}>
                      {ch.enabled ? '启用' : '禁用'}
                    </span>
                  </div>
                  <div className="mb-3">
                    <span className="px-2 py-0.5 rounded text-xs font-medium bg-accent-dim text-accent">{typeName}</span>
                    <span className="text-text3 text-xs ml-2">{formatDate(ch.created_at)}</span>
                  </div>
                  <div className="flex gap-2">
                    <button onClick={() => testMut.mutate(ch.id)} disabled={testMut.isPending} className="text-accent text-xs hover:underline">测试</button>
                    <button onClick={() => { setEditingId(ch.id); setEditForm({ name: ch.name, config: { ...ch.config }, enabled: ch.enabled }) }} className="text-yellow text-xs hover:underline">编辑</button>
                    <button onClick={() => { if (confirm(`删除渠道 ${ch.name}?`)) deleteMut.mutate(ch.id) }} className="text-red text-xs hover:underline">删除</button>
                  </div>
                </>
              )}
            </div>
          )
        })}
      </div>

      {channels.length === 0 && <p className="text-text3 text-sm mt-2">暂无通知渠道</p>}
    </>
  )
}

/* ---------- History tab ---------- */

/** 通知发送历史标签页 — 展示最近 30 条发送记录 */
function HistoryTab() {
  const { data, isLoading } = useQuery<{ notifications: NotificationEntry[]; count: number }>({
    queryKey: ['notification-history'],
    queryFn: () => client.get('/api/notifications/history', { params: { limit: 30 } }).then((r) => r.data),
  })

  if (isLoading) return <p className="text-text3 text-sm">加载中...</p>

  const entries = data?.notifications ?? []
  if (entries.length === 0) return <p className="text-text3 text-sm">暂无发送记录</p>

  const levelStyle = (level: string) => {
    switch (level) {
      case 'critical': return 'bg-red/20 text-red'
      case 'warning': return 'bg-yellow/20 text-yellow'
      default: return 'bg-accent-dim text-accent'
    }
  }

  return (
    <div className="bg-card border border-border rounded-lg p-4">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-border">
            <th className="text-text3 text-left text-xs uppercase py-2">时间</th>
            <th className="text-text3 text-left text-xs uppercase py-2">标题</th>
            <th className="text-text3 text-left text-xs uppercase py-2">级别</th>
            <th className="text-text3 text-left text-xs uppercase py-2">渠道</th>
            <th className="text-text3 text-left text-xs uppercase py-2">状态</th>
          </tr>
        </thead>
        <tbody>
          {entries.map((n) => (
            <tr key={n.id} className="border-b border-border">
              <td className="py-2 text-text2 text-xs whitespace-nowrap">{formatDate(n.created_at)}</td>
              <td className="py-2 text-text max-w-xs truncate" title={n.title}>{n.title}</td>
              <td className="py-2">
                <span className={cn('px-2 py-0.5 rounded text-xs font-medium', levelStyle(n.level))}>{n.level}</span>
              </td>
              <td className="py-2 text-text2">{n.channel_name}</td>
              <td className="py-2">
                <span className={cn('px-2 py-0.5 rounded text-xs font-medium', n.status === 'success' ? 'bg-green/20 text-green' : 'bg-red/20 text-red')}>
                  {n.status === 'success' ? '成功' : '失败'}
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

/* ---------- main page ---------- */

/**
 * 通知管理页面
 * 提供通知发送、通知渠道管理 (CRUD/测试) 和发送历史查看三大标签页
 * API 前缀: /api/notifications
 */
export default function NotificationsPage() {
  const [activeTab, setActiveTab] = useState('send')

  return (
    <div>
      <h2 className="text-lg font-semibold mb-4">通知管理</h2>

      <TabBar
        tabs={[
          { key: 'send', label: '发送通知' },
          { key: 'channels', label: '通知渠道' },
          { key: 'history', label: '发送历史' },
        ]}
        active={activeTab}
        onChange={setActiveTab}
      />

      {activeTab === 'send' && <SendNotificationTab />}
      {activeTab === 'channels' && <ChannelsTab />}
      {activeTab === 'history' && <HistoryTab />}
    </div>
  )
}
