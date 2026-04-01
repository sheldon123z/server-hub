/**
 * 资产管理页面 — 网络资产发现与管理
 *
 * 功能: 资产自动发现 / 手动添加 / 分组管理 / 状态跟踪
 * API 前缀: /api/assets
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useState, useRef, useEffect, useCallback } from 'react'
import client from '@/api/client'
import toast from 'react-hot-toast'
import { cn, ensureArray, ensureRecord, toNumber, toString } from '@/lib/utils'
import { useServerStore } from '@/stores/serverStore'
import mermaid from 'mermaid'

/* ── Types ────────────────────────────────────────── */

interface Asset {
  id: number
  name: string
  type: string
  description: string
  ip: string
  port: number | null
  status: string
  source: string
  created_at: string
  updated_at: string
}

interface AssetSummary {
  by_type: Record<string, number>
  by_status: Record<string, number>
  total: number
}

/* ── Helpers ──────────────────────────────────────── */

const TYPE_COLORS: Record<string, string> = {
  docker: 'bg-accent-dim text-accent',
  systemd: 'bg-green/20 text-green',
  network: 'bg-yellow/20 text-yellow',
  manual: 'bg-text3/20 text-text3',
}

function typeBadge(type: string) {
  return TYPE_COLORS[type] || 'bg-text3/20 text-text3'
}

function normalizeAssets(value: unknown): Asset[] {
  const items = Array.isArray(value) ? value : ensureRecord(value).assets
  return ensureArray<Record<string, unknown>>(items).map((item, index) => {
    const properties = ensureRecord(item.properties)
    return {
      id: toNumber(item.id, index + 1),
      name: toString(item.name, 'unknown'),
      type: toString(item.type, 'manual'),
      description: toString(item.description ?? properties.description),
      ip: toString(item.ip ?? properties.ip ?? properties.local_addr),
      port: item.port == null ? null : (Number.isFinite(Number(item.port)) ? Number(item.port) : null),
      status: toString(item.status, 'unknown'),
      source: toString(item.source, Boolean(item.is_manual) ? 'manual' : 'auto'),
      created_at: toString(item.created_at ?? item.last_seen),
      updated_at: toString(item.updated_at ?? item.last_seen),
    }
  })
}

function normalizeAssetSummary(value: unknown): AssetSummary {
  const record = ensureRecord(value)
  const byType: Record<string, number> = {}
  let total = 0

  for (const [key, raw] of Object.entries(record)) {
    const entry = ensureRecord(raw)
    const count = toNumber(entry.total, 0)
    byType[key] = count
    total += count
  }

  return {
    by_type: byType,
    by_status: {},
    total,
  }
}

/* ── Topology Diagram ────────────────────────────── */

mermaid.initialize({ startOnLoad: false, theme: 'dark' })

function TopologyDiagram({ serverId }: { serverId: string }) {
  const containerRef = useRef<HTMLDivElement>(null)
  const [rendered, setRendered] = useState(false)

  const { data, isLoading, error } = useQuery<{ mermaid: string }>({
    queryKey: ['assets-topology', serverId],
    queryFn: () => client.get('/api/assets/topology', { params: { server_id: serverId } }).then((r) => r.data),
  })

  const renderDiagram = useCallback(async () => {
    if (!data?.mermaid || !containerRef.current) return
    try {
      const id = `mermaid-topology-${Date.now()}`
      const { svg } = await mermaid.render(id, data.mermaid)
      if (containerRef.current) {
        containerRef.current.innerHTML = svg
        setRendered(true)
      }
    } catch {
      if (containerRef.current) {
        containerRef.current.innerHTML = '<p class="text-red text-sm p-4">Mermaid 渲染失败</p>'
      }
    }
  }, [data])

  useEffect(() => {
    if (data?.mermaid) renderDiagram()
  }, [data, renderDiagram])

  if (isLoading) return <p className="text-text3 text-sm py-8 text-center">加载拓扑数据...</p>
  if (error) return <p className="text-red text-sm py-8 text-center">拓扑数据加载失败</p>
  if (!data?.mermaid) return <p className="text-text3 text-sm py-8 text-center">暂无拓扑数据</p>

  return (
    <div className="bg-card border border-border rounded-lg p-4 overflow-auto">
      <div ref={containerRef} className="flex justify-center" />
    </div>
  )
}

/* ── Page ─────────────────────────────────────────── */

