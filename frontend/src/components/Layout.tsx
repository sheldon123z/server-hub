import { Outlet, useLocation } from 'react-router-dom'
import Sidebar from './Sidebar'
import TopBar from './TopBar'
import ChatWidget from './ChatWidget'
import ErrorBoundary from './ErrorBoundary'

const PAGE_TITLES: Record<string, string> = {
  '/dashboard': '仪表盘',
  '/users': '用户管理',
  '/docker': 'Docker 管理',
  '/services': '服务管理',
  '/cron': '定时任务',
  '/network': '网络状态',
  '/proxy': '代理管理',
  '/logs': '日志查看',
  '/notifications': '通知中心',
  '/notifications/channels': '通知渠道',
  '/settings/channels': '通知渠道',
  '/settings': '系统设置',
  '/audit': '审计日志',
  '/panel_users': '面板用户',
  '/assets': '资产管理',
  '/agents': 'OpsAgent',
  '/agents/studio': 'Agent Studio',
  '/playbooks': '运维剧本',
  '/servers': '服务器管理',
  '/fleet': '舰队总览',
  '/monitoring': '系统监控',
}

/**
 * 全局布局组件
 * 三栏结构：固定侧边栏 + 顶部标题栏/内容区 + 浮动聊天组件
 * 每个子区域均被 ErrorBoundary 包裹，单模块渲染错误不影响其他区域
 */
export default function Layout() {
  const location = useLocation()
  const title = PAGE_TITLES[location.pathname] || 'ServerHub'

  return (
    <div className="flex min-h-screen">
      <ErrorBoundary fallback={null}>
        <Sidebar />
      </ErrorBoundary>
      <div className="flex-1 ml-sidebar flex flex-col">
        <ErrorBoundary fallback={<div className="h-header border-b border-border" />}>
          <TopBar title={title} />
        </ErrorBoundary>
        <main className="flex-1 p-5 overflow-auto">
          <ErrorBoundary key={location.pathname}>
            <Outlet />
          </ErrorBoundary>
        </main>
      </div>
      <ErrorBoundary fallback={null}>
        <ChatWidget />
      </ErrorBoundary>
    </div>
  )
}
