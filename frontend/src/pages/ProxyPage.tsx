import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useState, useEffect, useCallback } from 'react'
import client from '@/api/client'
import toast from 'react-hot-toast'
import { cn } from '@/lib/utils'

/* ── Types ────────────────────────────────────────── */

/** 代理实例监听端口 */
interface ListenPort {
  /** 端口标签 */
  label: string
  /** 端口号 */
  port: number
  /** 端口描述 */
  description: string
}

/** 代理配置文件 (含订阅信息) */
interface ConfigProfile {
  /** 配置唯一标识 */
  key: string
  /** 配置显示名称 */
  name: string
  /** 是否有订阅 URL */
  has_subscription: boolean
  /** 订阅 URL 预览文本 */
  subscription_url_preview: string
}

/** 代理实例 (如 Clash/SingBox) */
interface ProxyInstance {
  /** 实例唯一 ID */
  id: string
  /** 实例名称 */
  name: string
  /** 代理类型 (clash/singbox/etc) */
  type: string
  /** 插件名称 */
  plugin: string
  /** 是否运行中 */
  running: boolean
  /** 是否启用 */
  enabled: boolean
  /** 状态文本 */
  status_text: string
  /** 监听端口列表 */
  listen_ports: ListenPort[]
  /** 当前使用的配置 key */
  current_config: string
  /** 当前配置显示名称 */
  current_config_name: string
  /** 可用配置文件列表 */
  config_profiles: ConfigProfile[]
  /** 支持的操作列表 */
  supported_actions: string[]
  /** 版本号 */
  version: string
}

/** 代理组 (Clash ProxyGroup) */
interface ProxyGroup {
  /** 组名 */
  name: string
  /** 组类型 (Selector/URLTest/Fallback) */
  type: string
  /** 当前选中的节点 */
  now: string
  /** 组内所有节点列表 */
  all: string[]
}

/** 节点延迟测试结果，节点名 -> 延迟(ms) 或错误信息 */
interface DelayResult {
  [node: string]: number | string
}

/* ── Helpers ──────────────────────────────────────── */

function statusDot(running: boolean) {
  return running ? 'bg-green' : 'bg-red'
}

function statusBadge(running: boolean) {
  return running ? 'bg-green/20 text-green' : 'bg-red/20 text-red'
}

function delayColor(delay: number | string): string {
  if (typeof delay === 'string') return 'bg-red/20 text-red'
  if (delay < 300) return 'bg-green/20 text-green'
  if (delay < 600) return 'bg-yellow/20 text-yellow'
  return 'bg-red/20 text-red'
}

function delayText(delay: number | string): string {
  if (typeof delay === 'string') return String(delay)
  return `${delay}ms`
}

/* ── Components ───────────────────────────────────── */

/** 新增代理配置文件表单 (含订阅 URL) */
function AddProfileForm({ instanceId, onDone }: { instanceId: string; onDone: () => void }) {
  const queryClient = useQueryClient()
  const [name, setName] = useState('')
  const [url, setUrl] = useState('')

  const addMut = useMutation({
    mutationFn: () =>
      client
        .post(`/api/proxy/instances/${instanceId}/config-profiles`, {
          name,
          url,
        })
        .then((r) => r.data),
    onSuccess: () => {
      toast.success('配置已添加')
      queryClient.invalidateQueries({ queryKey: ['proxy-instances'] })
      onDone()
    },
    onError: () => toast.error('添加失败'),
  })

  return (
    <div className="bg-bg border border-border rounded-lg p-4 space-y-3">
      <h5 className="text-xs uppercase text-text3 font-medium">新增配置</h5>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
        <input
          type="text"
          placeholder="显示名称"
          value={name}
          onChange={(e) => setName(e.target.value)}
          className="bg-bg2 border border-border rounded-md px-3 py-2 text-sm text-text focus:border-accent focus:outline-none"
        />
        <input
          type="text"
          placeholder="订阅 URL (必填)"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          className="bg-bg2 border border-border rounded-md px-3 py-2 text-sm text-text focus:border-accent focus:outline-none"
        />
      </div>
      <div className="flex gap-2">
        <button
          className="bg-accent text-[#0f172a] px-3 py-1.5 rounded-md text-sm font-medium hover:opacity-90 disabled:opacity-50"
          disabled={!name || !url || addMut.isPending}
          onClick={() => addMut.mutate()}
        >
          添加
        </button>
        <button
          className="bg-text3/20 text-text3 px-3 py-1.5 rounded-md text-sm hover:bg-text3/30"
          onClick={onDone}
        >
          取消
        </button>
      </div>
    </div>
  )
}

