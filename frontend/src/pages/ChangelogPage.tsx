/**
 * 运维变更日历页面 — 时间线 / 冻结窗口 / 统计
 */

import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import { cn, formatDate } from '@/lib/utils'
import { useAuthStore } from '@/stores/authStore'
import { changelogApi, type ChangeEvent, type FreezeWindow } from '@/api/changelog'

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const EVENT_TYPE_LABELS: Record<string, string> = {
  deploy: '部署',
  config: '配置',
  restart: '重启',
  maintenance: '维护',
  other: '其他',
}

const EVENT_TYPE_ICONS: Record<string, string> = {
  deploy: 'ti ti-rocket',
  config: 'ti ti-settings',
  restart: 'ti ti-refresh',
  maintenance: 'ti ti-tool',
  other: 'ti ti-activity',
}

const RISK_STYLES: Record<string, { dot: string; badge: string; label: string }> = {
  low: {
    dot: 'bg-green',
    badge: 'bg-green/15 text-green border border-green/30',
    label: '低',
  },
  medium: {
    dot: 'bg-yellow',
    badge: 'bg-yellow/15 text-yellow border border-yellow/30',
    label: '中',
  },
  high: {
    dot: 'bg-red',
    badge: 'bg-red/15 text-red border border-red/30',
    label: '高',
  },
}

const TIME_RANGES = [
  { label: '最近 7 天', days: 7 },
  { label: '最近 30 天', days: 30 },
  { label: '最近 90 天', days: 90 },
]

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function daysAgoISO(days: number): string {
  const d = new Date()
  d.setDate(d.getDate() - days)
  return d.toISOString()
}

function isWindowActive(w: FreezeWindow): boolean {
  const now = Date.now()
  return new Date(w.start_time).getTime() <= now && new Date(w.end_time).getTime() >= now
}

