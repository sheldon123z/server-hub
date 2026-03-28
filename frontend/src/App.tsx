import { lazy, Suspense } from 'react'
import { Routes, Route, Navigate } from 'react-router-dom'
import Layout from '@/components/Layout'
import ErrorBoundary from '@/components/ErrorBoundary'
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
const SettingsPage = lazy(() => import('@/pages/SettingsPage'))
const AuditPage = lazy(() => import('@/pages/AuditPage'))
const PanelUsersPage = lazy(() => import('@/pages/PanelUsersPage'))
const AssetsPage = lazy(() => import('@/pages/AssetsPage'))
const AgentsPage = lazy(() => import('@/pages/agents/AgentsPage'))
const PlaybooksPage = lazy(() => import('@/pages/PlaybooksPage'))

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
          <Route path="/dashboard" element={<ErrorBoundary><DashboardPage /></ErrorBoundary>} />
          <Route path="/users" element={<UsersPage />} />
          <Route path="/docker" element={<DockerPage />} />
          <Route path="/services" element={<ServicesPage />} />
          <Route path="/cron" element={<CronPage />} />
          <Route path="/network" element={<NetworkPage />} />
          <Route path="/proxy" element={<ProxyPage />} />
          <Route path="/logs" element={<LogsPage />} />
          <Route path="/notifications" element={<NotificationsPage />} />
          <Route path="/settings" element={<SettingsPage />} />
          <Route path="/audit" element={<AuditPage />} />
          <Route path="/panel_users" element={<PanelUsersPage />} />
          <Route path="/assets" element={<AssetsPage />} />
          <Route path="/agents" element={<AgentsPage />} />
          <Route path="/playbooks" element={<PlaybooksPage />} />
          <Route path="/monitoring" element={<Navigate to="/dashboard" replace />} />
        </Route>
      </Routes>
    </Suspense>
  )
}
