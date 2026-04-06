/**
 * 服务器管理页面 — 多服务器舰队管理
 *
 * 功能: 服务器 CRUD / 连通性测试 / 分组管理 / 状态概览
 * API 前缀: /api/servers
 */

import { useState, useMemo, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import client from '@/api/client'
import toast from 'react-hot-toast'
import { cn, formatDate, getErrorMessage } from '@/lib/utils'

/* ─── 类型定义 ─── */

interface Server {
  id: string
  name: string
  hostname: string
  ip_address: string
  agent_port: number
  ssh_user: string
  ssh_port: number
  status: string
  is_local: number | boolean
  tags: string | string[]
  groups: string
  last_heartbeat: string | null
  os_info: string | null
  agent_version: string | null
  created_at: string
  updated_at: string
}

interface ServerOverview {
  total: number
  online: number
  offline: number
  degraded: number
  auth_failed: number
}

interface ConnectivityResult {
  ping_ok: boolean
  ping_ms: number | null
  ssh_ok: boolean
  ssh_error: string | null
  agent_ok: boolean
  agent_version: string | null
}

interface ServerGroup {
  id: string
  name: string
  description: string
  server_count: number
}

interface ServerFormData {
  name: string
  hostname: string
  ip_address: string
  agent_port: number
  ssh_user: string
  ssh_port: number
  ssh_password: string
  tags: string
}

/* ─── 工具函数 ─── */

/** 判断服务器是否为本机（兼容 bool 和 number） */
function isLocalServer(srv: Server): boolean {
  return srv.is_local === 1 || srv.is_local === true
}

/** 将 tags 统一解析为字符串数组（兼容 string / string[] / JSON string） */
function parseTags(tags: string | string[] | undefined | null): string[] {
  if (!tags) return []
  if (Array.isArray(tags)) return tags.filter(Boolean)
  try {
    const parsed = JSON.parse(tags)
    if (Array.isArray(parsed)) return parsed.filter(Boolean)
  } catch { /* not JSON */ }
  return tags.split(',').map((t) => t.trim()).filter(Boolean)
}

/* ─── 状态颜色 ─── */

const STATUS_DOT: Record<string, string> = {
  online: 'bg-green',
  offline: 'bg-red',
  degraded: 'bg-yellow',
  auth_failed: 'bg-orange',
  unknown: 'bg-text3',
}

const STATUS_LABEL: Record<string, string> = {
  online: '在线',
  offline: '离线',
  degraded: '降级',
  auth_failed: '认证失败',
  unknown: '未知',
}

const STATUS_ICON: Record<string, string> = {
  online: 'ti-circle-check',
  offline: 'ti-circle-x',
  degraded: 'ti-alert-triangle',
  auth_failed: 'ti-lock',
  unknown: 'ti-help',
}

/* ─── 空表单 ─── */

const emptyForm: ServerFormData = {
  name: '',
  hostname: '',
  ip_address: '',
  agent_port: 9901,
  ssh_user: '',
  ssh_port: 22,
  ssh_password: '',
  tags: '',
}

/* ─── 主页面 ─── */

export default function ServersPage() {
  const queryClient = useQueryClient()
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [search, setSearch] = useState('')
  const [showAddModal, setShowAddModal] = useState(false)
  const [showEditModal, setShowEditModal] = useState(false)
  const [testResult, setTestResult] = useState<ConnectivityResult | null>(null)
  const [newToken, setNewToken] = useState<string | null>(null)
  const [deployLog, setDeployLog] = useState('')
  const [showPushUpdateConfirm, setShowPushUpdateConfirm] = useState(false)

  /* ── 数据查询 ── */

  const { data: servers = [], isLoading } = useQuery<Server[]>({
    queryKey: ['servers'],
    queryFn: async () => {
      const res = await client.get('/api/servers')
      return Array.isArray(res.data) ? res.data : res.data?.servers ?? []
    },
    refetchInterval: 30_000,
  })

  const { data: overview } = useQuery<ServerOverview>({
    queryKey: ['servers', 'overview'],
    queryFn: async () => {
      const res = await client.get('/api/servers/overview')
      return res.data
    },
    refetchInterval: 30_000,
  })

  const { data: groups = [] } = useQuery<ServerGroup[]>({
    queryKey: ['server-groups'],
    queryFn: async () => {
      const res = await client.get('/api/servers/groups')
      return Array.isArray(res.data) ? res.data : res.data?.groups ?? []
    },
  })

  /* ── Mutations ── */

  const deleteMut = useMutation({
    mutationFn: (id: string) => client.delete(`/api/servers/${id}`),
    onSuccess: () => {
      toast.success('已删除')
      queryClient.invalidateQueries({ queryKey: ['servers'] })
      setSelectedId(null)
    },
    onError: (err: unknown) => toast.error(getErrorMessage(err, '删除失败')),
  })

  const testMut = useMutation({
    mutationFn: (id: string) => client.post(`/api/servers/${id}/test`),
    onSuccess: (res) => {
      setTestResult(res.data)
      toast.success('测试完成')
    },
    onError: (err: unknown) => toast.error(getErrorMessage(err, '测试失败')),
  })

  const pushUpdateMut = useMutation({
    mutationFn: (id: string) => client.post(`/api/servers/${id}/push-update`),
    onSuccess: (res) => {
      const data = res.data as { ok: boolean; message?: string; results?: { file: string; ok: boolean }[] }
      if (data.ok) {
        toast.success(data.message ?? '推送更新成功')
      } else {
        toast.error(data.message ?? '推送更新失败')
      }
      setShowPushUpdateConfirm(false)
    },
    onError: (err: unknown) => {
      toast.error(getErrorMessage(err, '推送更新失败'))
      setShowPushUpdateConfirm(false)
    },
  })

  /* ── 过滤 ── */

  const filtered = useMemo(() => {
    if (!search) return servers
    const q = search.toLowerCase()
    return servers.filter(
      (s) =>
        s.name.toLowerCase().includes(q) ||
        s.ip_address.toLowerCase().includes(q) ||
        s.hostname.toLowerCase().includes(q) ||
        (s.tags && (Array.isArray(s.tags) ? s.tags.join(',') : s.tags).toLowerCase().includes(q))
    )
  }, [servers, search])

  const selected = servers.find((s) => s.id === selectedId) ?? null

  // 当选中的服务器变化时清除测试结果
  useEffect(() => {
    setTestResult(null)
  }, [selectedId])

  if (isLoading) return <div className="text-text3 text-sm">加载中...</div>

  return (
    <div>
      {/* ── 顶部概览卡片 ── */}
      <div className="grid grid-cols-5 gap-4 mb-5">
        <StatCard label="总计" value={overview?.total ?? servers.length} icon="server-2" color="text-accent" />
        <StatCard label="在线" value={overview?.online ?? 0} icon="circle-check" color="text-green" />
        <StatCard label="离线" value={overview?.offline ?? 0} icon="circle-x" color="text-red" />
        <StatCard label="认证失败" value={overview?.auth_failed ?? 0} icon="lock" color="text-orange" />
        <StatCard label="降级" value={overview?.degraded ?? 0} icon="alert-triangle" color="text-yellow" />
      </div>

      {/* ── 左右分栏 ── */}
      <div className="grid grid-cols-12 gap-4" style={{ height: 'calc(100vh - 260px)' }}>
        {/* 左侧: 服务器列表 */}
        <div className="col-span-4 border-r border-border pr-4 overflow-y-auto">
          <div className="flex items-center gap-2 mb-3">
            <input
              type="text"
              placeholder="搜索服务器\u2026"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="flex-1 bg-bg border border-border rounded-md px-3 py-1.5 text-xs text-text placeholder:text-text3 focus:outline-none focus:border-accent"
            />
            <button
              onClick={() => setShowAddModal(true)}
              aria-label="添加服务器"
              className="bg-accent text-[#0f172a] px-3 py-1.5 rounded-md text-xs font-medium shrink-0"
            >
              +
            </button>
          </div>

          {filtered.length === 0 ? (
            <div className="text-text3 text-xs text-center py-8">无匹配服务器</div>
          ) : (
            filtered.map((srv) => (
              <button
                key={srv.id}
                type="button"
                onClick={() => setSelectedId(srv.id)}
                aria-pressed={selectedId === srv.id}
                className={cn(
                  'w-full text-left p-3 rounded-lg cursor-pointer mb-2 transition-colors border',
                  'focus-visible:outline-2 focus-visible:outline-accent focus-visible:outline-offset-2',
                  selectedId === srv.id
                    ? 'bg-accent-dim border-accent/30'
                    : 'bg-card border-border hover:border-border-light'
                )}
              >
                <div className="flex items-center gap-2">
                  <span className={cn('w-2 h-2 rounded-full shrink-0', STATUS_DOT[srv.status] ?? STATUS_DOT.unknown)} />
                  <span className="text-sm font-medium text-text truncate">{srv.name}</span>
                  {isLocalServer(srv) && (
                    <span className="text-[10px] text-accent bg-accent-dim px-1.5 py-0.5 rounded shrink-0">本机</span>
                  )}
                </div>
                <div className="text-xs text-text3 mt-1 ml-4">{srv.ip_address}</div>
                {parseTags(srv.tags).length > 0 && (
                  <div className="flex gap-1 mt-1.5 ml-4 flex-wrap">
                    {parseTags(srv.tags).map((t) => (
                      <span key={t} className="text-[10px] text-text3 bg-bg2 px-1.5 py-0.5 rounded">
                        {t}
                      </span>
                    ))}
                  </div>
                )}
              </button>
            ))
          )}
        </div>

        {/* 右侧: 服务器详情 */}
        <div className="col-span-8 overflow-y-auto">
          {!selected ? (
            <div className="flex items-center justify-center h-full text-text3 text-sm">
              选择一个服务器查看详情
            </div>
          ) : (
            <ServerDetail
              server={selected}
              groups={groups}
              testResult={testResult}
              onTest={() => testMut.mutate(selected.id)}
              isTesting={testMut.isPending}
              onEdit={() => setShowEditModal(true)}
              onDelete={() => {
                if (confirm('确认删除此服务器？')) deleteMut.mutate(selected.id)
              }}
              onTokenRotated={(token) => setNewToken(token)}
              onPushUpdate={() => setShowPushUpdateConfirm(true)}
              isPushingUpdate={pushUpdateMut.isPending}
            />
          )}
        </div>
      </div>

      {/* ── Modals ── */}
      {showAddModal && (
        <ServerFormModal
          title="添加服务器"
          initial={emptyForm}
          onClose={() => setShowAddModal(false)}
          onSubmit={async (data) => {
            if (data.ssh_password) {
              // 有密码 → 使用一键部署 API
              const res = await client.post('/api/servers/deploy', data)
              queryClient.invalidateQueries({ queryKey: ['servers'] })
              toast.success('服务器添加并部署成功')
              setShowAddModal(false)
              // 显示部署日志
              if (res.data?.deploy_log) {
                setDeployLog(res.data.deploy_log)
              }
            } else {
              // 无密码 → 仅注册（现有逻辑）
              const res = await client.post('/api/servers', data)
              queryClient.invalidateQueries({ queryKey: ['servers'] })
              toast.success('添加成功')
              setShowAddModal(false)
              if (res.data?.agent_token) {
                setNewToken(res.data.agent_token)
              }
            }
          }}
        />
      )}
      {showEditModal && selected && (
        <ServerFormModal
          title="编辑服务器"
          initial={{
            name: selected.name,
            hostname: selected.hostname ?? '',
            ip_address: selected.ip_address,
            agent_port: selected.agent_port,
            ssh_user: selected.ssh_user,
            ssh_port: selected.ssh_port,
            ssh_password: '',
            tags: parseTags(selected.tags).join(', '),
          }}
          onClose={() => setShowEditModal(false)}
          onSubmit={async (data) => {
            await client.put(`/api/servers/${selected.id}`, data)
            queryClient.invalidateQueries({ queryKey: ['servers'] })
            toast.success('更新成功')
            setShowEditModal(false)
          }}
        />
      )}
      {newToken && (
        <TokenDisplayModal token={newToken} onClose={() => setNewToken(null)} />
      )}
      {deployLog && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50" onClick={() => setDeployLog('')}>
          <div className="bg-bg border border-border rounded-xl p-6 w-full max-w-lg shadow-xl" onClick={e => e.stopPropagation()}>
            <h3 className="text-base font-semibold text-text mb-3">部署日志</h3>
            <pre className="bg-bg2 rounded-md p-3 text-xs text-text2 max-h-80 overflow-y-auto whitespace-pre-wrap">
              {deployLog}
            </pre>
            <button onClick={() => setDeployLog('')} className="mt-3 px-4 py-2 text-sm bg-accent text-[#0f172a] rounded-md font-medium">
              关闭
            </button>
          </div>
        </div>
      )}
      {showPushUpdateConfirm && selected && (
        <PushUpdateConfirmModal
          serverName={selected.name}
          isPending={pushUpdateMut.isPending}
          onConfirm={() => pushUpdateMut.mutate(selected.id)}
          onClose={() => setShowPushUpdateConfirm(false)}
        />
      )}
    </div>
  )
}

