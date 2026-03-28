import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import React, { useState } from 'react'
import client from '@/api/client'
import toast from 'react-hot-toast'
import { cn, formatDate, formatBytes } from '@/lib/utils'

/* ── Types ────────────────────────────────────────── */

interface Container {
  name: string
  id: string
  image: string
  state: string
  status: string
  ports: string
  created: string
}

interface Stack {
  name: string
  display_name: string
  path: string
  services: number
  running: number
}

interface DockerImage {
  Repository: string
  Tag: string
  ID: string
  Size: number | string
  Created: string
}

interface Network {
  Name: string
  Driver: string
  Scope: string
  ID: string
}

interface Volume {
  Name: string
  Driver: string
  Mountpoint: string
}

/* ── Helpers ──────────────────────────────────────── */

const TABS = ['容器', '堆栈', '镜像', '网络', '卷'] as const
type Tab = (typeof TABS)[number]

const PRUNE_TYPES = [
  { label: '清理容器', value: 'containers' },
  { label: '清理镜像', value: 'images' },
  { label: '清理卷', value: 'volumes' },
  { label: '清理网络', value: 'networks' },
] as const

function containerStateColor(state: string) {
  if (state === 'running') return 'bg-green/20 text-green'
  if (state === 'exited' || state === 'dead') return 'bg-red/20 text-red'
  return 'bg-yellow/20 text-yellow'
}

/* ── Page ─────────────────────────────────────────── */