/** 资产管理主页面，含资产列表、发现任务和分组管理 */
export default function AssetsPage() {
  const queryClient = useQueryClient()
  const serverId = useServerStore((s) => s.selectedServerId)
  const [editingId, setEditingId] = useState<number | null>(null)
  const [editDesc, setEditDesc] = useState('')
  const [showAdd, setShowAdd] = useState(false)
  const [showTopology, setShowTopology] = useState(false)
  const [newAsset, setNewAsset] = useState({ name: '', type: 'manual', description: '', ip: '', port: '' })

  /* Queries */
  const { data: assetsData, isLoading } = useQuery<Asset[]>({
    queryKey: ['assets', serverId],
    queryFn: () => client.get('/api/assets/', { params: { server_id: serverId } }).then((r) => normalizeAssets(r.data)),
  })

  const { data: summary } = useQuery<AssetSummary>({
    queryKey: ['assets-summary', serverId],
    queryFn: () => client.get('/api/assets/summary', { params: { server_id: serverId } }).then((r) => normalizeAssetSummary(r.data)),
  })

  /* Mutations */
  const invalidateAssets = () => {
    queryClient.invalidateQueries({ queryKey: ['assets', serverId] })
    queryClient.invalidateQueries({ queryKey: ['assets-summary', serverId] })
    queryClient.invalidateQueries({ queryKey: ['assets-topology', serverId] })
  }

  const discoverMut = useMutation({
    mutationFn: () => client.post(`/api/assets/discover?server_id=${encodeURIComponent(serverId)}`).then((r) => r.data),
    onSuccess: (data) => {
      toast.success(`发现完成: ${data.total} 个资产`)
      invalidateAssets()
    },
    onError: () => toast.error('发现失败'),
  })

  const updateDescMut = useMutation({
    mutationFn: ({ id, description }: { id: number; description: string }) =>
      client.put(`/api/assets/${id}?server_id=${encodeURIComponent(serverId)}`, { description }).then((r) => r.data),
    onSuccess: () => {
      toast.success('描述已更新')
      setEditingId(null)
      invalidateAssets()
    },
    onError: () => toast.error('更新失败'),
  })

  const addMut = useMutation({
    mutationFn: (body: { name: string; type: string; description: string; ip: string; port: number | null }) =>
      client.post(`/api/assets/manual?server_id=${encodeURIComponent(serverId)}`, body).then((r) => r.data),
    onSuccess: () => {
      toast.success('资产已添加')
      setShowAdd(false)
      setNewAsset({ name: '', type: 'manual', description: '', ip: '', port: '' })
      invalidateAssets()
    },
    onError: () => toast.error('添加失败'),
  })

  const deleteMut = useMutation({
    mutationFn: (id: number) => client.delete(`/api/assets/${id}?server_id=${encodeURIComponent(serverId)}`).then((r) => r.data),
    onSuccess: () => {
      toast.success('资产已删除')
      invalidateAssets()
    },
    onError: () => toast.error('删除失败'),
  })

  const assets = ensureArray<Asset>(assetsData)

  /* Summary cards */
  const typeEntries = summary?.by_type ? Object.entries(summary.by_type) : []

  const inputCls = 'bg-bg border border-border rounded-md px-3 py-2 text-sm text-text focus:border-accent focus:outline-none'

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold">资产管理</h2>
        <div className="flex gap-2">
          <button
            className={cn(
              'px-3 py-1.5 rounded-md text-sm hover:opacity-90 transition-colors',
              showTopology ? 'bg-accent text-[#0f172a] font-medium' : 'bg-accent-dim text-accent',
            )}
            onClick={() => setShowTopology(!showTopology)}
          >
            拓扑
          </button>
          <button
            className="bg-accent-dim text-accent px-3 py-1.5 rounded-md text-sm hover:opacity-90 disabled:opacity-50"
            disabled={discoverMut.isPending}
            onClick={() => discoverMut.mutate()}
          >
            {discoverMut.isPending ? '发现中...' : '发现资产'}
          </button>
          <button
            className="bg-accent text-[#0f172a] px-3 py-1.5 rounded-md text-sm font-medium hover:opacity-90"
            onClick={() => setShowAdd(!showAdd)}
          >
            手动添加
          </button>
        </div>
      </div>

      {/* Summary cards */}
      {summary && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          {typeEntries.map(([type, count]) => (
            <div key={type} className="bg-card border border-border rounded-lg p-4">
              <div className="text-text3 text-xs uppercase mb-1">{type}</div>
              <div className="text-2xl font-bold text-text">{count}</div>
            </div>
          ))}
          <div className="bg-card border border-border rounded-lg p-4">
            <div className="text-text3 text-xs uppercase mb-1">总计</div>
            <div className="text-2xl font-bold text-accent">{summary.total}</div>
          </div>
        </div>
      )}

      {/* Topology diagram */}
      {showTopology && <TopologyDiagram serverId={serverId} />}

      {/* Add form */}
      {showAdd && (
        <div className="bg-card border border-border rounded-lg p-4">
          <h3 className="text-sm font-medium text-text mb-3">手动添加资产</h3>
          <div className="grid grid-cols-1 md:grid-cols-5 gap-3">
            <input
              type="text"
              placeholder="名称"
              value={newAsset.name}
              onChange={(e) => setNewAsset({ ...newAsset, name: e.target.value })}
              className={inputCls}
            />
            <select
              value={newAsset.type}
              onChange={(e) => setNewAsset({ ...newAsset, type: e.target.value })}
              className={inputCls}
            >
              <option value="manual">手动</option>
              <option value="docker">Docker</option>
              <option value="systemd">Systemd</option>
              <option value="network">网络</option>
            </select>
            <input
              type="text"
              placeholder="IP 地址"
              value={newAsset.ip}
              onChange={(e) => setNewAsset({ ...newAsset, ip: e.target.value })}
              className={inputCls}
            />
            <input
              type="text"
              placeholder="端口"
              value={newAsset.port}
              onChange={(e) => setNewAsset({ ...newAsset, port: e.target.value })}
              className={inputCls}
            />
            <input
              type="text"
              placeholder="描述"
              value={newAsset.description}
              onChange={(e) => setNewAsset({ ...newAsset, description: e.target.value })}
              className={inputCls}
            />
          </div>
          <div className="flex justify-end gap-2 mt-3">
            <button
              className="bg-text3/20 text-text3 px-3 py-1.5 rounded-md text-sm hover:bg-text3/30"
              onClick={() => setShowAdd(false)}
            >
              取消
            </button>
            <button
              className="bg-accent text-[#0f172a] px-3 py-1.5 rounded-md text-sm font-medium hover:opacity-90 disabled:opacity-50"
              disabled={addMut.isPending || !newAsset.name.trim()}
              onClick={() =>
                addMut.mutate({
                  name: newAsset.name,
                  type: newAsset.type,
                  description: newAsset.description,
                  ip: newAsset.ip,
                  port: newAsset.port ? parseInt(newAsset.port, 10) : null,
                })
              }
            >
              添加
            </button>
          </div>
        </div>
      )}

      {/* Asset table */}
      {isLoading ? (
        <div className="text-text3 text-sm py-8 text-center">加载中...</div>
      ) : (
        <div className="bg-card border border-border rounded-lg overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border">
                <th className="text-text3 text-left text-xs uppercase px-4 py-3">名称</th>
                <th className="text-text3 text-left text-xs uppercase px-4 py-3">类型</th>
                <th className="text-text3 text-left text-xs uppercase px-4 py-3">IP</th>
                <th className="text-text3 text-left text-xs uppercase px-4 py-3">端口</th>
                <th className="text-text3 text-left text-xs uppercase px-4 py-3">状态</th>
                <th className="text-text3 text-left text-xs uppercase px-4 py-3">来源</th>
                <th className="text-text3 text-left text-xs uppercase px-4 py-3">描述</th>
                <th className="text-text3 text-right text-xs uppercase px-4 py-3">操作</th>
              </tr>
            </thead>
            <tbody>
              {assets.map((a) => (
                <tr key={a.id} className="border-b border-border hover:bg-bg2/50 transition-colors">
                  <td className="px-4 py-3 text-text font-medium">{a.name}</td>
                  <td className="px-4 py-3">
                    <span className={cn('px-2 py-0.5 rounded text-xs font-medium', typeBadge(a.type))}>
                      {a.type}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-text3 font-mono text-xs">{a.ip || '-'}</td>
                  <td className="px-4 py-3 text-text3 font-mono text-xs">{a.port ?? '-'}</td>
                  <td className="px-4 py-3">
                    <span className="flex items-center gap-1.5">
                      <span
                        className={cn(
                          'w-2 h-2 rounded-full inline-block',
                          a.status === 'online' ? 'bg-green' : 'bg-red',
                        )}
                      />
                      <span className="text-text3 text-xs">{a.status}</span>
                    </span>
                  </td>
                  <td className="px-4 py-3 text-text3 text-xs">{a.source}</td>
                  <td className="px-4 py-3">
                    {editingId === a.id ? (
                      <div className="flex items-center gap-1">
                        <input
                          type="text"
                          value={editDesc}
                          onChange={(e) => setEditDesc(e.target.value)}
                          onKeyDown={(e) => {
                            if (e.key === 'Enter') updateDescMut.mutate({ id: a.id, description: editDesc })
                            if (e.key === 'Escape') setEditingId(null)
                          }}
                          className="bg-bg border border-border rounded-md px-2 py-1 text-xs text-text focus:border-accent focus:outline-none w-full"
                          autoFocus
                        />
                        <button
                          className="bg-accent text-[#0f172a] px-2 py-1 rounded text-xs font-medium hover:opacity-90 disabled:opacity-50 shrink-0"
                          disabled={updateDescMut.isPending}
                          onClick={() => updateDescMut.mutate({ id: a.id, description: editDesc })}
                        >
                          保存
                        </button>
                      </div>
                    ) : (
                      <span
                        className="text-text3 text-xs cursor-pointer hover:text-text"
                        onClick={() => {
                          setEditingId(a.id)
                          setEditDesc(a.description || '')
                        }}
                      >
                        {a.description || '点击编辑'}
                      </span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-right">
                    <button
                      className="bg-red/20 text-red px-3 py-1.5 rounded-md text-sm hover:bg-red/30 disabled:opacity-50"
                      disabled={deleteMut.isPending}
                      onClick={() => {
                        if (confirm(`确认删除资产「${a.name}」?`)) {
                          deleteMut.mutate(a.id)
                        }
                      }}
                    >
                      删除
                    </button>
                  </td>
                </tr>
              ))}
              {assets.length === 0 && (
                <tr>
                  <td colSpan={8} className="text-center text-text3 py-8 text-sm">
                    无资产数据，请点击「发现资产」
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