/* ─── 统计卡片 ─── */

function StatCard({ label, value, icon, color }: { label: string; value: number; icon: string; color: string }) {
  return (
    <div className="bg-card border border-border rounded-lg p-4">
      <div className="flex items-center justify-between">
        <div>
          <div className="text-xs text-text3">{label}</div>
          <div className={cn('text-2xl font-bold mt-1', color)}>{value}</div>
        </div>
        <i className={cn(`ti ti-${icon} text-2xl`, color)} />
      </div>
    </div>
  )
}

/* ─── 服务器详情 ─── */

function ServerDetail({
  server,
  groups,
  testResult,
  onTest,
  isTesting,
  onEdit,
  onDelete,
  onTokenRotated,
  onPushUpdate,
  isPushingUpdate,
}: {
  server: Server
  groups: ServerGroup[]
  testResult: ConnectivityResult | null
  onTest: () => void
  isTesting: boolean
  onEdit: () => void
  onDelete: () => void
  onTokenRotated: (token: string) => void
  onPushUpdate: () => void
  isPushingUpdate: boolean
}) {
  const queryClient = useQueryClient()
  const [rotating, setRotating] = useState(false)

  const serverGroups = server.groups
    ? server.groups.split(',').filter(Boolean).map((g) => g.trim())
    : []

  // 分组中已包含的 group name 列表，用于判断可添加/可移除
  const serverGroupNames = new Set(serverGroups)

  const handleRotateToken = async () => {
    if (!confirm('轮换 Token 后，旧 Token 立即失效。确认继续？')) return
    setRotating(true)
    try {
      const res = await client.post(`/api/servers/${server.id}/rotate-token`)
      if (res.data?.token) {
        onTokenRotated(res.data.token)
        toast.success('Token 已轮换')
      }
    } catch (err: unknown) {
      toast.error(getErrorMessage(err, 'Token 轮换失败'))
    } finally {
      setRotating(false)
    }
  }

  const handleAddToGroup = async (groupId: string) => {
    try {
      await client.post(`/api/servers/groups/${groupId}/members`, { server_id: server.id })
      queryClient.invalidateQueries({ queryKey: ['servers'] })
      toast.success('已添加到分组')
    } catch (err: unknown) {
      toast.error(getErrorMessage(err, '操作失败'))
    }
  }

  const handleRemoveFromGroup = async (groupId: string) => {
    try {
      await client.delete(`/api/servers/groups/${groupId}/members/${server.id}`)
      queryClient.invalidateQueries({ queryKey: ['servers'] })
      toast.success('已从分组移除')
    } catch (err: unknown) {
      toast.error(getErrorMessage(err, '操作失败'))
    }
  }

  return (
    <div>
      {/* 标题 + 操作按钮 */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-3">
          <span className={cn('w-3 h-3 rounded-full', STATUS_DOT[server.status] ?? STATUS_DOT.unknown)} />
          <div>
            <h3 className="text-lg font-semibold text-text">{server.name}</h3>
            <span className="text-xs text-text3 inline-flex items-center gap-1">
              {server.status === 'auth_failed' && <i className="ti ti-lock text-orange" />}
              {STATUS_LABEL[server.status] ?? '未知'}
            </span>
          </div>
          {isLocalServer(server) && (
            <span className="text-xs text-accent bg-accent-dim px-2 py-0.5 rounded">本机 Hub</span>
          )}
        </div>
        <div className="flex gap-2">
          <button
            onClick={onTest}
            disabled={isTesting}
            className="bg-accent-dim text-accent px-3 py-1.5 rounded-md text-sm font-medium hover:bg-accent/20 disabled:opacity-50"
          >
            {isTesting ? '测试中...' : '测试连通性'}
          </button>
          <button
            onClick={handleRotateToken}
            disabled={rotating}
            className="bg-bg2 text-text2 px-3 py-1.5 rounded-md text-sm hover:text-text hover:bg-bg2/80 disabled:opacity-50"
          >
            {rotating ? '轮换中...' : '轮换 Token'}
          </button>
          {!isLocalServer(server) && (
            <button
              onClick={onPushUpdate}
              disabled={isPushingUpdate}
              className="bg-blue/10 text-blue-400 px-3 py-1.5 rounded-md text-sm hover:bg-blue/20 disabled:opacity-50 inline-flex items-center gap-1.5"
            >
              <i className="ti ti-cloud-upload" />
              {isPushingUpdate ? '推送中...' : '推送更新'}
            </button>
          )}
          <button
            onClick={onEdit}
            className="bg-bg2 text-text2 px-3 py-1.5 rounded-md text-sm hover:text-text hover:bg-bg2/80"
          >
            编辑
          </button>
          {!isLocalServer(server) && (
            <button
              onClick={onDelete}
              className="bg-red/20 text-red px-3 py-1.5 rounded-md text-sm hover:bg-red/30"
            >
              删除
            </button>
          )}
        </div>
      </div>

      {/* 信息卡片网格 */}
      <div className="grid grid-cols-3 gap-3 mb-4">
        <InfoCard label="主机名" value={server.hostname || '-'} />
        <InfoCard label="IP 地址" value={server.ip_address} />
        <InfoCard label="操作系统" value={server.os_info || '-'} />
        <InfoCard label="Agent 版本" value={server.agent_version || '-'} />
        <InfoCard label="最后心跳" value={server.last_heartbeat ? formatDate(server.last_heartbeat) : '-'} />
        <InfoCard label="状态" value={STATUS_LABEL[server.status] ?? '未知'} />
        <InfoCard label="Agent 端口" value={String(server.agent_port)} />
        <InfoCard label="SSH 用户" value={server.ssh_user || '-'} />
        <InfoCard label="SSH 端口" value={String(server.ssh_port)} />
      </div>

      {/* 连通性测试结果 */}
      {testResult && (
        <div className="mb-4">
          <h4 className="text-sm font-medium text-text mb-2">连通性测试结果</h4>
          <div className="grid grid-cols-3 gap-3">
            <TestResultCard
              label="Ping"
              ok={testResult.ping_ok}
              detail={testResult.ping_ok ? `${testResult.ping_ms}ms` : '不可达'}
            />
            <TestResultCard
              label="SSH (可选)"
              ok={testResult.ssh_ok === true ? true : (testResult.ssh_error ? false : null)}
              detail={testResult.ssh_ok ? '密钥认证正常' : (testResult.ssh_error || '未配置密钥（不影响功能）')}
            />
            <TestResultCard
              label="Agent"
              ok={testResult.agent_ok}
              detail={testResult.agent_ok ? `v${testResult.agent_version}` : '不可用'}
            />
          </div>
        </div>
      )}

      {/* 所属分组 */}
      <div className="mb-4">
        <h4 className="text-sm font-medium text-text mb-2">所属分组</h4>
        <div className="flex gap-2 flex-wrap">
          {serverGroups.length === 0 ? (
            <span className="text-xs text-text3">暂无分组</span>
          ) : (
            serverGroups.map((g) => {
              const group = groups.find((gr) => gr.name === g)
              return (
                <span key={g} className="text-xs bg-accent-dim text-accent px-2 py-1 rounded inline-flex items-center gap-1">
                  {g}
                  {group && (
                    <button
                      onClick={() => handleRemoveFromGroup(group.id)}
                      className="text-accent/60 hover:text-red ml-0.5"
                      title="移除"
                    >
                      <i className="ti ti-x text-[10px]" />
                    </button>
                  )}
                </span>
              )
            })
          )}
        </div>
        {/* 可添加的分组 */}
        {groups.filter((g) => !serverGroupNames.has(g.name)).length > 0 && (
          <div className="mt-2 flex items-center gap-2 flex-wrap">
            <span className="text-xs text-text3">添加到:</span>
            {groups
              .filter((g) => !serverGroupNames.has(g.name))
              .map((g) => (
                <button
                  key={g.id}
                  onClick={() => handleAddToGroup(g.id)}
                  className="text-xs text-text3 bg-bg2 hover:bg-accent-dim hover:text-accent px-2 py-0.5 rounded transition-colors"
                >
                  + {g.name}
                </button>
              ))}
          </div>
        )}
      </div>

      {/* 标签 */}
      {parseTags(server.tags).length > 0 && (
        <div>
          <h4 className="text-sm font-medium text-text mb-2">标签</h4>
          <div className="flex gap-2 flex-wrap">
            {parseTags(server.tags).map((t) => (
              <span key={t} className="text-xs bg-bg2 text-text3 px-2 py-1 rounded">{t}</span>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

/* ─── 信息卡片 ─── */

function InfoCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="bg-card border border-border rounded-lg p-3">
      <div className="text-[10px] text-text3 uppercase tracking-wider">{label}</div>
      <div className="text-sm text-text mt-1 font-medium truncate" title={value}>{value}</div>
    </div>
  )
}

/* ─── 测试结果卡片 ─── */

function TestResultCard({ label, ok, detail }: { label: string; ok: boolean | null; detail: string }) {
  const borderCls = ok === true ? 'border-green/30 bg-green/5' : ok === false ? 'border-red/30 bg-red/5' : 'border-border bg-bg2'
  const iconCls = ok === true ? 'ti-circle-check text-green' : ok === false ? 'ti-circle-x text-red' : 'ti-minus text-text3'
  const textCls = ok === true ? 'text-green' : ok === false ? 'text-red' : 'text-text3'
  return (
    <div className={cn('border rounded-lg p-3', borderCls)}>
      <div className="flex items-center gap-2 mb-1">
        <i className={cn('ti text-sm', iconCls)} />
        <span className="text-xs font-medium text-text">{label}</span>
      </div>
      <div className={cn('text-xs', textCls)}>{detail}</div>
    </div>
  )
}

/* ─── 服务器表单 Modal ─── */

function ServerFormModal({
  title,
  initial,
  onClose,
  onSubmit,
}: {
  title: string
  initial: ServerFormData
  onClose: () => void
  onSubmit: (data: ServerFormData) => Promise<void>
}) {
  const [form, setForm] = useState<ServerFormData>(initial)
  const [submitting, setSubmitting] = useState(false)

  const handleSubmit = async () => {
    if (!form.name.trim() || !form.ip_address.trim()) {
      toast.error('名称和 IP 不能为空')
      return
    }
    setSubmitting(true)
    try {
      await onSubmit(form)
    } catch (err: unknown) {
      toast.error(getErrorMessage(err, '操作失败'))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50" onClick={onClose}>
      <div
        className="bg-bg border border-border rounded-xl p-6 w-full max-w-md shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <h3 className="text-base font-semibold text-text mb-4">{title}</h3>

        <div className="space-y-3">
          <FormField label="名称" required>
            <input
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              className="w-full bg-bg2 border border-border rounded-md px-3 py-2 text-sm text-text focus:outline-none focus:border-accent"
              placeholder="e.g. prod-gpu-01"
            />
          </FormField>

          <FormField label="主机名">
            <input
              value={form.hostname}
              onChange={(e) => setForm({ ...form, hostname: e.target.value })}
              className="w-full bg-bg2 border border-border rounded-md px-3 py-2 text-sm text-text focus:outline-none focus:border-accent"
              placeholder="留空则与名称相同"
            />
          </FormField>

          <FormField label="IP 地址" required>
            <input
              value={form.ip_address}
              onChange={(e) => setForm({ ...form, ip_address: e.target.value })}
              className="w-full bg-bg2 border border-border rounded-md px-3 py-2 text-sm text-text focus:outline-none focus:border-accent"
              placeholder="e.g. 192.168.1.100"
            />
          </FormField>

          <div className="grid grid-cols-2 gap-3">
            <FormField label="Agent 端口">
              <input
                type="number"
                value={form.agent_port}
                onChange={(e) => setForm({ ...form, agent_port: Number(e.target.value) })}
                className="w-full bg-bg2 border border-border rounded-md px-3 py-2 text-sm text-text focus:outline-none focus:border-accent"
              />
            </FormField>
            <FormField label="SSH 端口">
              <input
                type="number"
                value={form.ssh_port}
                onChange={(e) => setForm({ ...form, ssh_port: Number(e.target.value) })}
                className="w-full bg-bg2 border border-border rounded-md px-3 py-2 text-sm text-text focus:outline-none focus:border-accent"
              />
            </FormField>
          </div>

          <FormField label="SSH 用户">
            <input
              value={form.ssh_user}
              onChange={(e) => setForm({ ...form, ssh_user: e.target.value })}
              className="w-full bg-bg2 border border-border rounded-md px-3 py-2 text-sm text-text focus:outline-none focus:border-accent"
              placeholder="e.g. root"
            />
          </FormField>

          <FormField label="SSH 密码">
            <input
              type="password"
              value={form.ssh_password}
              onChange={(e) => setForm({ ...form, ssh_password: e.target.value })}
              className="w-full bg-bg2 border border-border rounded-md px-3 py-2 text-sm text-text focus:outline-none focus:border-accent"
              placeholder="填写后将自动安装 Agent"
            />
            <p className="text-xs text-text3 mt-1">
              {form.ssh_password
                ? '将自动通过 SSH 安装 Agent 到远程服务器'
                : '不填密码则仅注册，需手动安装 Agent'}
            </p>
          </FormField>

          <FormField label="标签 (逗号分隔)">
            <input
              value={form.tags}
              onChange={(e) => setForm({ ...form, tags: e.target.value })}
              className="w-full bg-bg2 border border-border rounded-md px-3 py-2 text-sm text-text focus:outline-none focus:border-accent"
              placeholder="e.g. gpu,production,team-a"
            />
          </FormField>
        </div>

        <div className="flex justify-end gap-2 mt-5">
          <button
            onClick={onClose}
            className="px-4 py-2 text-sm text-text2 hover:text-text border border-border rounded-md"
          >
            取消
          </button>
          <button
            onClick={handleSubmit}
            disabled={submitting}
            className="px-4 py-2 text-sm bg-accent text-[#0f172a] rounded-md font-medium disabled:opacity-50"
          >
            {submitting ? '部署中...' : form.ssh_password ? '注册并部署 Agent' : '仅注册'}
          </button>
        </div>
      </div>
    </div>
  )
}

/* ─── Token 显示 Modal ─── */

function TokenDisplayModal({ token, onClose }: { token: string; onClose: () => void }) {
  const [copied, setCopied] = useState(false)

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(token)
      setCopied(true)
      toast.success('已复制到剪贴板')
      setTimeout(() => setCopied(false), 2000)
    } catch {
      toast.error('复制失败，请手动复制')
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50" onClick={onClose}>
      <div
        className="bg-bg border border-border rounded-xl p-6 w-full max-w-lg shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center gap-2 mb-3">
          <i className="ti ti-key text-yellow text-lg" />
          <h3 className="text-base font-semibold text-text">Agent Token</h3>
        </div>
        <p className="text-xs text-yellow mb-3">
          此 Token 仅显示一次，请立即保存。关闭后将无法再次查看。
        </p>
        <div className="flex items-center gap-2 bg-bg2 border border-border rounded-md p-3">
          <code className="text-sm text-text font-mono flex-1 break-all select-all">{token}</code>
          <button
            onClick={handleCopy}
            className="shrink-0 bg-accent text-[#0f172a] px-3 py-1.5 rounded text-xs font-medium"
          >
            {copied ? '已复制' : '复制'}
          </button>
        </div>
        <div className="flex justify-end mt-4">
          <button
            onClick={onClose}
            className="px-4 py-2 text-sm bg-accent text-[#0f172a] rounded-md font-medium"
          >
            我已保存，关闭
          </button>
        </div>
      </div>
    </div>
  )
}

/* ─── 推送更新确认 Modal ─── */

function PushUpdateConfirmModal({
  serverName,
  isPending,
  onConfirm,
  onClose,
}: {
  serverName: string
  isPending: boolean
  onConfirm: () => void
  onClose: () => void
}) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50" onClick={onClose}>
      <div
        className="bg-bg border border-border rounded-xl p-6 w-full max-w-md shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center gap-2 mb-3">
          <i className="ti ti-cloud-upload text-blue-400 text-lg" />
          <h3 className="text-base font-semibold text-text">推送 Agent 更新</h3>
        </div>
        <p className="text-sm text-text2 mb-2">
          即将向 <span className="font-medium text-text">{serverName}</span> 推送最新版 serverhub-agent 源码并触发重启。
        </p>
        <ul className="text-xs text-text3 list-disc list-inside space-y-1 mb-5">
          <li>所有 <code className="bg-bg2 px-1 rounded">serverhub-agent/*.py</code> 文件将上传到远程服务器</li>
          <li>远程 Agent 将在文件提交后自动重启</li>
          <li>重启期间约 5–10 秒内 Agent 连接将短暂中断</li>
        </ul>
        <div className="flex justify-end gap-2">
          <button
            onClick={onClose}
            disabled={isPending}
            className="px-4 py-2 text-sm text-text2 hover:text-text border border-border rounded-md disabled:opacity-50"
          >
            取消
          </button>
          <button
            onClick={onConfirm}
            disabled={isPending}
            className="px-4 py-2 text-sm bg-blue/20 text-blue-400 hover:bg-blue/30 rounded-md font-medium disabled:opacity-50 inline-flex items-center gap-1.5"
          >
            <i className="ti ti-cloud-upload" />
            {isPending ? '推送中...' : '确认推送'}
          </button>
        </div>
      </div>
    </div>
  )
}

/* ─── 表单字段 ─── */

function FormField({ label, required, children }: { label: string; required?: boolean; children: React.ReactNode }) {
  return (
    <div>
      <label className="text-xs text-text3 mb-1 block">
        {label}
        {required && <span className="text-red ml-0.5">*</span>}
      </label>
      {children}
    </div>
  )
}
