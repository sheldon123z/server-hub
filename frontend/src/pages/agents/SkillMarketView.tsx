/**
 * SkillMarketView - Market sub-view for discovering and installing remote skills.
 * Search, filter by category, install/update actions.
 */

import { useState, useMemo } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import { cn } from '@/lib/utils'
import {
  getMarketIndex,
  syncMarket,
  installFromMarket,
  type MarketSkill,
} from '@/api/skills'

export function SkillMarketView() {
  const qc = useQueryClient()
  const [search, setSearch] = useState('')
  const [category, setCategory] = useState<string>('all')

  const { data: market, isLoading } = useQuery({
    queryKey: ['skill-market'],
    queryFn: getMarketIndex,
  })

  const skills: MarketSkill[] = market?.skills ?? []
  const lastSync = market?.last_sync

  // Extract unique categories
  const categories = useMemo(() => {
    const cats = new Set<string>()
    skills.forEach((s) => {
      if (s.category) cats.add(s.category)
    })
    return ['all', ...Array.from(cats).sort()]
  }, [skills])

  // Filter skills
  const filtered = useMemo(() => {
    let list = skills
    if (category !== 'all') {
      list = list.filter((s) => s.category === category)
    }
    if (search.trim()) {
      const q = search.toLowerCase()
      list = list.filter(
        (s) =>
          s.name.toLowerCase().includes(q) ||
          s.description.toLowerCase().includes(q) ||
          s.tags?.some((t) => t.toLowerCase().includes(q)),
      )
    }
    return list
  }, [skills, category, search])

  // Sync mutation
  const syncMut = useMutation({
    mutationFn: syncMarket,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['skill-market'] })
      toast.success('市场索引已同步')
    },
    onError: () => toast.error('同步失败'),
  })

  // Install mutation
  const installMut = useMutation({
    mutationFn: ({ name, version }: { name: string; version?: string }) =>
      installFromMarket(name, version),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['skill-market'] })
      qc.invalidateQueries({ queryKey: ['admin-skills'] })
      toast.success('安装成功')
    },
    onError: () => toast.error('安装失败'),
  })

  return (
    <div className="space-y-4">
      {/* Search + filter */}
      <div className="flex items-center gap-3">
        <input
          type="text"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="搜索技能..."
          className="flex-1 rounded-lg border border-border bg-bg px-3 py-2 text-sm text-text placeholder:text-text3 focus:border-accent/50 focus:outline-none"
        />
        <select
          value={category}
          onChange={(e) => setCategory(e.target.value)}
          className="rounded-lg border border-border bg-bg px-3 py-2 text-sm text-text focus:border-accent/50 focus:outline-none"
        >
          {categories.map((c) => (
            <option key={c} value={c}>
              {c === 'all' ? '全部分类' : c}
            </option>
          ))}
        </select>
      </div>

      {/* Skills grid */}
      {isLoading ? (
        <div className="text-sm text-text3 text-center py-12">加载中...</div>
      ) : filtered.length === 0 ? (
        <div className="text-center py-12">
          <div className="text-text3 text-sm">
            {skills.length === 0 ? '市场暂无技能，请先同步' : '无匹配结果'}
          </div>
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
          {filtered.map((skill) => (
            <MarketCard
              key={skill.name}
              skill={skill}
              onInstall={(version) =>
                installMut.mutate({ name: skill.name, version })
              }
              installing={installMut.isPending}
            />
          ))}
        </div>
      )}

      {/* Footer: sync info */}
      <div className="flex items-center justify-between border-t border-border pt-3">
        <div className="text-xs text-text3">
          {lastSync ? `上次同步: ${lastSync}` : '未同步'}
          {market?.source_count != null && ` \u00B7 ${market.source_count} 个远程源`}
        </div>
        <button
          type="button"
          onClick={() => syncMut.mutate()}
          disabled={syncMut.isPending}
          className="rounded-lg border border-border px-3 py-1.5 text-xs text-text2 transition-colors hover:border-accent/40 disabled:opacity-50"
        >
          {syncMut.isPending ? '同步中...' : '\uD83D\uDD04 同步市场'}
        </button>
      </div>
    </div>
  )
}

// ── Market skill card ───────────────────────────────────

function MarketCard({
  skill,
  onInstall,
  installing,
}: {
  skill: MarketSkill
  onInstall: (version?: string) => void
  installing: boolean
}) {
  return (
    <div className="rounded-xl border border-border bg-bg p-4 transition-colors hover:border-border/80">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className="text-sm font-medium text-text truncate">{skill.name}</span>
            <span className="text-[11px] text-text3">v{skill.version}</span>
          </div>
          <div className="mt-1 text-xs text-text3 line-clamp-2">{skill.description}</div>
          <div className="mt-2 flex flex-wrap items-center gap-2 text-[11px] text-text3">
            {skill.author && <span>{skill.author}</span>}
            {skill.category && (
              <span className="rounded bg-bg2 px-1.5 py-0.5">{skill.category}</span>
            )}
            {skill.tags?.map((t) => (
              <span key={t} className="rounded bg-bg2 px-1.5 py-0.5">
                {t}
              </span>
            ))}
          </div>
        </div>

        <div className="shrink-0">
          {skill.updatable ? (
            <div className="flex flex-col items-end gap-1">
              <span className="text-[11px] text-text3">
                {skill.installed_version} &rarr; {skill.version}
              </span>
              <button
                type="button"
                onClick={() => onInstall(skill.version)}
                disabled={installing}
                className="rounded-lg bg-accent px-3 py-1.5 text-xs font-medium text-[#0f172a] transition-colors hover:bg-accent/80 disabled:opacity-50"
              >
                更新
              </button>
            </div>
          ) : skill.installed ? (
            <span className="rounded-lg bg-bg2 px-3 py-1.5 text-xs text-text3">已安装</span>
          ) : (
            <button
              type="button"
              onClick={() => onInstall()}
              disabled={installing}
              className={cn(
                'rounded-lg border border-accent/50 px-3 py-1.5 text-xs font-medium text-accent transition-colors hover:bg-accent/10 disabled:opacity-50',
              )}
            >
              安装
            </button>
          )}
        </div>
      </div>
    </div>
  )
}
