import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import React, { useState } from 'react'
import client from '@/api/client'
import toast from 'react-hot-toast'
import { cn, ensureArray, ensureRecord, toString } from '@/lib/utils'
import { useServerStore } from '@/stores/serverStore'

interface Service {
  /** systemd 服务名称 */
  name: string
  /** 前端显示名称 */
  display_name: string
  /** 服务描述 */
  description: string
  /** 活跃状态 (active / inactive / activating 等) */
  active_state: string
  /** 子状态 (running / dead / waiting 等) */
  sub_state: string
  /** 是否已设置开机自启 */
  enabled: boolean
}

/** 服务资源使用数据 (CPU/内存/IO) */
interface ServiceResources {
  /** CPU 使用百分比 */
  cpu_percent?: string
  /** 当前内存占用 */
  memory_current?: string
  /** 内存峰值 */
  memory_peak?: string
  /** 任务数 */
  tasks?: string
  /** IO 读取量 */
  io_read?: string
  /** IO 写入量 */
  io_write?: string
  [key: string]: string | undefined
}

/** 服务依赖关系 */
interface ServiceDependencies {
  /** 该服务依赖的服务列表 */
  requires: string[]
  /** 依赖该服务的服务列表 */
  required_by: string[]
  /** Wants 依赖列表 */
  wants: string[]
  /** WantedBy 依赖列表 */
  wanted_by: string[]
}

/** 服务日志条目 */
interface ServiceJournal {
  /** 服务名称 */
  name: string
  /** 日志内容 */
  journal: string
}

function stateColor(state: string) {
  if (state === 'active') return 'bg-green'
  if (state === 'inactive' || state === 'dead') return 'bg-red'
  if (state === 'activating' || state === 'deactivating') return 'bg-yellow'
  return 'bg-text3'
}

function stateBadge(state: string) {
  if (state === 'active') return 'bg-green/20 text-green'
  if (state === 'inactive' || state === 'dead') return 'bg-red/20 text-red'
  return 'bg-yellow/20 text-yellow'
}

/** 将 API 返回的各类服务数据统一规范化为 Service[] */
function normalizeServices(value: unknown): Service[] {
  const record = ensureRecord(value)
  const items = Array.isArray(value) ? value : record.services
  return ensureArray<Record<string, unknown>>(items).map((item) => {
    const activeState = typeof item.active_state === 'string'
      ? item.active_state
      : item.active === true
        ? 'active'
        : 'inactive'
    return {
      name: toString(item.name, 'unknown'),
      display_name: toString(item.display_name ?? item.name),
      description: toString(item.description),
      active_state: activeState,
      sub_state: toString(item.sub_state ?? item.status_text ?? activeState),
      enabled: Boolean(item.enabled),
    }
  })
}

/** 将 API 返回的依赖数据统一规范化为 ServiceDependencies */
function normalizeDependencies(value: unknown): ServiceDependencies {
  const record = ensureRecord(value)
  const dependencies = ensureArray<string>(record.dependencies)
  return {
    requires: ensureArray<string>(record.requires ?? dependencies),
    required_by: ensureArray<string>(record.required_by),
    wants: ensureArray<string>(record.wants),
    wanted_by: ensureArray<string>(record.wanted_by),
  }
}

/**
 * 服务管理页面
 * 提供 systemd 服务的启停/重启/重载、enable/disable、资源监控、依赖关系查看和日志浏览
 * API 前缀: /api/services
 */