function isWindowUpcoming(w: FreezeWindow): boolean {
  return new Date(w.start_time).getTime() > Date.now()
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function RiskBadge({ risk }: { risk: string }) {
  const s = RISK_STYLES[risk] ?? RISK_STYLES.low
  return (
    <span className={cn('inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium', s.badge)}>
      {s.label}风险
    </span>
  )
}

function EventTypeIcon({ type }: { type: string }) {
  return (
    <span className={cn(EVENT_TYPE_ICONS[type] ?? 'ti ti-activity', 'text-base text-text3')} />
  )
}

// ---------------------------------------------------------------------------
// Modal: Create Event
// ---------------------------------------------------------------------------

interface CreateEventModalProps {
  onClose: () => void
  onSave: (data: Omit<ChangeEvent, 'id'>) => void
  isPending: boolean
}

function CreateEventModal({ onClose, onSave, isPending }: CreateEventModalProps) {
  const [form, setForm] = useState({
    title: '',
    event_type: 'deploy' as ChangeEvent['event_type'],
    risk_level: 'low' as ChangeEvent['risk_level'],
    affected_services: '',
    duration_minutes: '',
    description: '',
    timestamp: new Date().toISOString().slice(0, 16),
    operator: '',
  })

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!form.title.trim()) {
      toast.error('请输入变更标题')
      return
    }
    onSave({
      title: form.title.trim(),
      event_type: form.event_type,
      risk_level: form.risk_level,
      affected_services: form.affected_services.trim() || undefined,
      duration_minutes: form.duration_minutes ? Number(form.duration_minutes) : undefined,
      description: form.description.trim() || undefined,
      timestamp: new Date(form.timestamp).toISOString(),
      operator: form.operator.trim() || 'admin',
    })
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="bg-card border border-border rounded-xl w-full max-w-lg mx-4 shadow-xl">
        <div className="flex items-center justify-between px-5 py-4 border-b border-border">
          <h3 className="text-base font-semibold text-text">记录变更</h3>
          <button onClick={onClose} className="text-text3 hover:text-text">
            <span className="ti ti-x text-lg" />
          </button>
        </div>
        <form onSubmit={handleSubmit} className="p-5 space-y-4">
          <div>
            <label className="block text-xs text-text3 mb-1">变更标题 *</label>
            <input
              value={form.title}
              onChange={(e) => setForm((f) => ({ ...f, title: e.target.value }))}
              placeholder="简要描述此次变更"
              className="w-full bg-bg border border-border rounded-lg px-3 py-2 text-sm text-text focus:border-accent focus:outline-none"
            />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs text-text3 mb-1">事件类型</label>
              <select
                value={form.event_type}
                onChange={(e) => setForm((f) => ({ ...f, event_type: e.target.value as ChangeEvent['event_type'] }))}
                className="w-full bg-bg border border-border rounded-lg px-3 py-2 text-sm text-text focus:border-accent focus:outline-none"
              >
                {Object.entries(EVENT_TYPE_LABELS).map(([v, l]) => (
                  <option key={v} value={v}>{l}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-xs text-text3 mb-1">风险等级</label>
              <select
                value={form.risk_level}
                onChange={(e) => setForm((f) => ({ ...f, risk_level: e.target.value as ChangeEvent['risk_level'] }))}
                className="w-full bg-bg border border-border rounded-lg px-3 py-2 text-sm text-text focus:border-accent focus:outline-none"
              >
                <option value="low">低风险</option>
                <option value="medium">中风险</option>
                <option value="high">高风险</option>
              </select>
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs text-text3 mb-1">变更时间</label>
              <input
                type="datetime-local"
                value={form.timestamp}
                onChange={(e) => setForm((f) => ({ ...f, timestamp: e.target.value }))}
                className="w-full bg-bg border border-border rounded-lg px-3 py-2 text-sm text-text focus:border-accent focus:outline-none"
              />
            </div>
            <div>
              <label className="block text-xs text-text3 mb-1">持续时间（分钟）</label>
              <input
                type="number"
                min={1}
                value={form.duration_minutes}
                onChange={(e) => setForm((f) => ({ ...f, duration_minutes: e.target.value }))}
                placeholder="可选"
                className="w-full bg-bg border border-border rounded-lg px-3 py-2 text-sm text-text focus:border-accent focus:outline-none"
              />
            </div>
          </div>
          <div>
            <label className="block text-xs text-text3 mb-1">影响服务（逗号分隔）</label>
            <input
              value={form.affected_services}
              onChange={(e) => setForm((f) => ({ ...f, affected_services: e.target.value }))}
              placeholder="如: nginx, api, worker"
              className="w-full bg-bg border border-border rounded-lg px-3 py-2 text-sm text-text focus:border-accent focus:outline-none"
            />
          </div>
          <div>
            <label className="block text-xs text-text3 mb-1">详细描述</label>
            <textarea
              value={form.description}
              onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))}
              rows={3}
              placeholder="可选：填写变更原因、回滚方案等"
              className="w-full bg-bg border border-border rounded-lg px-3 py-2 text-sm text-text focus:border-accent focus:outline-none resize-none"
            />
          </div>
          <div className="flex justify-end gap-2 pt-1">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 text-sm text-text3 hover:text-text border border-border rounded-lg transition-colors"
            >
              取消
            </button>
            <button
              type="submit"
              disabled={isPending}
              className="px-4 py-2 text-sm bg-accent text-white rounded-lg hover:bg-accent/80 disabled:opacity-50 transition-colors"
            >
              {isPending ? '保存中...' : '保存'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Modal: Create Freeze Window
// ---------------------------------------------------------------------------

interface CreateFreezeModalProps {
  onClose: () => void
  onSave: (data: { title: string; start_time: string; end_time: string; reason?: string }) => void
  isPending: boolean
}

function CreateFreezeModal({ onClose, onSave, isPending }: CreateFreezeModalProps) {
  const tomorrow = new Date()
  tomorrow.setDate(tomorrow.getDate() + 1)
  const dayAfter = new Date(tomorrow)
  dayAfter.setDate(dayAfter.getDate() + 1)

  const [form, setForm] = useState({
    title: '',
    start_time: tomorrow.toISOString().slice(0, 16),
    end_time: dayAfter.toISOString().slice(0, 16),
    reason: '',
  })

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!form.title.trim()) {
      toast.error('请输入冻结窗口标题')
      return
    }
    if (new Date(form.end_time) <= new Date(form.start_time)) {
      toast.error('结束时间必须晚于开始时间')
      return
    }
    onSave({
      title: form.title.trim(),
      start_time: new Date(form.start_time).toISOString(),
      end_time: new Date(form.end_time).toISOString(),
      reason: form.reason.trim() || undefined,
    })
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="bg-card border border-border rounded-xl w-full max-w-md mx-4 shadow-xl">
        <div className="flex items-center justify-between px-5 py-4 border-b border-border">
          <h3 className="text-base font-semibold text-text">新增冻结窗口</h3>
          <button onClick={onClose} className="text-text3 hover:text-text">
            <span className="ti ti-x text-lg" />
          </button>
        </div>
        <form onSubmit={handleSubmit} className="p-5 space-y-4">
          <div>
            <label className="block text-xs text-text3 mb-1">窗口标题 *</label>
            <input
              value={form.title}
              onChange={(e) => setForm((f) => ({ ...f, title: e.target.value }))}
              placeholder="如: 春节期间变更冻结"
              className="w-full bg-bg border border-border rounded-lg px-3 py-2 text-sm text-text focus:border-accent focus:outline-none"
            />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs text-text3 mb-1">开始时间</label>
              <input
                type="datetime-local"
                value={form.start_time}
                onChange={(e) => setForm((f) => ({ ...f, start_time: e.target.value }))}
                className="w-full bg-bg border border-border rounded-lg px-3 py-2 text-sm text-text focus:border-accent focus:outline-none"
              />
            </div>
            <div>
              <label className="block text-xs text-text3 mb-1">结束时间</label>
              <input
                type="datetime-local"
                value={form.end_time}
                onChange={(e) => setForm((f) => ({ ...f, end_time: e.target.value }))}
                className="w-full bg-bg border border-border rounded-lg px-3 py-2 text-sm text-text focus:border-accent focus:outline-none"
              />
            </div>
          </div>
          <div>
            <label className="block text-xs text-text3 mb-1">原因说明</label>
            <textarea
              value={form.reason}
              onChange={(e) => setForm((f) => ({ ...f, reason: e.target.value }))}
              rows={2}
              placeholder="可选"
              className="w-full bg-bg border border-border rounded-lg px-3 py-2 text-sm text-text focus:border-accent focus:outline-none resize-none"
            />
          </div>
          <div className="flex justify-end gap-2 pt-1">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 text-sm text-text3 hover:text-text border border-border rounded-lg transition-colors"
            >
              取消
            </button>
            <button
              type="submit"
              disabled={isPending}
              className="px-4 py-2 text-sm bg-accent text-white rounded-lg hover:bg-accent/80 disabled:opacity-50 transition-colors"
            >
              {isPending ? '保存中...' : '创建'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main Page
// ---------------------------------------------------------------------------

export default function ChangelogPage() {
  const qc = useQueryClient()
  const isAdmin = useAuthStore((s) => s.isAdmin())

  const [rangeDays, setRangeDays] = useState(30)
  const [typeFilter, setTypeFilter] = useState('')
  const [operatorFilter, setOperatorFilter] = useState('')
  const [showCreateEvent, setShowCreateEvent] = useState(false)
  const [showCreateFreeze, setShowCreateFreeze] = useState(false)
  const [deletingEventId, setDeletingEventId] = useState<number | null>(null)
  const [deletingWindowId, setDeletingWindowId] = useState<number | null>(null)

  // Queries
  const { data: events = [], isLoading: eventsLoading, refetch: refetchEvents } = useQuery({
    queryKey: ['changelog-events', rangeDays, typeFilter, operatorFilter],
    queryFn: () =>
      changelogApi.getEvents({
        start: daysAgoISO(rangeDays),
        event_type: typeFilter || undefined,
        operator: operatorFilter || undefined,
        limit: 200,
      }),
  })

  const { data: freezeWindows = [], isLoading: freezeLoading, refetch: refetchFreeze } = useQuery({
    queryKey: ['changelog-freeze-windows'],
    queryFn: () => changelogApi.getFreezeWindows(),
  })

  const { data: stats } = useQuery({
    queryKey: ['changelog-stats', rangeDays],
    queryFn: () =>
      changelogApi.getStats({ start: daysAgoISO(7) }),
  })

  // Mutations
  const createEventMutation = useMutation({
    mutationFn: changelogApi.createEvent,
    onSuccess: () => {
      toast.success('变更记录已保存')
      setShowCreateEvent(false)
      qc.invalidateQueries({ queryKey: ['changelog-events'] })
      qc.invalidateQueries({ queryKey: ['changelog-stats'] })
    },
    onError: () => toast.error('保存失败'),
  })

  const deleteEventMutation = useMutation({
    mutationFn: changelogApi.deleteEvent,
    onSuccess: () => {
      toast.success('已删除')
      setDeletingEventId(null)
      qc.invalidateQueries({ queryKey: ['changelog-events'] })
      qc.invalidateQueries({ queryKey: ['changelog-stats'] })
    },
    onError: () => toast.error('删除失败'),
  })

  const createFreezeMutation = useMutation({
    mutationFn: changelogApi.createFreezeWindow,
    onSuccess: () => {
      toast.success('冻结窗口已创建')
      setShowCreateFreeze(false)
      qc.invalidateQueries({ queryKey: ['changelog-freeze-windows'] })
    },
    onError: () => toast.error('创建失败'),
  })

  const deleteFreezeWindowMutation = useMutation({
    mutationFn: changelogApi.deleteFreezeWindow,
    onSuccess: () => {
      toast.success('冻结窗口已删除')
      setDeletingWindowId(null)
      qc.invalidateQueries({ queryKey: ['changelog-freeze-windows'] })
    },
    onError: () => toast.error('删除失败'),
  })

  // Derived
  const operators = [...new Set(events.map((e) => e.operator).filter(Boolean))]
  const activeFreeze = freezeWindows.find(isWindowActive)
  const visibleWindows = freezeWindows.filter((w) => isWindowActive(w) || isWindowUpcoming(w))

  return (
    <div className="p-6 max-w-7xl mx-auto">
      <div className="flex gap-6">
        {/* ---------------------------------------------------------------- */}
        {/* Left: Timeline                                                   */}
        {/* ---------------------------------------------------------------- */}
        <div className="flex-1 min-w-0 space-y-4">
          {/* Header */}
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span className="ti ti-calendar-event text-accent text-xl" />
              <h1 className="text-xl font-semibold text-text">运维变更日历</h1>
              {eventsLoading && (
                <span className="ti ti-loader text-text3 animate-spin text-sm" />
              )}
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={() => { refetchEvents(); refetchFreeze() }}
                className="flex items-center gap-1.5 px-3 py-1.5 text-sm text-text3 hover:text-text border border-border rounded-lg transition-colors"
              >
                <span className="ti ti-refresh text-sm" />
                刷新
              </button>
              {isAdmin && (
                <button
                  onClick={() => setShowCreateEvent(true)}
                  className="flex items-center gap-1.5 px-3 py-1.5 text-sm bg-accent text-white rounded-lg hover:bg-accent/80 transition-colors"
                >
                  <span className="ti ti-plus text-sm" />
                  记录变更
                </button>
              )}
            </div>
          </div>

          {/* Filters */}
          <div className="flex flex-wrap items-center gap-2">
            {/* Time range */}
            <div className="flex gap-1 bg-card border border-border rounded-lg p-0.5">
              {TIME_RANGES.map((r) => (
                <button
                  key={r.days}
                  onClick={() => setRangeDays(r.days)}
                  className={cn(
                    'px-3 py-1 text-xs rounded-md transition-colors',
                    rangeDays === r.days
                      ? 'bg-accent text-white'
                      : 'text-text3 hover:text-text',
                  )}
                >
                  {r.label}
                </button>
              ))}
            </div>

            {/* Type filter */}
            <select
              value={typeFilter}
              onChange={(e) => setTypeFilter(e.target.value)}
              className="bg-bg border border-border rounded-lg px-2.5 py-1 text-xs text-text focus:border-accent focus:outline-none"
            >
              <option value="">全部类型</option>
              {Object.entries(EVENT_TYPE_LABELS).map(([v, l]) => (
                <option key={v} value={v}>{l}</option>
              ))}
            </select>

            {/* Operator filter */}
            {operators.length > 0 && (
              <select
                value={operatorFilter}
                onChange={(e) => setOperatorFilter(e.target.value)}
                className="bg-bg border border-border rounded-lg px-2.5 py-1 text-xs text-text focus:border-accent focus:outline-none"
              >
                <option value="">全部操作人</option>
                {operators.map((op) => (
                  <option key={op} value={op}>{op}</option>
                ))}
              </select>
            )}

            {events.length > 0 && (
              <span className="text-xs text-text3 ml-1">{events.length} 条记录</span>
            )}
          </div>

          {/* Timeline */}
          {events.length === 0 && !eventsLoading ? (
            <div className="flex flex-col items-center justify-center py-20 text-text3 bg-card border border-border rounded-xl">
              <span className="ti ti-calendar-off text-4xl opacity-40 mb-3" />
              <p className="text-sm">暂无变更记录</p>
              {isAdmin && (
                <button
                  onClick={() => setShowCreateEvent(true)}
                  className="mt-3 text-xs text-accent hover:underline"
                >
                  记录第一条变更
                </button>
              )}
            </div>
          ) : (
            <div className="relative space-y-0">
              {/* Vertical line */}
              <div className="absolute left-[19px] top-0 bottom-0 w-px bg-border" />

              {events.map((event) => {
                const riskStyle = RISK_STYLES[event.risk_level] ?? RISK_STYLES.low
                const services = event.affected_services
                  ? event.affected_services.split(',').map((s) => s.trim()).filter(Boolean)
                  : []
                const isDeleting = deletingEventId === event.id

                return (
                  <div key={event.id} className="relative flex gap-4 pb-4 group">
                    {/* Timeline dot */}
                    <div className="relative z-10 flex-shrink-0 mt-3.5">
                      <div className={cn('w-2.5 h-2.5 rounded-full ring-2 ring-bg', riskStyle.dot)} />
                    </div>

                    {/* Card */}
                    <div className="flex-1 bg-card border border-border rounded-lg p-3.5 hover:border-border/80 transition-colors min-w-0">
                      <div className="flex items-start justify-between gap-2">
                        <div className="flex items-center gap-2 min-w-0">
                          <EventTypeIcon type={event.event_type} />
                          <span className="font-medium text-text text-sm truncate">{event.title}</span>
                          <RiskBadge risk={event.risk_level} />
                          <span className="px-1.5 py-0.5 rounded text-[10px] bg-bg border border-border text-text3">
                            {EVENT_TYPE_LABELS[event.event_type] ?? event.event_type}
                          </span>
                        </div>
                        {isAdmin && (
                          <div className="flex-shrink-0">
                            {isDeleting ? (
                              <div className="flex items-center gap-1.5">
                                <span className="text-xs text-text3">确认删除?</span>
                                <button
                                  onClick={() => deleteEventMutation.mutate(event.id)}
                                  disabled={deleteEventMutation.isPending}
                                  className="px-2 py-0.5 text-xs bg-red/15 text-red rounded hover:bg-red/25 transition-colors"
                                >
                                  删除
                                </button>
                                <button
                                  onClick={() => setDeletingEventId(null)}
                                  className="px-2 py-0.5 text-xs border border-border text-text3 rounded hover:text-text transition-colors"
                                >
                                  取消
                                </button>
                              </div>
                            ) : (
                              <button
                                onClick={() => setDeletingEventId(event.id)}
                                className="opacity-0 group-hover:opacity-100 p-1 text-text3 hover:text-red transition-all"
                              >
                                <span className="ti ti-trash text-sm" />
                              </button>
                            )}
                          </div>
                        )}
                      </div>

                      <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-0.5 text-xs text-text3">
                        <span className="flex items-center gap-1">
                          <span className="ti ti-clock text-[11px]" />
                          {formatDate(event.timestamp)}
                        </span>
                        <span className="flex items-center gap-1">
                          <span className="ti ti-user text-[11px]" />
                          {event.operator}
                        </span>
                        {event.duration_minutes && (
                          <span className="flex items-center gap-1">
                            <span className="ti ti-hourglass text-[11px]" />
                            {event.duration_minutes} 分钟
                          </span>
                        )}
                      </div>

                      {services.length > 0 && (
                        <div className="mt-2 flex flex-wrap gap-1">
                          {services.map((svc) => (
                            <span
                              key={svc}
                              className="px-1.5 py-0.5 text-[10px] rounded bg-accent/10 text-accent border border-accent/20"
                            >
                              {svc}
                            </span>
                          ))}
                        </div>
                      )}

                      {event.description && (
                        <p className="mt-2 text-xs text-text3 leading-relaxed line-clamp-2">
                          {event.description}
                        </p>
                      )}
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </div>

        {/* ---------------------------------------------------------------- */}
        {/* Right sidebar                                                    */}
        {/* ---------------------------------------------------------------- */}
        <div className="w-72 flex-shrink-0 space-y-5">
          {/* Freeze Windows */}
          <div className="bg-card border border-border rounded-xl overflow-hidden">
            <div className="flex items-center justify-between px-4 py-3 border-b border-border">
              <div className="flex items-center gap-2">
                <span className="ti ti-snowflake text-accent text-base" />
                <span className="text-sm font-semibold text-text">变更冻结</span>
              </div>
              {isAdmin && (
                <button
                  onClick={() => setShowCreateFreeze(true)}
                  className="text-xs text-accent hover:text-accent/80 flex items-center gap-0.5"
                >
                  <span className="ti ti-plus text-xs" />
                  新增
                </button>
              )}
            </div>

            <div className="p-3 space-y-2">
              {/* Active freeze banner */}
              {activeFreeze && (
                <div className="flex items-start gap-2 p-2.5 rounded-lg bg-red/10 border border-red/30">
                  <span className="ti ti-alert-triangle text-red text-base flex-shrink-0 mt-0.5" />
                  <div>
                    <p className="text-xs font-semibold text-red">当前处于冻结期</p>
                    <p className="text-xs text-red/80 mt-0.5">{activeFreeze.title}</p>
                    <p className="text-[10px] text-red/60 mt-0.5">
                      至 {formatDate(activeFreeze.end_time)}
                    </p>
                  </div>
                </div>
              )}

              {freezeLoading ? (
                <p className="text-xs text-text3 py-2 text-center">加载中...</p>
              ) : visibleWindows.length === 0 ? (
                <p className="text-xs text-text3 py-4 text-center">无冻结窗口</p>
              ) : (
                visibleWindows.map((w) => {
                  const active = isWindowActive(w)
                  const upcoming = isWindowUpcoming(w)
                  const isDeleting = deletingWindowId === w.id

                  return (
                    <div
                      key={w.id}
                      className={cn(
                        'p-2.5 rounded-lg border text-xs group',
                        active
                          ? 'border-red/30 bg-red/5'
                          : upcoming
                          ? 'border-yellow/30 bg-yellow/5'
                          : 'border-border bg-bg',
                      )}
                    >
                      <div className="flex items-start justify-between gap-1">
                        <span className={cn('font-medium', active ? 'text-red' : upcoming ? 'text-yellow' : 'text-text')}>
                          {w.title}
                        </span>
                        {isAdmin && (
                          <div className="flex-shrink-0">
                            {isDeleting ? (
                              <div className="flex gap-1">
                                <button
                                  onClick={() => deleteFreezeWindowMutation.mutate(w.id)}
                                  disabled={deleteFreezeWindowMutation.isPending}
                                  className="text-[10px] text-red hover:underline"
                                >
                                  确认
                                </button>
                                <button
                                  onClick={() => setDeletingWindowId(null)}
                                  className="text-[10px] text-text3 hover:underline"
                                >
                                  取消
                                </button>
                              </div>
                            ) : (
                              <button
                                onClick={() => setDeletingWindowId(w.id)}
                                className="opacity-0 group-hover:opacity-100 text-text3 hover:text-red transition-all"
                              >
                                <span className="ti ti-trash text-xs" />
                              </button>
                            )}
                          </div>
                        )}
                      </div>
                      <div className="mt-1 text-text3 space-y-0.5">
                        <div>{formatDate(w.start_time)} — {formatDate(w.end_time)}</div>
                        {w.reason && <div className="text-[10px] opacity-70">{w.reason}</div>}
                      </div>
                      <div className="mt-1.5">
                        <span className={cn(
                          'inline-block px-1.5 py-0.5 rounded text-[9px] font-medium',
                          active ? 'bg-red/20 text-red' : 'bg-yellow/20 text-yellow',
                        )}>
                          {active ? '进行中' : '即将开始'}
                        </span>
                      </div>
                    </div>
                  )
                })
              )}
            </div>
          </div>

          {/* Stats: Last 7 days */}
          <div className="bg-card border border-border rounded-xl overflow-hidden">
            <div className="flex items-center gap-2 px-4 py-3 border-b border-border">
              <span className="ti ti-chart-bar text-accent text-base" />
              <span className="text-sm font-semibold text-text">近 7 天统计</span>
            </div>
            <div className="p-3 space-y-3">
              {/* Total */}
              <div className="flex items-center justify-between">
                <span className="text-xs text-text3">总变更次数</span>
                <span className="text-lg font-bold text-text">{stats?.total ?? 0}</span>
              </div>

              {/* By type */}
              {stats?.by_type && Object.keys(stats.by_type).length > 0 && (
                <div>
                  <p className="text-[10px] text-text3 mb-1.5 uppercase tracking-wider">按类型</p>
                  <div className="space-y-1">
                    {Object.entries(stats.by_type).map(([type, count]) => (
                      <div key={type} className="flex items-center justify-between">
                        <div className="flex items-center gap-1.5">
                          <EventTypeIcon type={type} />
                          <span className="text-xs text-text2">{EVENT_TYPE_LABELS[type] ?? type}</span>
                        </div>
                        <span className="text-xs font-medium text-text">{count}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* By risk */}
              {stats?.by_risk && Object.keys(stats.by_risk).length > 0 && (
                <div>
                  <p className="text-[10px] text-text3 mb-1.5 uppercase tracking-wider">按风险</p>
                  <div className="space-y-1">
                    {(['high', 'medium', 'low'] as const).map((risk) => {
                      const count = stats.by_risk[risk] ?? 0
                      const total = stats.total || 1
                      const pct = Math.round((count / total) * 100)
                      const style = RISK_STYLES[risk]
                      return (
                        <div key={risk} className="space-y-0.5">
                          <div className="flex items-center justify-between text-xs">
                            <span className="text-text2">{style.label}风险</span>
                            <span className="text-text3">{count}</span>
                          </div>
                          <div className="h-1 bg-bg rounded-full overflow-hidden">
                            <div
                              className={cn('h-full rounded-full transition-all', style.dot)}
                              style={{ width: `${pct}%` }}
                            />
                          </div>
                        </div>
                      )
                    })}
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Modals */}
      {showCreateEvent && (
        <CreateEventModal
          onClose={() => setShowCreateEvent(false)}
          onSave={(data) => createEventMutation.mutate(data)}
          isPending={createEventMutation.isPending}
        />
      )}
      {showCreateFreeze && (
        <CreateFreezeModal
          onClose={() => setShowCreateFreeze(false)}
          onSave={(data) => createFreezeMutation.mutate(data)}
          isPending={createFreezeMutation.isPending}
        />
      )}
    </div>
  )
}
