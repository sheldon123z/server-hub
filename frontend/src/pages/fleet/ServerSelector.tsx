/**
 * ServerSelector — 服务器多选组件
 * 支持全选、按分组筛选、搜索
 */
import { useState, useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import client from '@/api/client'
import { cn } from '@/lib/utils'

interface Server {
  id: string
  name: string
  hostname: string
  ip_address: string
  status: string
  tags: string | string[]
  groups: string
}

interface ServerGroup {
  id: string
  name: string
  description: string
  server_count: number
}

interface ServerSelectorProps {
  selected: string[]
  onChange: (ids: string[]) => void
}

function parseGroups(groups: string | undefined | null): string[] {
  if (!groups) return []
  return groups.split(',').map((g) => g.trim()).filter(Boolean)
}

const STATUS_DOT: Record<string, string> = {
  online: 'bg-green',
  offline: 'bg-red',
  degraded: 'bg-yellow',
  unknown: 'bg-text3',
}

export default function ServerSelector({ selected, onChange }: ServerSelectorProps) {
  const [search, setSearch] = useState('')
  const [groupFilter, setGroupFilter] = useState<string>('all')

  const { data: servers = [] } = useQuery<Server[]>({
    queryKey: ['servers'],
    queryFn: async () => {
      const res = await client.get('/api/servers')
      return Array.isArray(res.data) ? res.data : (res.data?.servers ?? [])
    },
  })

  const { data: groups = [] } = useQuery<ServerGroup[]>({
    queryKey: ['server-groups'],
    queryFn: async () => {
      const res = await client.get('/api/servers/groups')
      return Array.isArray(res.data) ? res.data : (res.data?.groups ?? [])
    },
  })

  const filtered = useMemo(() => {
    let list = servers
    if (groupFilter !== 'all') {
      list = list.filter((s) => parseGroups(s.groups).includes(groupFilter))
    }
    if (search.trim()) {
      const q = search.toLowerCase()
      list = list.filter(
        (s) =>
          s.name.toLowerCase().includes(q) ||
          s.ip_address.toLowerCase().includes(q) ||
          s.hostname.toLowerCase().includes(q),
      )
    }
    return list
  }, [servers, groupFilter, search])

  const allFilteredIds = filtered.map((s) => s.id)
  const allFilteredSelected =
    allFilteredIds.length > 0 && allFilteredIds.every((id) => selected.includes(id))

  const toggleAll = () => {
    if (allFilteredSelected) {
      onChange(selected.filter((id) => !allFilteredIds.includes(id)))
    } else {
      const next = [...new Set([...selected, ...allFilteredIds])]
      onChange(next)
    }
  }

  const toggle = (id: string) => {
    if (selected.includes(id)) {
      onChange(selected.filter((x) => x !== id))
    } else {
      onChange([...selected, id])
    }
  }

  return (
    <div className="space-y-3">
      {/* 搜索 + 已选计数 */}
      <div className="flex items-center gap-2">
        <input
          type="text"
          placeholder="搜索服务器..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="flex-1 bg-bg border border-border rounded-md px-3 py-1.5 text-xs text-text placeholder:text-text3 focus:outline-none focus:border-accent"
        />
        <span className="text-xs text-text3 shrink-0">
          已选{' '}
          <span className="text-accent font-medium">{selected.length}</span>{' '}
          台
        </span>
      </div>

      {/* 分组筛选 */}
      {groups.length > 0 && (
        <div className="flex gap-1 flex-wrap">
          <button
            onClick={() => setGroupFilter('all')}
            className={cn(
              'px-2 py-1 text-xs rounded transition-colors',
              groupFilter === 'all'
                ? 'bg-accent text-[#0f172a]'
                : 'bg-bg2 text-text3 hover:text-text2',
            )}
          >
            全部
          </button>
          {groups.map((g) => (
            <button
              key={g.id}
              onClick={() => setGroupFilter(g.name)}
              className={cn(
                'px-2 py-1 text-xs rounded transition-colors',
                groupFilter === g.name
                  ? 'bg-accent text-[#0f172a]'
                  : 'bg-bg2 text-text3 hover:text-text2',
              )}
            >
              {g.name}
            </button>
          ))}
        </div>
      )}

      {/* 全选行 */}
      <label className="flex items-center gap-2 text-xs cursor-pointer py-1.5 border-b border-border">
        <input
          type="checkbox"
          checked={allFilteredSelected}
          onChange={toggleAll}
          className="rounded border-border bg-bg text-accent"
        />
        <span className="text-text3">全选当前列表（{filtered.length} 台）</span>
      </label>

      {/* 服务器列表 */}
      <div className="space-y-1 max-h-[320px] overflow-y-auto">
        {filtered.map((srv) => (
          <label
            key={srv.id}
            className={cn(
              'flex items-center gap-3 p-2 rounded-md cursor-pointer transition-colors',
              selected.includes(srv.id) ? 'bg-accent-dim' : 'hover:bg-bg2',
            )}
          >
            <input
              type="checkbox"
              checked={selected.includes(srv.id)}
              onChange={() => toggle(srv.id)}
              className="rounded border-border bg-bg text-accent"
            />
            <span
              className={cn(
                'w-2 h-2 rounded-full shrink-0',
                STATUS_DOT[srv.status] ?? STATUS_DOT.unknown,
              )}
            />
            <div className="flex-1 min-w-0">
              <div className="text-sm text-text truncate">{srv.name}</div>
              <div className="text-[10px] text-text3">{srv.ip_address}</div>
            </div>
            <span
              className={cn(
                'text-[10px] px-1.5 py-0.5 rounded shrink-0',
                srv.status === 'online'
                  ? 'text-green bg-green/10'
                  : 'text-text3 bg-bg2',
              )}
            >
              {srv.status === 'online'
                ? '在线'
                : srv.status === 'offline'
                  ? '离线'
                  : srv.status}
            </span>
          </label>
        ))}
        {filtered.length === 0 && (
          <div className="text-center text-text3 text-xs py-8">无匹配服务器</div>
        )}
      </div>
    </div>
  )
}