export default function ServicesPage() {
  const queryClient = useQueryClient()
  const serverId = useServerStore((s) => s.selectedServerId)
  const [expanded, setExpanded] = useState<string | null>(null)
  const [search, setSearch] = useState('')

  const { data: servicesData, isLoading } = useQuery<Service[]>({
    queryKey: ['services', serverId],
    queryFn: () => client.get('/api/services/', { params: { server_id: serverId } }).then((r) => normalizeServices(r.data)),
    refetchInterval: 10000,
  })

  const { data: resources } = useQuery<ServiceResources>({
    queryKey: ['service-resources', expanded, serverId],
    queryFn: () => client.get(`/api/services/${expanded}/resources`, { params: { server_id: serverId } }).then((r) => r.data),
    enabled: !!expanded,
  })

  const { data: deps } = useQuery<ServiceDependencies>({
    queryKey: ['service-deps', expanded, serverId],
    queryFn: () => client.get(`/api/services/${expanded}/dependencies`, { params: { server_id: serverId } }).then((r) => normalizeDependencies(r.data)),
    enabled: !!expanded,
  })

  const { data: journal } = useQuery<ServiceJournal>({
    queryKey: ['service-journal', expanded, serverId],
    queryFn: () => client.get(`/api/services/${expanded}/journal`, { params: { lines: 50, server_id: serverId } }).then((r) => r.data),
    enabled: !!expanded,
  })

  const actionMut = useMutation({
    mutationFn: ({ name, action }: { name: string; action: string }) =>
      client.post(`/api/services/${name}/${action}`, null, { params: { server_id: serverId } }).then((r) => r.data),
    onSuccess: (data) => {
      toast.success(`${data.service}: ${data.action} 成功`)
      queryClient.invalidateQueries({ queryKey: ['services', serverId] })
    },
    onError: () => toast.error('操作失败'),
  })

  const enableMut = useMutation({
    mutationFn: ({ name, enable }: { name: string; enable: boolean }) =>
      client.post(`/api/services/${name}/${enable ? 'enable' : 'disable'}`, null, { params: { server_id: serverId } }).then((r) => r.data),
    onSuccess: () => {
      toast.success('操作成功')
      queryClient.invalidateQueries({ queryKey: ['services', serverId] })
    },
    onError: () => toast.error('操作失败'),
  })

  const reloadMut = useMutation({
    mutationFn: (name: string) =>
      client.post(`/api/services/${name}/reload`, null, { params: { server_id: serverId } }).then((r) => r.data),
    onSuccess: () => {
      toast.success('Reload 成功')
      queryClient.invalidateQueries({ queryKey: ['services', serverId] })
    },
    onError: () => toast.error('Reload 失败'),
  })

  const services = ensureArray<Service>(servicesData)

  const filtered = services.filter(
    (s) =>
      s.name.toLowerCase().includes(search.toLowerCase()) ||
      s.description?.toLowerCase().includes(search.toLowerCase()),
  )

  const totalCount = services.length
  const runningCount = services.filter((s) => s.active_state === 'active').length
  const stoppedCount = services.filter((s) => s.active_state !== 'active').length
  const autoStartCount = services.filter((s) => s.enabled).length

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold">服务管理</h2>
        <input
          type="text"
          placeholder="搜索服务..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="bg-bg border border-border rounded-md px-3 py-2 text-sm text-text focus:border-accent focus:outline-none w-64"
        />
      </div>

      {/* Stat summary cards */}
      {!isLoading && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <div className="bg-card border border-border rounded-lg p-4">
            <div className="text-text3 text-xs uppercase mb-1">总服务数</div>
            <div className="text-2xl font-bold text-text">{totalCount}</div>
          </div>
          <div className="bg-card border border-border rounded-lg p-4">
            <div className="text-text3 text-xs uppercase mb-1">运行中</div>
            <div className="text-2xl font-bold text-green">{runningCount}</div>
          </div>
          <div className="bg-card border border-border rounded-lg p-4">
            <div className="text-text3 text-xs uppercase mb-1">已停止</div>
            <div className="text-2xl font-bold text-red">{stoppedCount}</div>
          </div>
          <div className="bg-card border border-border rounded-lg p-4">
            <div className="text-text3 text-xs uppercase mb-1">开机启动</div>
            <div className="text-2xl font-bold text-accent">{autoStartCount}</div>
          </div>
        </div>
      )}

      {isLoading ? (
        <div className="text-text3 text-sm py-8 text-center">加载中...</div>
      ) : (
        <div className="bg-card border border-border rounded-lg overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border">
                <th className="text-text3 text-left text-xs uppercase px-4 py-3">状态</th>
                <th className="text-text3 text-left text-xs uppercase px-4 py-3">服务名</th>
                <th className="text-text3 text-left text-xs uppercase px-4 py-3">描述</th>
                <th className="text-text3 text-left text-xs uppercase px-4 py-3">子状态</th>
                <th className="text-text3 text-left text-xs uppercase px-4 py-3">开机启动</th>
                <th className="text-text3 text-right text-xs uppercase px-4 py-3">操作</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((svc) => (
                <React.Fragment key={svc.name}>
                  <tr
                    className={cn(
                      'border-b border-border hover:bg-bg2/50 cursor-pointer transition-colors',
                      expanded === svc.name && 'bg-bg2/50',
                    )}
                    onClick={() => setExpanded(expanded === svc.name ? null : svc.name)}
                  >
                    <td className="px-4 py-3">
                      <span className={cn('w-2 h-2 rounded-full inline-block', stateColor(svc.active_state))} />
                    </td>
                    <td className="px-4 py-3 font-medium text-text">{svc.display_name || svc.name}</td>
                    <td className="px-4 py-3 text-text3 max-w-xs truncate">{svc.description || '-'}</td>
                    <td className="px-4 py-3">
                      <span className={cn('px-2 py-0.5 rounded text-xs font-medium', stateBadge(svc.active_state))}>
                        {svc.sub_state}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <span
                        className={cn(
                          'px-2 py-0.5 rounded text-xs font-medium',
                          svc.enabled ? 'bg-green/20 text-green' : 'bg-text3/20 text-text3',
                        )}
                      >
                        {svc.enabled ? '已启用' : '已禁用'}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-right">
                      <div className="flex items-center justify-end gap-1" onClick={(e) => e.stopPropagation()}>
                        {svc.active_state !== 'active' ? (
                          <button
                            className="bg-accent text-[#0f172a] px-3 py-1.5 rounded-md text-sm font-medium hover:opacity-90 disabled:opacity-50"
                            disabled={actionMut.isPending}
                            onClick={() => actionMut.mutate({ name: svc.name, action: 'start' })}
                          >
                            启动
                          </button>
                        ) : (
                          <>
                            <button
                              className="bg-red/20 text-red px-3 py-1.5 rounded-md text-sm hover:bg-red/30 disabled:opacity-50"
                              disabled={actionMut.isPending}
                              onClick={() => actionMut.mutate({ name: svc.name, action: 'stop' })}
                            >
                              停止
                            </button>
                            <button
                              className="bg-yellow/20 text-yellow px-3 py-1.5 rounded-md text-sm hover:bg-yellow/30 disabled:opacity-50"
                              disabled={actionMut.isPending}
                              onClick={() => actionMut.mutate({ name: svc.name, action: 'restart' })}
                            >
                              重启
                            </button>
                            <button
                              className="bg-accent-dim text-accent px-3 py-1.5 rounded-md text-sm hover:opacity-90 disabled:opacity-50"
                              disabled={reloadMut.isPending}
                              onClick={() => reloadMut.mutate(svc.name)}
                            >
                              Reload
                            </button>
                          </>
                        )}
                        <button
                          className={cn(
                            'px-3 py-1.5 rounded-md text-sm disabled:opacity-50',
                            svc.enabled
                              ? 'bg-text3/20 text-text3 hover:bg-text3/30'
                              : 'bg-green/20 text-green hover:bg-green/30',
                          )}
                          disabled={enableMut.isPending}
                          onClick={() => enableMut.mutate({ name: svc.name, enable: !svc.enabled })}
                        >
                          {svc.enabled ? '禁用' : '启用'}
                        </button>
                      </div>
                    </td>
                  </tr>

                  {expanded === svc.name && (
                    <tr key={`${svc.name}-detail`}>
                      <td colSpan={6} className="px-4 py-4 bg-bg/50">
                        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
                          {/* Resource usage */}
                          <div className="bg-card border border-border rounded-lg p-4">
                            <h4 className="text-xs uppercase text-text3 mb-3">资源使用</h4>
                            {resources ? (
                              <dl className="space-y-2 text-sm">
                                {Object.entries(resources).map(([k, v]) => (
                                  <div key={k} className="flex justify-between">
                                    <dt className="text-text3">{k}</dt>
                                    <dd className="text-text font-mono">{v || '-'}</dd>
                                  </div>
                                ))}
                              </dl>
                            ) : (
                              <p className="text-text3 text-xs">加载中...</p>
                            )}
                          </div>

                          {/* Dependencies */}
                          <div className="bg-card border border-border rounded-lg p-4">
                            <h4 className="text-xs uppercase text-text3 mb-3">依赖关系</h4>
                            {deps ? (
                              <div className="space-y-2 text-sm">
                                {(['requires', 'required_by', 'wants', 'wanted_by'] as const).map((key) => (
                                  <div key={key}>
                                    <span className="text-text3 text-xs">{key}:</span>
                                    <div className="flex flex-wrap gap-1 mt-1">
                                      {deps[key]?.length ? (
                                        deps[key].map((d) => (
                                          <span
                                            key={d}
                                            className="px-2 py-0.5 rounded text-xs font-medium bg-accent-dim text-accent"
                                          >
                                            {d}
                                          </span>
                                        ))
                                      ) : (
                                        <span className="text-text3 text-xs">-</span>
                                      )}
                                    </div>
                                  </div>
                                ))}
                              </div>
                            ) : (
                              <p className="text-text3 text-xs">加载中...</p>
                            )}
                          </div>

                          {/* Journal */}
                          <div className="bg-card border border-border rounded-lg p-4 lg:col-span-1">
                            <h4 className="text-xs uppercase text-text3 mb-3">日志 (最近 50 行)</h4>
                            <pre className="text-xs text-text3 font-mono whitespace-pre-wrap max-h-64 overflow-y-auto bg-bg rounded p-2">
                              {journal?.journal || '加载中...'}
                            </pre>
                          </div>
                        </div>
                      </td>
                    </tr>
                  )}
                </React.Fragment>
              ))}
              {filtered.length === 0 && (
                <tr>
                  <td colSpan={6} className="text-center text-text3 py-8 text-sm">
                    无匹配服务
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
