import { useState, useRef, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import client from '@/api/client'
import { cn, formatDate } from '@/lib/utils'

interface InAppNotification {
  id: number
  type: string
  title: string
  content: string | null
  severity: string
  read: boolean
  created_at: string
}

const SEVERITY_STYLE: Record<string, string> = {
  critical: 'text-red',
  warning: 'text-yellow',
  error: 'text-red',
  info: 'text-accent',
  success: 'text-green',
}

/**
 * 顶部栏铃铛通知组件
 * 显示未读数徽章，点击展开最近 10 条站内通知下拉面板
 */
export default function NotificationBell() {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)
  const navigate = useNavigate()
  const qc = useQueryClient()

  const { data: countData } = useQuery<{ count: number }>({
    queryKey: ['notif-unread-count'],
    queryFn: () => client.get('/api/notifications/unread-count').then((r) => r.data),
    refetchInterval: 30_000,
  })

  const { data: listData } = useQuery<{ items: InAppNotification[]; total: number }>({
    queryKey: ['notif-inbox-preview'],
    queryFn: () => client.get('/api/notifications', { params: { limit: 10 } }).then((r) => r.data),
    enabled: open,
  })

  const readAllMut = useMutation({
    mutationFn: () => client.put('/api/notifications/read-all').then((r) => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['notif-unread-count'] })
      qc.invalidateQueries({ queryKey: ['notif-inbox-preview'] })
    },
  })

  const readOneMut = useMutation({
    mutationFn: (id: number) => client.put(`/api/notifications/${id}/read`).then((r) => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['notif-unread-count'] })
      qc.invalidateQueries({ queryKey: ['notif-inbox-preview'] })
    },
  })

  useEffect(() => {
    if (!open) return
    function handleClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', handleClick)
    return () => document.removeEventListener('mousedown', handleClick)
  }, [open])

  const unread = countData?.count ?? 0
  const items = listData?.items ?? []

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => setOpen((v) => !v)}
        className="relative flex items-center justify-center w-8 h-8 rounded-md text-text2 hover:text-text hover:bg-bg2 transition-colors"
        title="通知"
      >
        <i className="ti ti-bell text-lg" />
        {unread > 0 && (
          <span className="absolute -top-0.5 -right-0.5 min-w-[16px] h-4 px-0.5 bg-red text-white text-[10px] font-bold rounded-full flex items-center justify-center leading-none">
            {unread > 99 ? '99+' : unread}
          </span>
        )}
      </button>

      {open && (
        <div className="absolute right-0 top-full mt-1 w-80 bg-bg border border-border rounded-lg shadow-xl z-50 overflow-hidden">
          {/* 头部 */}
          <div className="flex items-center justify-between px-3 py-2 border-b border-border">
            <span className="text-sm font-medium text-text">通知</span>
            <div className="flex items-center gap-2">
              {unread > 0 && (
                <button
                  onClick={() => readAllMut.mutate()}
                  className="text-xs text-text3 hover:text-accent transition-colors"
                >
                  全部已读
                </button>
              )}
              <button
                onClick={() => { setOpen(false); navigate('/notifications') }}
                className="text-xs text-text3 hover:text-accent transition-colors"
              >
                查看全部
              </button>
            </div>
          </div>

          {/* 通知列表 */}
          <div className="max-h-80 overflow-y-auto">
            {items.length === 0 ? (
              <div className="py-8 text-center text-text3 text-sm">暂无通知</div>
            ) : (
              items.map((n) => (
                <button
                  key={n.id}
                  onClick={() => { if (!n.read) readOneMut.mutate(n.id) }}
                  className={cn(
                    'w-full text-left px-3 py-2.5 border-b border-border last:border-0 hover:bg-bg2 transition-colors',
                    !n.read && 'bg-accent-dim/30',
                  )}
                >
                  <div className="flex items-start gap-2">
                    <span className={cn('mt-0.5 text-sm shrink-0', SEVERITY_STYLE[n.severity] ?? 'text-text2')}>
                      <i className={cn('ti', n.severity === 'critical' || n.severity === 'error' ? 'ti-alert-circle' : n.severity === 'warning' ? 'ti-alert-triangle' : 'ti-info-circle')} />
                    </span>
                    <div className="flex-1 min-w-0">
                      <div className={cn('text-sm truncate', !n.read ? 'text-text font-medium' : 'text-text2')}>
                        {n.title}
                      </div>
                      {n.content && (
                        <div className="text-xs text-text3 truncate mt-0.5">{n.content}</div>
                      )}
                      <div className="text-[10px] text-text3 mt-0.5">{formatDate(n.created_at)}</div>
                    </div>
                    {!n.read && <span className="w-1.5 h-1.5 rounded-full bg-accent shrink-0 mt-1.5" />}
                  </div>
                </button>
              ))
            )}
          </div>
        </div>
      )}
    </div>
  )
}
