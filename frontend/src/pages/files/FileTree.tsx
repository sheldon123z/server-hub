/**
 * FileTree — 懒加载目录树，点击展开子目录
 */

import { useState, useEffect, useCallback } from 'react'
import client from '@/api/client'
import { cn } from '@/lib/utils'
import type { FileEntry } from './types'

interface FileTreeProps {
  currentPath: string
  onNavigate: (path: string) => void
}

export function FileTree({ currentPath, onNavigate }: FileTreeProps) {
  const [expanded, setExpanded] = useState<Set<string>>(new Set(['/']))
  const [cache, setCache] = useState<Map<string, FileEntry[]>>(new Map())
  const [loading, setLoading] = useState<Set<string>>(new Set())

  const loadDir = useCallback(async (path: string) => {
    if (cache.has(path) || loading.has(path)) return
    setLoading((s) => new Set([...s, path]))
    try {
      const r = await client.get<{ entries: FileEntry[] }>('/api/files/list', {
        params: { path, sort: 'name' },
      })
      const dirs = (r.data.entries ?? []).filter((e) => e.type === 'directory')
      setCache((c) => new Map(c).set(path, dirs))
    } catch {
      setCache((c) => new Map(c).set(path, []))
    } finally {
      setLoading((s) => {
        const n = new Set(s)
        n.delete(path)
        return n
      })
    }
  }, [cache, loading])

  useEffect(() => {
    loadDir('/')
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const toggle = useCallback(
    async (path: string) => {
      if (expanded.has(path)) {
        setExpanded((s) => {
          const n = new Set(s)
          n.delete(path)
          return n
        })
      } else {
        setExpanded((s) => new Set([...s, path]))
        await loadDir(path)
      }
    },
    [expanded, loadDir],
  )

  return (
    <div className="py-2 px-1 select-none">
      <TreeItem
        name="/"
        path="/"
        depth={0}
        expanded={expanded}
        cache={cache}
        loading={loading}
        currentPath={currentPath}
        onToggle={toggle}
        onNavigate={onNavigate}
      />
    </div>
  )
}

interface TreeItemProps {
  name: string
  path: string
  depth: number
  expanded: Set<string>
  cache: Map<string, FileEntry[]>
  loading: Set<string>
  currentPath: string
  onToggle: (path: string) => void
  onNavigate: (path: string) => void
}

function TreeItem({
  name,
  path,
  depth,
  expanded,
  cache,
  loading,
  currentPath,
  onToggle,
  onNavigate,
}: TreeItemProps) {
  const isExpanded = expanded.has(path)
  const isActive = currentPath === path
  const isLoading = loading.has(path)
  const children = cache.get(path) ?? []

  const handleClick = () => {
    onNavigate(path)
    onToggle(path)
  }

  return (
    <div>
      <button
        className={cn(
          'flex items-center gap-1 w-full text-left py-1 pr-2 rounded text-[13px] transition-colors',
          isActive
            ? 'bg-accent-dim text-accent'
            : 'text-text2 hover:text-text hover:bg-card',
        )}
        style={{ paddingLeft: `${6 + depth * 14}px` }}
        onClick={handleClick}
      >
        {isLoading ? (
          <i className="ti ti-loader-2 animate-spin text-[10px] shrink-0 text-text3" />
        ) : isExpanded ? (
          <i className="ti ti-chevron-down text-[10px] shrink-0" />
        ) : (
          <i className="ti ti-chevron-right text-[10px] shrink-0" />
        )}
        <i className={cn('ti shrink-0', isExpanded ? 'ti-folder-open text-yellow' : 'ti-folder text-yellow')} />
        <span className="truncate">{name}</span>
      </button>

      {isExpanded && children.length > 0 && (
        <div>
          {children.map((child) => (
            <TreeItem
              key={child.path}
              name={child.name}
              path={child.path}
              depth={depth + 1}
              expanded={expanded}
              cache={cache}
              loading={loading}
              currentPath={currentPath}
              onToggle={onToggle}
              onNavigate={onNavigate}
            />
          ))}
        </div>
      )}
    </div>
  )
}