export default function DockerPage() {
  const queryClient = useQueryClient()
  const [tab, setTab] = useState<Tab>('容器')
  const [expandedContainer, setExpandedContainer] = useState<string | null>(null)
  const [execCmd, setExecCmd] = useState('')
  const [pruneOpen, setPruneOpen] = useState(false)
  const [pullImage, setPullImage] = useState('')

  /* Queries */
  const { data: containers = [], isLoading: loadingContainers } = useQuery<Container[]>({
    queryKey: ['docker-containers'],
    queryFn: () => client.get('/api/docker/containers').then((r) => r.data),
    refetchInterval: 10000,
    enabled: tab === '容器',
  })

  const { data: stacks = [] } = useQuery<Stack[]>({
    queryKey: ['docker-stacks'],
    queryFn: () => client.get('/api/docker/stacks').then((r) => r.data),
    enabled: tab === '堆栈',
  })

  const { data: images = [] } = useQuery<DockerImage[]>({
    queryKey: ['docker-images'],
    queryFn: () => client.get('/api/docker/images').then((r) => r.data),
    enabled: tab === '镜像',
  })

  const { data: networksData } = useQuery<{ networks: Network[] }>({
    queryKey: ['docker-networks'],
    queryFn: () => client.get('/api/docker/networks').then((r) => r.data),
    enabled: tab === '网络',
  })

  const { data: volumesData } = useQuery<{ volumes: Volume[] }>({
    queryKey: ['docker-volumes'],
    queryFn: () => client.get('/api/docker/volumes').then((r) => r.data),
    enabled: tab === '卷',
  })

  const { data: containerLogs } = useQuery<{ name: string; logs: string }>({
    queryKey: ['docker-logs', expandedContainer],
    queryFn: () =>
      client.get(`/api/docker/containers/${expandedContainer}/logs?tail=200`).then((r) => r.data),
    enabled: !!expandedContainer,
  })

  /* Mutations */
  const containerAction = useMutation({
    mutationFn: ({ name, action }: { name: string; action: string }) =>
      client.post(`/api/docker/containers/${name}/${action}`).then((r) => r.data),
    onSuccess: (data) => {
      toast.success(data.output || '操作成功')
      queryClient.invalidateQueries({ queryKey: ['docker-containers'] })
    },
    onError: () => toast.error('操作失败'),
  })

  const stackAction = useMutation({
    mutationFn: ({ name, action }: { name: string; action: string }) =>
      client.post(`/api/docker/stacks/${name}/${action}`).then((r) => r.data),
    onSuccess: () => {
      toast.success('操作成功')
      queryClient.invalidateQueries({ queryKey: ['docker-stacks'] })
    },
    onError: () => toast.error('操作失败'),
  })

  const deleteImage = useMutation({
    mutationFn: (id: string) => client.delete(`/api/docker/images/${id}`).then((r) => r.data),
    onSuccess: () => {
      toast.success('镜像已删除')
      queryClient.invalidateQueries({ queryKey: ['docker-images'] })
    },
    onError: () => toast.error('删除失败'),
  })

  const execMut = useMutation({
    mutationFn: ({ name, command }: { name: string; command: string }) =>
      client.post(`/api/docker/containers/${name}/exec`, { command }).then((r) => r.data),
    onSuccess: (data) => toast.success(data.output?.slice(0, 200) || '执行完成'),
    onError: () => toast.error('执行失败'),
  })

  const pruneMut = useMutation({
    mutationFn: (type: string) => client.post(`/api/docker/prune/${type}`).then((r) => r.data),
    onSuccess: (data) => {
      toast.success(data.output || '清理完成')
      queryClient.invalidateQueries({ queryKey: ['docker-containers'] })
      queryClient.invalidateQueries({ queryKey: ['docker-images'] })
      queryClient.invalidateQueries({ queryKey: ['docker-volumes'] })
      queryClient.invalidateQueries({ queryKey: ['docker-networks'] })
    },
    onError: () => toast.error('清理失败'),
  })

  const pullMut = useMutation({
    mutationFn: (image: string) =>
      client.post('/api/docker/images/pull', { image }).then((r) => r.data),
    onSuccess: (data) => {
      toast.success(data.output || '镜像拉取成功')
      queryClient.invalidateQueries({ queryKey: ['docker-images'] })
      setPullImage('')
    },
    onError: () => toast.error('镜像拉取失败'),
  })

  // Always-on queries for stat summary (not gated by tab)
  const { data: allContainers = [] } = useQuery<Container[]>({
    queryKey: ['docker-containers-all'],
    queryFn: () => client.get('/api/docker/containers').then((r) => r.data),
    refetchInterval: 15000,
  })
  const { data: allImages = [] } = useQuery<DockerImage[]>({
    queryKey: ['docker-images-all'],
    queryFn: () => client.get('/api/docker/images').then((r) => r.data),
    staleTime: 30000,
  })
  const { data: allStacks = [] } = useQuery<Stack[]>({
    queryKey: ['docker-stacks-all'],
    queryFn: () => client.get('/api/docker/stacks').then((r) => r.data),
    staleTime: 30000,
  })

  const networks = networksData?.networks ?? []
  const volumes = volumesData?.volumes ?? []

  const runningCount = allContainers.filter((c) => c.state === 'running').length

  /* ── Render ─────────────────────────────────────── */

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold">Docker 管理</h2>
        <div className="relative">
          <button
            className="bg-red/20 text-red px-3 py-1.5 rounded-md text-sm hover:bg-red/30"
            onClick={() => setPruneOpen(!pruneOpen)}
          >
            清理资源
          </button>
          {pruneOpen && (
            <div className="absolute right-0 mt-1 bg-card border border-border rounded-lg shadow-lg z-10 py-1 w-36">
              {PRUNE_TYPES.map((p) => (
                <button
                  key={p.value}
                  className="w-full text-left px-3 py-2 text-sm text-text hover:bg-bg2 disabled:opacity-50"
                  disabled={pruneMut.isPending}
                  onClick={() => {
                    pruneMut.mutate(p.value)
                    setPruneOpen(false)
                  }}
                >
                  {p.label}
                </button>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Stat summary cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <div className="bg-card border border-border rounded-lg p-4">
          <div className="text-text3 text-xs uppercase mb-1">容器总数</div>
          <div className="text-2xl font-bold text-text">{allContainers.length}</div>
        </div>
        <div className="bg-card border border-border rounded-lg p-4">
          <div className="text-text3 text-xs uppercase mb-1">运行中</div>
          <div className="text-2xl font-bold text-green">{runningCount}</div>
        </div>
        <div className="bg-card border border-border rounded-lg p-4">
          <div className="text-text3 text-xs uppercase mb-1">镜像数</div>
          <div className="text-2xl font-bold text-accent">{allImages.length}</div>
        </div>
        <div className="bg-card border border-border rounded-lg p-4">
          <div className="text-text3 text-xs uppercase mb-1">堆栈数</div>
          <div className="text-2xl font-bold text-yellow">{allStacks.length}</div>
        </div>
      </div>

      {/* Tab bar */}
      <div className="flex border-b border-border">
        {TABS.map((t) => (
          <button
            key={t}
            className={cn(
              'px-4 py-2 text-sm cursor-pointer border-b-2 transition-colors',
              tab === t ? 'border-accent text-accent' : 'border-transparent text-text3 hover:text-text',
            )}
            onClick={() => setTab(t)}
          >
            {t}
          </button>
        ))}
      </div>

      {/* ── 容器 Tab ── */}
      {tab === '容器' && (
        <div className="bg-card border border-border rounded-lg overflow-hidden">
          {loadingContainers ? (
            <div className="text-text3 text-sm py-8 text-center">加载中...</div>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border">
                  <th className="text-text3 text-left text-xs uppercase px-4 py-3">名称</th>
                  <th className="text-text3 text-left text-xs uppercase px-4 py-3">镜像</th>
                  <th className="text-text3 text-left text-xs uppercase px-4 py-3">状态</th>
                  <th className="text-text3 text-left text-xs uppercase px-4 py-3">运行状态</th>
                  <th className="text-text3 text-left text-xs uppercase px-4 py-3">端口</th>
                  <th className="text-text3 text-right text-xs uppercase px-4 py-3">操作</th>
                </tr>
              </thead>
              <tbody>
                {containers.map((c) => (
                  <React.Fragment key={c.name}>
                    <tr
                      className={cn(
                        'border-b border-border hover:bg-bg2/50 cursor-pointer transition-colors',
                        expandedContainer === c.name && 'bg-bg2/50',
                      )}
                      onClick={() =>
                        setExpandedContainer(expandedContainer === c.name ? null : c.name)
                      }
                    >
                      <td className="px-4 py-3 font-medium text-text">{c.name}</td>
                      <td className="px-4 py-3 text-text3 max-w-[200px] truncate">{c.image}</td>
                      <td className="px-4 py-3">
                        <span className={cn('px-2 py-0.5 rounded text-xs font-medium', containerStateColor(c.state))}>
                          {c.state}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-text3">{c.status}</td>
                      <td className="px-4 py-3 text-text3 font-mono text-xs max-w-[200px] truncate">
                        {c.ports || '-'}
                      </td>
                      <td className="px-4 py-3 text-right">
                        <div className="flex items-center justify-end gap-1" onClick={(e) => e.stopPropagation()}>
                          {c.state !== 'running' ? (
                            <button
                              className="bg-accent text-[#0f172a] px-3 py-1.5 rounded-md text-sm font-medium hover:opacity-90 disabled:opacity-50"
                              disabled={containerAction.isPending}
                              onClick={() => containerAction.mutate({ name: c.name, action: 'start' })}
                            >
                              启动
                            </button>
                          ) : (
                            <>
                              <button
                                className="bg-red/20 text-red px-3 py-1.5 rounded-md text-sm hover:bg-red/30 disabled:opacity-50"
                                disabled={containerAction.isPending}
                                onClick={() => containerAction.mutate({ name: c.name, action: 'stop' })}
                              >
                                停止
                              </button>
                              <button
                                className="bg-yellow/20 text-yellow px-3 py-1.5 rounded-md text-sm hover:bg-yellow/30 disabled:opacity-50"
                                disabled={containerAction.isPending}
                                onClick={() => containerAction.mutate({ name: c.name, action: 'restart' })}
                              >
                                重启
                              </button>
                            </>
                          )}
                        </div>
                      </td>
                    </tr>

                    {expandedContainer === c.name && (
                      <tr key={`${c.name}-detail`}>
                        <td colSpan={6} className="px-4 py-4 bg-bg/50">
                          <div className="space-y-3">
                            {/* Exec */}
                            <div className="flex items-center gap-2">
                              <input
                                type="text"
                                placeholder="在容器内执行命令..."
                                value={execCmd}
                                onChange={(e) => setExecCmd(e.target.value)}
                                onKeyDown={(e) => {
                                  if (e.key === 'Enter' && execCmd.trim()) {
                                    execMut.mutate({ name: c.name, command: execCmd })
                                    setExecCmd('')
                                  }
                                }}
                                className="bg-bg border border-border rounded-md px-3 py-2 text-sm text-text focus:border-accent focus:outline-none flex-1 font-mono"
                              />
                              <button
                                className="bg-accent text-[#0f172a] px-3 py-1.5 rounded-md text-sm font-medium hover:opacity-90 disabled:opacity-50"
                                disabled={execMut.isPending || !execCmd.trim()}
                                onClick={() => {
                                  execMut.mutate({ name: c.name, command: execCmd })
                                  setExecCmd('')
                                }}
                              >
                                执行
                              </button>
                            </div>
                            {/* Logs */}
                            <div>
                              <h4 className="text-xs uppercase text-text3 mb-2">日志 (最近 200 行)</h4>
                              <pre className="text-xs text-text3 font-mono whitespace-pre-wrap max-h-64 overflow-y-auto bg-bg rounded p-2 border border-border">
                                {containerLogs?.logs || '加载中...'}
                              </pre>
                            </div>
                          </div>
                        </td>
                      </tr>
                    )}
                  </React.Fragment>
                ))}
                {containers.length === 0 && (
                  <tr>
                    <td colSpan={6} className="text-center text-text3 py-8 text-sm">
                      无容器
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          )}
        </div>
      )}

      {/* ── 堆栈 Tab ── */}
      {tab === '堆栈' && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {stacks.map((s) => (
            <div key={s.name} className="bg-card border border-border rounded-lg p-4 space-y-3">
              <div className="flex items-center justify-between">
                <h3 className="font-medium text-text">{s.display_name || s.name}</h3>
                <span
                  className={cn(
                    'px-2 py-0.5 rounded text-xs font-medium',
                    s.running === s.services ? 'bg-green/20 text-green' : 'bg-yellow/20 text-yellow',
                  )}
                >
                  {s.running}/{s.services}
                </span>
              </div>
              <p className="text-text3 text-xs font-mono truncate">{s.path}</p>
              <div className="flex gap-1">
                {(['restart', 'pull', 'up', 'down'] as const).map((action) => (
                  <button
                    key={action}
                    className={cn(
                      'px-3 py-1.5 rounded-md text-sm disabled:opacity-50',
                      action === 'down'
                        ? 'bg-red/20 text-red hover:bg-red/30'
                        : 'bg-accent-dim text-accent hover:opacity-90',
                    )}
                    disabled={stackAction.isPending}
                    onClick={() => stackAction.mutate({ name: s.name, action })}
                  >
                    {action}
                  </button>
                ))}
              </div>
            </div>
          ))}
          {stacks.length === 0 && (
            <div className="col-span-full text-center text-text3 py-8 text-sm">无堆栈</div>
          )}
        </div>
      )}

      {/* ── 镜像 Tab ── */}
      {tab === '镜像' && (
        <div className="space-y-3">
        <div className="flex gap-2 items-center">
          <input
            type="text"
            placeholder="镜像名称 (如 nginx:latest)"
            value={pullImage}
            onChange={(e) => setPullImage(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && pullImage.trim()) pullMut.mutate(pullImage.trim())
            }}
            className="bg-bg border border-border rounded-md px-3 py-2 text-sm text-text focus:border-accent focus:outline-none flex-1 font-mono"
          />
          <button
            onClick={() => pullMut.mutate(pullImage.trim())}
            disabled={!pullImage.trim() || pullMut.isPending}
            className="bg-accent text-[#0f172a] px-4 py-2 rounded-md text-sm font-medium hover:opacity-90 disabled:opacity-50 shrink-0"
          >
            {pullMut.isPending ? '拉取中...' : 'Pull'}
          </button>
        </div>
        <div className="bg-card border border-border rounded-lg overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border">
                <th className="text-text3 text-left text-xs uppercase px-4 py-3">仓库</th>
                <th className="text-text3 text-left text-xs uppercase px-4 py-3">标签</th>
                <th className="text-text3 text-left text-xs uppercase px-4 py-3">ID</th>
                <th className="text-text3 text-left text-xs uppercase px-4 py-3">大小</th>
                <th className="text-text3 text-left text-xs uppercase px-4 py-3">创建时间</th>
                <th className="text-text3 text-right text-xs uppercase px-4 py-3">操作</th>
              </tr>
            </thead>
            <tbody>
              {images.map((img) => (
                <tr key={img.ID} className="border-b border-border hover:bg-bg2/50 transition-colors">
                  <td className="px-4 py-3 text-text">{img.Repository}</td>
                  <td className="px-4 py-3 text-text3">{img.Tag}</td>
                  <td className="px-4 py-3 text-text3 font-mono text-xs">{img.ID?.slice(0, 12)}</td>
                  <td className="px-4 py-3 text-text3">
                    {typeof img.Size === 'number' ? formatBytes(img.Size) : img.Size}
                  </td>
                  <td className="px-4 py-3 text-text3">{img.Created}</td>
                  <td className="px-4 py-3 text-right">
                    <button
                      className="bg-red/20 text-red px-3 py-1.5 rounded-md text-sm hover:bg-red/30 disabled:opacity-50"
                      disabled={deleteImage.isPending}
                      onClick={() => {
                        if (confirm(`确认删除镜像 ${img.Repository}:${img.Tag}?`)) {
                          deleteImage.mutate(img.ID)
                        }
                      }}
                    >
                      删除
                    </button>
                  </td>
                </tr>
              ))}
              {images.length === 0 && (
                <tr>
                  <td colSpan={6} className="text-center text-text3 py-8 text-sm">
                    无镜像
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
        </div>
      )}

      {/* ── 网络 Tab ── */}
      {tab === '网络' && (
        <div className="bg-card border border-border rounded-lg overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border">
                <th className="text-text3 text-left text-xs uppercase px-4 py-3">名称</th>
                <th className="text-text3 text-left text-xs uppercase px-4 py-3">驱动</th>
                <th className="text-text3 text-left text-xs uppercase px-4 py-3">范围</th>
                <th className="text-text3 text-left text-xs uppercase px-4 py-3">ID</th>
              </tr>
            </thead>
            <tbody>
              {networks.map((n) => (
                <tr key={n.ID || n.Name} className="border-b border-border hover:bg-bg2/50 transition-colors">
                  <td className="px-4 py-3 text-text font-medium">{n.Name}</td>
                  <td className="px-4 py-3 text-text3">{n.Driver}</td>
                  <td className="px-4 py-3 text-text3">{n.Scope}</td>
                  <td className="px-4 py-3 text-text3 font-mono text-xs">{n.ID?.slice(0, 12)}</td>
                </tr>
              ))}
              {networks.length === 0 && (
                <tr>
                  <td colSpan={4} className="text-center text-text3 py-8 text-sm">
                    无网络
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      {/* ── 卷 Tab ── */}
      {tab === '卷' && (
        <div className="bg-card border border-border rounded-lg overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border">
                <th className="text-text3 text-left text-xs uppercase px-4 py-3">名称</th>
                <th className="text-text3 text-left text-xs uppercase px-4 py-3">驱动</th>
                <th className="text-text3 text-left text-xs uppercase px-4 py-3">挂载点</th>
              </tr>
            </thead>
            <tbody>
              {volumes.map((v) => (
                <tr key={v.Name} className="border-b border-border hover:bg-bg2/50 transition-colors">
                  <td className="px-4 py-3 text-text font-medium">{v.Name}</td>
                  <td className="px-4 py-3 text-text3">{v.Driver}</td>
                  <td className="px-4 py-3 text-text3 font-mono text-xs max-w-md truncate">{v.Mountpoint}</td>
                </tr>
              ))}
              {volumes.length === 0 && (
                <tr>
                  <td colSpan={3} className="text-center text-text3 py-8 text-sm">
                    无卷
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
