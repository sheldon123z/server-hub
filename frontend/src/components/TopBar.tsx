import { useState, useRef, useEffect } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { useAuthStore } from '@/stores/authStore'
import { useServerStore } from '@/stores/serverStore'
import { authApi } from '@/api/auth'
import { useNavigate } from 'react-router-dom'
import { cn } from '@/lib/utils'
import NotificationBell from './NotificationBell'

/**
 * 顶部栏组件属性
 */
interface TopBarProps {
  /** 当前页面的中文标题，由 Layout 根据路由映射生成 */
  title: string
}

const STATUS_DOT: Record<string, string> = {
  online: 'bg-green',
  offline: 'bg-red',
  degraded: 'bg-yellow',
  unknown: 'bg-text3',
}

/**
 * 顶部栏组件
 * 显示页面标题、多服务器切换下拉菜单、当前用户信息和退出按钮
 * 切换服务器后自动 invalidate 所有 TanStack Query 缓存
 */
export default function TopBar({ title }: TopBarProps) {
  const { user, setUser } = useAuthStore()
  const { servers, selectedServerId, setSelectedServer, fetchServers } = useServerStore()
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const [dropdownOpen, setDropdownOpen] = useState(false)
  const dropdownRef = useRef<HTMLDivElement>(null)

  // 初始加载服务器列表
  useEffect(() => {
    fetchServers()
  }, [fetchServers])

  // 点击外部关闭下拉
  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setDropdownOpen(false)
      }
    }
    if (dropdownOpen) document.addEventListener('mousedown', handleClick)
    return () => document.removeEventListener('mousedown', handleClick)
  }, [dropdownOpen])

  const handleLogout = async () => {
    await authApi.logout()
    setUser(null)
    navigate('/login')
  }

  const currentServer = servers.find((s) => s.id === selectedServerId)
  const currentLabel = currentServer ? currentServer.name : '本机 (Hub)'
  const currentStatus = currentServer?.status ?? 'online'

  return (
    <header className="h-header border-b border-border flex items-center justify-between px-6 flex-shrink-0">
      <div className="text-base font-semibold">{title}</div>
      <div className="flex items-center gap-3">
        {/* 服务器选择器 */}
        <div className="relative" ref={dropdownRef}>
          <button
            onClick={() => setDropdownOpen(!dropdownOpen)}
            className="flex items-center gap-2 text-xs px-2.5 py-1.5 rounded-md border border-border text-text2 hover:text-text hover:border-border-light transition-colors"
          >
            <span className={cn('w-1.5 h-1.5 rounded-full', STATUS_DOT[currentStatus] ?? STATUS_DOT.unknown)} />
            <i className="ti ti-server-2 text-sm" />
            <span className="max-w-[120px] truncate">{currentLabel}</span>
            <i className={cn('ti ti-chevron-down text-xs transition-transform', dropdownOpen && 'rotate-180')} />
          </button>

          {dropdownOpen && (
            <div className="absolute right-0 top-full mt-1 w-56 bg-bg border border-border rounded-lg shadow-xl z-50 py-1 max-h-64 overflow-y-auto">
              {/* 默认本机选项 */}
              <button
                onClick={() => { setSelectedServer('local'); setDropdownOpen(false); queryClient.invalidateQueries() }}
                className={cn(
                  'w-full flex items-center gap-2 px-3 py-2 text-xs text-left hover:bg-bg2 transition-colors',
                  selectedServerId === 'local' && 'bg-accent-dim text-accent'
                )}
              >
                <span className={cn('w-1.5 h-1.5 rounded-full bg-green')} />
                <span>本机 (Hub)</span>
              </button>

              {servers.filter((s) => s.is_local !== 1).length > 0 && (
                <div className="border-t border-border my-1" />
              )}

              {servers.filter((s) => s.is_local !== 1).map((srv) => (
                <button
                  key={srv.id}
                  onClick={() => { setSelectedServer(srv.id); setDropdownOpen(false); queryClient.invalidateQueries() }}
                  className={cn(
                    'w-full flex items-center gap-2 px-3 py-2 text-xs text-left hover:bg-bg2 transition-colors',
                    selectedServerId === srv.id && 'bg-accent-dim text-accent'
                  )}
                >
                  <span className={cn('w-1.5 h-1.5 rounded-full', STATUS_DOT[srv.status] ?? STATUS_DOT.unknown)} />
                  <div className="flex-1 min-w-0">
                    <div className="truncate">{srv.name}</div>
                    <div className="text-text3 text-[10px]">{srv.ip_address}</div>
                  </div>
                </button>
              ))}

              {servers.filter((s) => s.is_local !== 1).length === 0 && (
                <div className="px-3 py-2 text-[10px] text-text3">暂无远程服务器</div>
              )}
            </div>
          )}
        </div>

        <span className="text-xs text-text3">每 15s 自动刷新</span>
        <NotificationBell />
        {user && (
          <div className="flex items-center gap-2">
            <span className="text-xs text-text2">{user.display_name || user.username}</span>
            <span className="text-[10px] text-text3">{user.role}</span>
            <button
              onClick={handleLogout}
              className="text-xs px-2 py-1 rounded border border-border text-text2 hover:text-text hover:border-border-light transition-colors"
            >
              退出
            </button>
          </div>
        )}
      </div>
    </header>
  )
}
