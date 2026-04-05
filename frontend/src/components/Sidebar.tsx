import { NavLink } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import client from '@/api/client'
import type { SidebarItem } from '@/types/api'
import { useAuthStore } from '@/stores/authStore'

// 静态 fallback — 当 /api/sidebar 不可用时使用
const FALLBACK_ITEMS: SidebarItem[] = [
  { name: 'dashboard', display_name: '仪表盘', icon: 'dashboard', category: '监控', required_role: 'user', order: 1 },
  { name: 'servers', display_name: '服务器', icon: 'server-2', category: '基础设施', required_role: 'admin', order: 2 },
  { name: 'fleet', display_name: '舰队总览', icon: 'topology-ring-3', category: '基础设施', required_role: 'admin', order: 3 },
  { name: 'agents', display_name: 'OpsAgent', icon: 'robot', category: '智能', required_role: 'user', order: 5 },
  { name: 'teams', display_name: '团队管理', icon: 'users-group', category: '智能', required_role: 'admin', order: 6 },
  { name: 'playbooks', display_name: '运维剧本', icon: 'script', category: '自动化', required_role: 'admin', order: 55 },
  { name: 'docker', display_name: 'Docker', icon: 'brand-docker', category: '管理', required_role: 'admin', order: 10 },
  { name: 'services', display_name: '服务管理', icon: 'server', category: '管理', required_role: 'admin', order: 11 },
  { name: 'users', display_name: '用户管理', icon: 'users', category: '管理', required_role: 'admin', order: 12 },
  { name: 'cron', display_name: '定时任务', icon: 'clock', category: '管理', required_role: 'admin', order: 13 },
  { name: 'logs', display_name: '日志查看', icon: 'file-text', category: '管理', required_role: 'admin', order: 14 },
  { name: 'notifications', display_name: '通知管理', icon: 'bell', category: '管理', required_role: 'admin', order: 15 },
  { name: 'network', display_name: '网络状态', icon: 'network', category: '网络', required_role: 'admin', order: 20 },
  { name: 'proxy', display_name: '代理管理', icon: 'shield', category: '网络', required_role: 'admin', order: 21 },
  { name: 'files', display_name: '文件管理', icon: 'folder', category: '资产', required_role: 'admin', order: 35 },
  { name: 'assets', display_name: '资产管理', icon: 'database', category: '资产', required_role: 'admin', order: 30 },
  { name: 'settings', display_name: '系统设置', icon: 'settings', category: '系统', required_role: 'admin', order: 40 },
  { name: 'audit', display_name: '审计日志', icon: 'list-search', category: '系统', required_role: 'admin', order: 41 },
  { name: 'panel_users', display_name: '面板用户', icon: 'user-cog', category: '系统', required_role: 'admin', order: 42 },
  { name: 'settings/roles', display_name: '权限管理', icon: 'shield-lock', category: '系统', required_role: 'admin', order: 43 },
]

/**
 * 侧边栏导航组件
 * 从 /api/sidebar 动态获取菜单项，按 category 分组渲染；
 * API 不可用时 fallback 到静态菜单列表，并根据用户角色过滤条目
 */
export default function Sidebar() {
  const user = useAuthStore((s) => s.user)

  const { data: apiItems } = useQuery({
    queryKey: ['sidebar'],
    queryFn: async () => {
      try {
        const r = await client.get<SidebarItem[]>('/api/sidebar')
        return r.data
      } catch {
        return null // fallback to static items
      }
    },
    staleTime: 5 * 60 * 1000,
    retry: false,
  })

  // 使用 API 数据，失败则 fallback 到静态列表（按角色过滤）
  const items = apiItems ?? FALLBACK_ITEMS.filter(
    (item) => item.required_role === 'user' || user?.role === 'admin'
  )

  const groups: Record<string, SidebarItem[]> = {}
  for (const item of items) {
    ;(groups[item.category] ??= []).push(item)
  }

  return (
    <aside className="fixed left-0 top-0 bottom-0 w-sidebar bg-bg2 border-r border-border flex flex-col z-40">
      <div className="p-4 border-b border-border">
        <h1 className="text-lg font-bold text-text m-0">ServerHub</h1>
        <div className="text-xs text-text3 mt-0.5">NF5468M6</div>
      </div>

      <nav className="flex-1 overflow-y-auto py-2 px-2">
        {Object.entries(groups).map(([category, categoryItems]) => (
          <div key={category}>
            <div className="text-[10px] uppercase tracking-wider text-text3 px-3 pt-4 pb-1">
              {category}
            </div>
            {categoryItems.map((item) => (
              <NavLink
                key={item.name}
                to={`/${item.name}`}
                className={({ isActive }) =>
                  `flex items-center gap-2.5 px-3 py-2 rounded-md text-[13px] transition-colors ${
                    isActive
                      ? 'bg-accent-dim text-accent'
                      : 'text-text2 hover:text-text hover:bg-[rgba(56,189,248,0.05)]'
                  }`
                }
              >
                <i className={`ti ti-${item.icon} text-base`} />
                {item.display_name}
              </NavLink>
            ))}
          </div>
        ))}
      </nav>
    </aside>
  )
}