/** Clash 代理扩展面板 — 代理组列表、节点切换、延迟测试 */
function ClashExtension({ instanceId }: { instanceId: string }) {
  const queryClient = useQueryClient()
  const [expandedGroup, setExpandedGroup] = useState<string | null>(null)
  const [delays, setDelays] = useState<Record<string, DelayResult>>({})
  const [testingGroup, setTestingGroup] = useState<string | null>(null)

  const { data: groups = [], isLoading } = useQuery<ProxyGroup[]>({
    queryKey: ['clash-groups', instanceId],
    queryFn: () =>
      client.get(`/api/proxy/instances/${instanceId}/extensions/clash/groups`).then((r) => r.data),
    refetchInterval: 15000,
  })

  const switchNodeMut = useMutation({
    mutationFn: ({ group, node }: { group: string; node: string }) =>
      client
        .post(`/api/proxy/instances/${instanceId}/extensions/clash/switch-node`, { group, node })
        .then((r) => r.data),
    onSuccess: (data) => {
      toast.success(data.msg || '节点已切换')
      queryClient.invalidateQueries({ queryKey: ['clash-groups', instanceId] })
    },
    onError: () => toast.error('切换失败'),
  })

  const testDelays = useCallback(
    async (groupName: string) => {
      setTestingGroup(groupName)
      try {
        const res = await client.get(
          `/api/proxy/instances/${instanceId}/extensions/clash/test-delays/${encodeURIComponent(groupName)}`,
        )
        setDelays((prev) => ({ ...prev, [groupName]: res.data }))
      } catch {
        toast.error('测速失败')
      } finally {
        setTestingGroup(null)
      }
    },
    [instanceId],
  )

  if (isLoading) return <p className="text-text3 text-xs">加载代理组...</p>

  return (
    <div className="space-y-2">
      <h4 className="text-xs uppercase text-text3 font-medium">代理组</h4>
      {groups.length === 0 ? (
        <p className="text-text3 text-sm">无代理组</p>
      ) : (
        <div className="space-y-1">
          {groups.map((g) => (
            <div key={g.name} className="bg-bg border border-border rounded-lg overflow-hidden">
              {/* Group header */}
              <div
                className="flex items-center justify-between px-4 py-2.5 cursor-pointer hover:bg-bg2/50 transition-colors"
                onClick={() => setExpandedGroup(expandedGroup === g.name ? null : g.name)}
              >
                <div className="flex items-center gap-3">
                  <svg
                    className={cn(
                      'w-3.5 h-3.5 text-text3 transition-transform',
                      expandedGroup === g.name && 'rotate-90',
                    )}
                    fill="none"
                    viewBox="0 0 24 24"
                    stroke="currentColor"
                    strokeWidth={2}
                  >
                    <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
                  </svg>
                  <span className="text-sm font-medium text-text">{g.name}</span>
                  <span className="text-xs text-text3">{g.type}</span>
                </div>
                <div className="flex items-center gap-2">
                  <span className="px-2 py-0.5 rounded text-xs font-medium bg-accent-dim text-accent truncate max-w-[200px]">
                    {g.now || '-'}
                  </span>
                  <span className="text-xs text-text3">{g.all.length} 节点</span>
                  <button
                    className="bg-accent-dim text-accent px-2.5 py-1 rounded-md text-xs hover:opacity-90 disabled:opacity-50"
                    disabled={testingGroup === g.name}
                    onClick={(e) => {
                      e.stopPropagation()
                      testDelays(g.name)
                    }}
                  >
                    {testingGroup === g.name ? '测速中...' : '测速'}
                  </button>
                </div>
              </div>

              {/* Expanded node list */}
              {expandedGroup === g.name && (
                <div className="border-t border-border px-4 py-3">
                  <div className="flex flex-wrap gap-1.5">
                    {g.all.map((node) => {
                      const isActive = node === g.now
                      const nodeDelay = delays[g.name]?.[node]
                      return (
                        <button
                          key={node}
                          className={cn(
                            'px-2.5 py-1.5 rounded-md text-xs transition-colors disabled:opacity-50',
                            isActive
                              ? 'bg-accent text-[#0f172a] font-medium'
                              : 'bg-bg2 text-text hover:bg-card border border-border',
                          )}
                          disabled={switchNodeMut.isPending}
                          onClick={() => switchNodeMut.mutate({ group: g.name, node })}
                        >
                          <span>{node}</span>
                          {nodeDelay !== undefined && (
                            <span
                              className={cn(
                                'ml-1.5 px-1.5 py-0.5 rounded text-[10px] font-mono',
                                isActive ? 'bg-white/20' : delayColor(nodeDelay),
                              )}
                            >
                              {delayText(nodeDelay)}
                            </span>
                          )}
                        </button>
                      )
                    })}
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

/* ── Page ─────────────────────────────────────────── */

/**
 * 代理管理页面
 * 提供代理实例列表、启停/重启、配置切换、订阅更新和 Clash 代理组管理
 * API 前缀: /api/proxy
 */
export default function ProxyPage() {
  const queryClient = useQueryClient()
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [showAddProfile, setShowAddProfile] = useState(false)

  const { data: instances = [], isLoading } = useQuery<ProxyInstance[]>({
    queryKey: ['proxy-instances'],
    queryFn: async () => {
      const res = await client.get('/api/proxy/instances')
      const raw = res.data
      return Array.isArray(raw) ? raw : raw?.instances ?? []
    },
    refetchInterval: 10000,
  })

  // Auto-select first instance
  useEffect(() => {
    if (!selectedId && instances.length > 0) {
      setSelectedId(instances[0].id)
    }
  }, [instances, selectedId])

  const selected = instances.find((i) => i.id === selectedId)

  const actionMut = useMutation({
    mutationFn: ({ id, action }: { id: string; action: string }) =>
      client.post(`/api/proxy/instances/${id}/actions/${action}`).then((r) => r.data),
    onSuccess: (data) => {
      toast.success(data.msg || '操作成功')
      queryClient.invalidateQueries({ queryKey: ['proxy-instances'] })
    },
    onError: () => toast.error('操作失败'),
  })

  const switchConfigMut = useMutation({
    mutationFn: ({ id, profileKey }: { id: string; profileKey: string }) =>
      client
        .post(`/api/proxy/instances/${id}/switch-config`, { profile_key: profileKey })
        .then((r) => r.data),
    onSuccess: () => {
      toast.success('配置已切换')
      queryClient.invalidateQueries({ queryKey: ['proxy-instances'] })
    },
    onError: () => toast.error('切换失败'),
  })

  const updateSubMut = useMutation({
    mutationFn: ({ id, profileKey }: { id: string; profileKey: string }) =>
      client
        .post(`/api/proxy/instances/${id}/config-profiles/${profileKey}/update-subscription`)
        .then((r) => r.data),
    onSuccess: () => {
      toast.success('订阅已更新')
      queryClient.invalidateQueries({ queryKey: ['proxy-instances'] })
    },
    onError: () => toast.error('更新失败'),
  })

  if (isLoading) {
    return <div className="text-text3 text-sm py-8 text-center">加载中...</div>
  }

  if (instances.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-20">
        <svg className="w-16 h-16 text-text3/50 mb-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M12 21a9.004 9.004 0 008.716-6.747M12 21a9.004 9.004 0 01-8.716-6.747M12 21c2.485 0 4.5-4.03 4.5-9S14.485 3 12 3m0 18c-2.485 0-4.5-4.03-4.5-9S9.515 3 12 3m0 0a8.997 8.997 0 017.843 4.582M12 3a8.997 8.997 0 00-7.843 4.582m15.686 0A11.953 11.953 0 0112 10.5c-2.998 0-5.74-1.1-7.843-2.918m15.686 0A8.959 8.959 0 0121 12c0 .778-.099 1.533-.284 2.253m0 0A17.919 17.919 0 0112 16.5a17.92 17.92 0 01-8.716-2.247m0 0A9.015 9.015 0 013 12c0-1.605.42-3.113 1.157-4.418" />
        </svg>
        <h3 className="text-text font-medium mb-1">暂无代理实例</h3>
        <p className="text-text3 text-sm">未检测到已配置的代理服务</p>
      </div>
    )
  }

  return (
    <div className="flex gap-5 h-full">
      {/* Left panel: Instance list */}
      <div className="w-56 shrink-0 space-y-1">
        <h3 className="text-xs uppercase text-text3 font-medium px-2 mb-2">实例列表</h3>
        {instances.map((inst) => (
          <button
            key={inst.id}
            className={cn(
              'w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-left transition-colors',
              selectedId === inst.id ? 'bg-card border border-border' : 'hover:bg-bg2',
            )}
            onClick={() => setSelectedId(inst.id)}
          >
            <span className={cn('w-2 h-2 rounded-full shrink-0', statusDot(inst.running))} />
            <div className="min-w-0">
              <div className="text-sm font-medium text-text truncate">
                {inst.name}
              </div>
              <div className="text-xs text-text3">{inst.type} : {inst.listen_ports?.[0]?.port ?? '-'}</div>
            </div>
          </button>
        ))}
      </div>

      {/* Right panel: Instance detail */}
      {selected ? (
        <div className="flex-1 min-w-0 space-y-5">
          {/* Status card */}
          <div className="bg-card border border-border rounded-lg p-5">
            <div className="flex items-start justify-between">
              <div>
                <h3 className="text-lg font-semibold text-text">
                  {selected.name}
                </h3>
                <div className="flex items-center gap-3 mt-2 text-sm text-text3">
                  <span>类型: {selected.type}</span>
                  <span>端口: {selected.listen_ports?.[0]?.port ?? '-'}</span>
                  <span
                    className={cn('px-2 py-0.5 rounded text-xs font-medium', statusBadge(selected.running))}
                  >
                    {selected.running ? '运行中' : '已停止'}
                  </span>
                  {selected.current_config_name && (
                    <span className="px-2 py-0.5 rounded text-xs font-medium bg-accent-dim text-accent">
                      {selected.current_config_name}
                    </span>
                  )}
                </div>
              </div>

              {/* Action buttons */}
              <div className="flex items-center gap-2">
                {!selected.running ? (
                  <button
                    className="bg-accent text-[#0f172a] px-4 py-2 rounded-md text-sm font-medium hover:opacity-90 disabled:opacity-50"
                    disabled={actionMut.isPending}
                    onClick={() => actionMut.mutate({ id: selected.id, action: 'start' })}
                  >
                    启动
                  </button>
                ) : (
                  <>
                    <button
                      className="bg-red/20 text-red px-4 py-2 rounded-md text-sm hover:bg-red/30 disabled:opacity-50"
                      disabled={actionMut.isPending}
                      onClick={() => actionMut.mutate({ id: selected.id, action: 'stop' })}
                    >
                      停止
                    </button>
                    <button
                      className="bg-yellow/20 text-yellow px-4 py-2 rounded-md text-sm hover:bg-yellow/30 disabled:opacity-50"
                      disabled={actionMut.isPending}
                      onClick={() => actionMut.mutate({ id: selected.id, action: 'restart' })}
                    >
                      重启
                    </button>
                  </>
                )}
                <button
                  className="bg-accent-dim text-accent px-4 py-2 rounded-md text-sm hover:opacity-90 disabled:opacity-50"
                  disabled={actionMut.isPending}
                  onClick={() => actionMut.mutate({ id: selected.id, action: 'test' })}
                >
                  测试连接
                </button>
              </div>
            </div>
          </div>

          {/* Config profiles */}
          <div className="bg-card border border-border rounded-lg p-5 space-y-4">
            <div className="flex items-center justify-between">
              <h4 className="text-xs uppercase text-text3 font-medium">配置文件</h4>
              <button
                className="text-accent text-xs hover:underline"
                onClick={() => setShowAddProfile(!showAddProfile)}
              >
                {showAddProfile ? '取消' : '+ 新增配置'}
              </button>
            </div>

            {showAddProfile && (
              <AddProfileForm
                instanceId={selected.id}
                onDone={() => setShowAddProfile(false)}
              />
            )}

            {selected.config_profiles.length === 0 ? (
              <p className="text-text3 text-sm">暂无配置文件</p>
            ) : (
              <div className="space-y-2">
                {selected.config_profiles.map((profile) => {
                  const isActive = profile.key === selected.current_config
                  return (
                    <div
                      key={profile.key}
                      className={cn(
                        'flex items-center justify-between px-4 py-3 rounded-lg border transition-colors',
                        isActive
                          ? 'border-accent/50 bg-accent-dim/30'
                          : 'border-border bg-bg',
                      )}
                    >
                      <div className="flex items-center gap-3">
                        {isActive && (
                          <span className="w-1.5 h-1.5 rounded-full bg-accent" />
                        )}
                        <span className="text-sm text-text font-medium">{profile.name}</span>
                        <span className="text-xs text-text3 font-mono">{profile.key}</span>
                      </div>
                      <div className="flex items-center gap-2">
                        {profile.has_subscription && (
                          <button
                            className="bg-accent-dim text-accent px-2.5 py-1 rounded-md text-xs hover:opacity-90 disabled:opacity-50"
                            disabled={updateSubMut.isPending}
                            onClick={() =>
                              updateSubMut.mutate({ id: selected.id, profileKey: profile.key })
                            }
                          >
                            更新订阅
                          </button>
                        )}
                        {!isActive && (
                          <button
                            className="bg-accent text-[#0f172a] px-2.5 py-1 rounded-md text-xs font-medium hover:opacity-90 disabled:opacity-50"
                            disabled={switchConfigMut.isPending}
                            onClick={() =>
                              switchConfigMut.mutate({ id: selected.id, profileKey: profile.key })
                            }
                          >
                            切换
                          </button>
                        )}
                      </div>
                    </div>
                  )
                })}
              </div>
            )}
          </div>

          {/* Clash extension */}
          {selected.plugin === 'clash' && (
            <div className="bg-card border border-border rounded-lg p-5">
              <ClashExtension instanceId={selected.id} />
            </div>
          )}
        </div>
      ) : (
        <div className="flex-1 flex items-center justify-center text-text3 text-sm">
          请选择一个代理实例
        </div>
      )}
    </div>
  )
}
