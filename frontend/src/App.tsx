import { lazy, Suspense } from 'react'
import { Routes, Route, Navigate } from 'react-router-dom'
import Layout from '@/components/Layout'
import { useAuth } from '@/hooks/useAuth'
import { useAuthStore } from '@/stores/authStore'

// 懒加载所有页面
const LoginPage = lazy(() => import('@/pages/LoginPage'))
const DashboardPage = lazy(() => import('@/pages/DashboardPage'))
const UsersPage = lazy(() => import('@/pages/UsersPage'))
const DockerPage = lazy(() => import('@/pages/DockerPage'))
const ServicesPage = lazy(() => import('@/pages/ServicesPage'))
const CronPage = lazy(() => import('@/pages/CronPage'))
const NetworkPage = lazy(() => import('@/pages/NetworkPage'))
const ProxyPage = lazy(() => import('@/pages/ProxyPage'))
const LogsPage = lazy(() => import('@/pages/LogsPage'))
const NotificationsPage = lazy(() => import('@/pages/NotificationsPage'))
const NotificationCenterPage = lazy(() => import('@/pages/notifications/NotificationCenterPage'))
const ChannelManagementPage = lazy(() => import('@/pages/settings/ChannelManagementPage'))
const SettingsPage = lazy(() => import('@/pages/SettingsPage'))
const AuditPage = lazy(() => import('@/pages/AuditPage'))
const PanelUsersPage = lazy(() => import('@/pages/PanelUsersPage'))
const AssetsPage = lazy(() => import('@/pages/AssetsPage'))
const AgentsPage = lazy(() => import('@/pages/agents/AgentsPage'))
const AgentStudioPage = lazy(() => import('@/pages/agents/AgentStudioPage'))
const PlaybooksPage = lazy(() => import('@/pages/PlaybooksPage'))
const ServersPage = lazy(() => import('@/pages/ServersPage'))
const FleetDashboardPage = lazy(() => import('@/pages/FleetDashboardPage'))
const BatchOperationPage = lazy(() => import('@/pages/fleet/BatchOperationPage'))
const TeamsPage = lazy(() => import('@/pages/TeamsPage'))
const RolesPage = lazy(() => import('@/pages/settings/RolesPage'))
const AlertsPage = lazy(() => import('@/pages/AlertsPage'))
const AlertRulesPage = lazy(() => import('@/pages/AlertRulesPage'))
const FileBrowserPage = lazy(() => import('@/pages/files/FileBrowserPage'))
const ChangelogPage = lazy(() => import('@/pages/ChangelogPage'))
const PipelinesPage = lazy(() => import('@/pages/PipelinesPage'))

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { user, isLoading } = useAuthStore()
  if (isLoading) return <PageLoading />
  if (!user) return <Navigate to="/login" replace />
  return <>{children}</>
}

function PageLoading() {
  return (
    <div className="flex items-center justify-center h-screen bg-bg">
      <div className="text-text3 text-sm">加载中...</div>
    </div>
  )
}

export default function App() {
  useAuth()

  return (
    <Suspense fallback={<PageLoading />}>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route
          element={
            <ProtectedRoute>
              <Layout />
            </ProtectedRoute>
          }
        >
          <Route path="/" element={<Navigate to="/dashboard" replace />} />
          <Route path="/dashboard" element={<DashboardPage />} />
          <Route path="/users" element={<UsersPage />} />
          <Route path="/docker" element={<DockerPage />} />
          <Route path="/services" element={<ServicesPage />} />
          <Route path="/cron" element={<CronPage />} />
          <Route path="/network" element={<NetworkPage />} />
          <Route path="/proxy" element={<ProxyPage />} />
          <Route path="/logs" element={<LogsPage />} />
          <Route path="/notifications" element={<NotificationCenterPage />} />
          <Route path="/notifications/channels" element={<NotificationsPage />} />
          <Route path="/settings/channels" element={<ChannelManagementPage />} />
          <Route path="/settings" element={<SettingsPage />} />
          <Route path="/audit" element={<AuditPage />} />
          <Route path="/panel_users" element={<PanelUsersPage />} />
          <Route path="/assets" element={<AssetsPage />} />
          <Route path="/agents" element={<AgentsPage />} />
          <Route path="/agents/studio" element={<AgentStudioPage />} />
          <Route path="/playbooks" element={<PlaybooksPage />} />
          <Route path="/servers" element={<ServersPage />} />
          <Route path="/fleet" element={<FleetDashboardPage />} />
          <Route path="/fleet/batch" element={<BatchOperationPage />} />
          <Route path="/teams" element={<TeamsPage />} />
          <Route path="/settings/roles" element={<RolesPage />} />
          <Route path="/alerts" element={<AlertsPage />} />
          <Route path="/alerts/rules" element={<AlertRulesPage />} />
          <Route path="/files" element={<FileBrowserPage />} />
          <Route path="/changelog" element={<ChangelogPage />} />
          <Route path="/pipelines" element={<PipelinesPage />} />
          <Route path="/monitoring" element={<Navigate to="/dashboard" replace />} />
        </Route>
      </Routes>
    </Suspense>
  )
}
