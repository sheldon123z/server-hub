import { Outlet, useLocation } from 'react-router-dom'
import Sidebar from './Sidebar'
import TopBar from './TopBar'
import ChatWidget from './ChatWidget'

const PAGE_TITLES: Record<string, string> = {
  '/dashboard': '仪表盘',
  '/users': '用户管理',
  '/docker': 'Docker 管理',
  '/services': '服务管理',
  '/cron': '定时任务',
  '/network': '网络状态',
  '/proxy': '代理管理',
  '/logs': '日志查看',
  '/notifications': '通知管理',
  '/settings': '系统设置',
  '/audit': '审计日志',
  '/panel_users': '面板用户',
  '/assets': '资产管理',
  '/agents': 'OpsAgent',
  '/playbooks': '运维剧本',
  '/servers': '服务器管理',
  '/monitoring': '系统监控',
}

export default function Layout() {
  const location = useLocation()
  const title = PAGE_TITLES[location.pathname] || 'ServerHub'

  return (
    <div className="flex min-h-screen">
      <Sidebar />
      <div className="flex-1 ml-sidebar flex flex-col">
        <TopBar title={title} />
        <main className="flex-1 p-5 overflow-auto">
          <Outlet />
        </main>
      </div>
      <ChatWidget />
    </div>
  )
}
