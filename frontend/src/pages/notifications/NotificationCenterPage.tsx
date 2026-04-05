import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import client from '@/api/client'
import { cn, formatDate } from '@/lib/utils'

interface InAppNotification {
  id: number
  user_id: string | null
  type: string
  title: string
  content: string | null
  severity: string
  read: boolean
  related_alert_id: string | null
  created_at: string
}

const SEVERITY_STYLE: Record<string, { dot: string; badge: string }> = {
  critical: { dot: 'bg-red', badge: 'bg-red/20 text-red' },
  error: { dot: 'bg-red', badge: 'bg-red/20 text-red' },
  warning: { dot: 'bg-yellow', badge: 'bg-yellow/20 text-yellow' },
  info: { dot: 'bg-accent', badge: 'bg-accent-dim text-accent' },
  success: { dot: 'bg-green', badge: 'bg-green/20 text-green' },
}

const TYPE_LABEL: Record<string, string> = {
  alert: '告警',
  system: '系统',
  digest: '摘要',
  action: '操作',
}

/**
 * 通知中心页面
 * 展示所有站内通知，支持已读/未读过滤和全部标记已读
 */
export default function NotificationCenterPage() {
  const [unreadOnly, setUnreadOnly] = useState(false)
  const [page, setPage] = useState(0)
  const PAGE_SIZE = 20
  const qc = useQueryClient()

  const { data, isLoading } = useQuery<{ items: InAppNotification[]; total: number }>({
    queryKey: ['notif-center', unreadOnly, page],
    queryFn: () =>
      client
        .get('/api/notifications', {
          params: { unread_only: unreadOnly, limit: PAGE_SIZE, offset: page * PAGE_SIZE },
        })
        .then((r) => r.data),
  })

  const readAllMut = useMutation({
    mutationFn: () => client.put('/api/notifications/read-all').then((r) => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['notif-center'] })
      qc.invalidateQueries({ queryKey: ['notif-unread-count'] })
    },
  })

  const readOneMut = useMutation({
    mutationFn: (id: number) => client.put(`/api/notifications/${id}/read`).then((r) => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['notif-center'] })
      qc.invalidateQueries({ queryKey: ['notif-unread-count'] })
    },
  })

  const items = data?.items ?? []
  const total = data?.total ?? 0
  const totalPages = Math.ceil(total / PAGE_SIZE)

  const handleUnreadOnly = (v: boolean) => {
    setUnreadOnly(v)
    setPage(0)
  }

  return (
    <div>
      {/* 工具栏 */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-3">
          <h2 className="text-lg font-semibold">通知中心</h2>
          <span className="text-xs text-text3">共 {total} 条</span>
        </div>
        <div className="flex items-center gap-3">
          <label className="flex items-center gap-1.5 text-sm cursor-pointer select-none">
            <input
              type="checkbox"
              checked={unreadOnly}
              onChange={(e) => handleUnreadOnly(e.target.checked)}
              className="rounded border-border"
            />
            <span className="text-text2">只看未读</span>
          </label>
          <button
            onClick={() => readAllMut.mutate()}
            disabled={readAllMut.isPending}
            className="text-xs px-3 py-1.5 rounded-md border border-border text-text2 hover:text-text hover:border-border-light transition-colors disabled:opacity-50"
          >
            全部标记已读
          </button>
        </div>
      </div>

      {/* 通知列表 */}
      <div className="bg-card border border-border rounded-lg overflow-hidden">
        {isLoading ? (
          <div className="py-12 text-center text-text3 text-sm">加载中...</div>
        ) : items.length === 0 ? (
          <div className="py-12 text-center text-text3 text-sm">
            {unreadOnly ? '没有未读通知' : '暂无通知'}
          </div>
        ) : (
          items.map((n, idx) => {
            const st = SEVERITY_STYLE[n.severity] ?? SEVERITY_STYLE.info
            return (
              <div
                key={n.id}
                className={cn(
                  'flex items-start gap-3 px-4 py-3 transition-colors',
                  idx !== items.length - 1 && 'border-b border-border',
                  !n.read && 'bg-accent-dim/20',
                )}
              >
                {/* 未读指示点 */}
                <span className={cn('w-2 h-2 rounded-full shrink-0 mt-1.5', n.read ? 'bg-transparent' : st.dot)} />

                {/* 内容 */}
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className={cn('text-sm', n.read ? 'text-text2' : 'font-medium text-text')}>
                      {n.title}
                    </span>
                    <span className={cn('px-1.5 py-0.5 rounded text-[10px] font-medium', st.badge)}>
                      {n.severity}
                    </span>
                    <span className="px-1.5 py-0.5 rounded text-[10px] font-medium bg-bg2 text-text3">
                      {TYPE_LABEL[n.type] ?? n.type}
                    </span>
                  </div>
                  {n.content && (
                    <p className="text-xs text-text3 mt-0.5 line-clamp-2">{n.content}</p>
                  )}
                  <span className="text-[10px] text-text3 mt-1 block">{formatDate(n.created_at)}</span>
                </div>

                {/* 操作 */}
                {!n.read && (
                  <button
                    onClick={() => readOneMut.mutate(n.id)}
                    disabled={readOneMut.isPending}
                    className="shrink-0 text-xs text-text3 hover:text-accent transition-colors"
                    title="标记已读"
                  >
                    <i className="ti ti-check" />
                  </button>
                )}
              </div>
            )
          })
        )}
      </div>

      {/* 分页 */}
      {totalPages > 1 && (
        <div className="flex items-center justify-center gap-2 mt-4">
          <button
            onClick={() => setPage((p) => Math.max(0, p - 1))}
            disabled={page === 0}
            className="px-3 py-1 text-xs rounded border border-border text-text2 hover:text-text disabled:opacity-40"
          >
            上一页
          </button>
          <span className="text-xs text-text3">
            {page + 1} / {totalPages}
          </span>
          <button
            onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
            disabled={page >= totalPages - 1}
            className="px-3 py-1 text-xs rounded border border-border text-text2 hover:text-text disabled:opacity-40"
          >
            下一页
          </button>
        </div>
      )}
    </div>
  )
}
